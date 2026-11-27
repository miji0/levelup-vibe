"""Collection core. Database generations, leases and transactions belong to the job caller."""

import asyncio
import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from levelup.infra.public_http import CollectionError, PublicResponse, SafePublicHTTP
from levelup.modules.tech.adapters import adapter_for_url, known_feed_for_url, parse_list
from levelup.modules.tech.feeds import (
    EntryIssue,
    ParsedFeed,
    discover_feeds,
    parse_feed,
    probe_candidates,
)

# Whole-fallback time budget (seconds) for pages that advertise no feed.
PROBE_BUDGET = 20.0


@dataclass(frozen=True)
class FeedContract:
    # DEC-003 requires explicit reviewed bounds and timezone for each supported adapter.
    max_items: int
    max_candidates: int
    source_timezone: ZoneInfo | None = None

    def __post_init__(self) -> None:
        if self.max_items < 1 or self.max_candidates < 1:
            raise ValueError("Positive reviewed limits required")


@dataclass(frozen=True)
class FeedOption:
    name: str
    collection_url: str
    result: str
    collector_type: str = "rss"
    adapter_key: str | None = None


@dataclass(frozen=True)
class Resolution:
    input_url: str
    options: tuple[FeedOption, ...]
    candidate_errors: tuple[str, ...] = ()

    @property
    def requires_selection(self) -> bool:
        return len(self.options) > 1


class CollectionCore:
    def __init__(self, http: SafePublicHTTP, contract: FeedContract) -> None:
        self.http = http
        self.contract = contract

    async def _parse(self, response: PublicResponse) -> ParsedFeed:
        if response.status != 200:
            raise CollectionError("BODY_REQUIRED")
        adapter = adapter_for_url(response.url)
        feed = (
            parse_list(response.body, adapter)
            if adapter and response.url == adapter.collection_url
            else parse_feed(
                response.body,
                response.url,
                max_items=self.contract.max_items,
                source_timezone=self.contract.source_timezone,
            )
        )
        entries = []
        issues = list(feed.issues)
        destinations: dict[str | None, str | None] = {}
        for entry in feed.entries:
            try:
                host = urlsplit(entry.url).hostname
                if host not in destinations:
                    try:
                        await self.http.check_url(entry.url)
                        destinations[host] = None
                    except CollectionError as exc:
                        destinations[host] = exc.code
                if destinations[host] is not None:
                    raise CollectionError(destinations[host] or "PRIVATE_URL")
                entries.append(entry)
            except CollectionError as exc:
                hashes = tuple(
                    (kind, hashlib.sha256(value.encode()).hexdigest()) for kind, value in entry.keys
                )
                issues.append(EntryIssue(entry.index, exc.code, hashes, entry.content_hash))
        return ParsedFeed(feed.name, tuple(entries), tuple(issues), feed.collector_type)

    async def collect(
        self,
        url: str,
        *,
        baseline: bool,
        has_open_issues: bool = False,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> tuple[PublicResponse, ParsedFeed | None]:
        needs_body = baseline or has_open_issues
        response = await self.http.fetch(
            url,
            etag=None if needs_body else etag,
            last_modified=None if needs_body else last_modified,
        )
        if response.status == 304 and not needs_body:
            return response, None
        return response, await self._parse(response)

    async def resolve(self, input_url: str) -> Resolution:
        response = await self.http.fetch(input_url)
        adapter = adapter_for_url(response.url)
        if adapter:
            data = (
                response
                if response.url == adapter.collection_url
                else await self.http.fetch(adapter.collection_url)
            )
            feed = await self._parse(data)
            if not feed.baseline_usable:
                raise CollectionError("INVALID_FEED")
            return Resolution(
                input_url, (FeedOption(feed.name, data.url, feed.result, "html", adapter.key),)
            )
        content_type = response.content_type.split(";", 1)[0].strip().lower()
        if content_type not in ("text/html", "application/xhtml+xml"):
            feed = await self._parse(response)
            if not feed.baseline_usable:
                raise CollectionError("INVALID_FEED")
            return Resolution(
                input_url, (FeedOption(feed.name, response.url, feed.result, feed.collector_type),)
            )
        urls = discover_feeds(
            response.body, response.url, max_candidates=self.contract.max_candidates
        )
        if not urls:
            return await self._resolve_without_advertised_feed(input_url, response.url)
        options: dict[str, FeedOption] = {}
        errors = []
        for url in urls:
            try:
                candidate = await self.http.fetch(url)
                feed = await self._parse(candidate)
                if not feed.baseline_usable:
                    raise CollectionError("INVALID_FEED")
                options[candidate.url] = FeedOption(
                    feed.name, candidate.url, feed.result, feed.collector_type
                )
            except CollectionError as exc:
                errors.append(exc.code)
        if not options:
            # The page advertised links but none is a usable feed (e.g. an alternate pointing back
            # at the page itself): guess common paths too, and keep the original verdict if nothing
            # is found.
            try:
                return await self._resolve_without_advertised_feed(input_url, response.url)
            except CollectionError:
                raise CollectionError("INVALID_FEED") from None
        return Resolution(input_url, tuple(options.values()), tuple(errors))

    async def _resolve_without_advertised_feed(self, input_url: str, page_url: str) -> Resolution:
        """Same-origin guesses, then a reviewed lead for the host; only a parsed feed counts."""
        candidates = list(probe_candidates(page_url))
        known = known_feed_for_url(page_url)
        if known and known not in candidates:
            candidates.append(known)
        option = await self._first_usable_feed(candidates)
        if option is None:
            raise CollectionError("UNSUPPORTED_SOURCE")
        return Resolution(input_url, (option,))

    async def _first_usable_feed(self, candidates: list[str]) -> FeedOption | None:
        tasks = [asyncio.ensure_future(self._try_feed(url)) for url in candidates]
        try:
            async with asyncio.timeout(PROBE_BUDGET):
                results = await asyncio.gather(*tasks, return_exceptions=True)
        except TimeoutError:
            # Keep whatever finished in time and drain the cancelled rest.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            results = [
                None if task.cancelled() else task.exception() or task.result() for task in tasks
            ]
        for result in results:
            if isinstance(result, BaseException):
                raise result
        # Candidate order is priority, so the answer does not depend on which probe returns first.
        return next((result for result in results if isinstance(result, FeedOption)), None)

    async def _try_feed(self, url: str) -> FeedOption | None:
        try:
            response = await self.http.fetch(url)
            feed = await self._parse(response)
        except CollectionError:
            return None  # A missing page, a block or a non-feed reply is just "not here".
        if not feed.baseline_usable:
            return None
        return FeedOption(feed.name, response.url, feed.result, feed.collector_type)

    async def validate_selection(self, input_url: str, collection_url: str) -> FeedOption:
        # Registration must re-resolve; a client's earlier discovery response is not authority.
        selection, _ = await self.http.check_url(collection_url)
        resolution = await self.resolve(input_url)
        for option in resolution.options:
            if option.collection_url == selection:
                return option
        raise CollectionError("INVALID_SELECTION")
