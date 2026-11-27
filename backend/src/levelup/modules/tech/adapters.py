"""Reviewed fixed-site adapters. Parse public list data, never execute publisher JavaScript."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from levelup.infra.public_http import MAX_BODY_BYTES, CollectionError, normalize_url
from levelup.modules.tech.feeds import (
    EntryIssue,
    ParsedEntry,
    ParsedFeed,
    parse_publication,
    plain_text,
)


@dataclass(frozen=True)
class ListAdapter:
    key: str
    name: str
    host: str
    input_paths: tuple[str, ...]
    collection_path: str
    max_items: int

    @property
    def collection_url(self) -> str:
        return "https://" + self.host + self.collection_path


ADAPTERS = (
    ListAdapter(
        "samsung-insights-v1",
        "삼성SDS",
        "www.samsungsds.com",
        ("/kr/insights/", "/kr/insights/index.html", "/kr/insights/insights.txt"),
        "/kr/insights/insights.txt",
        2000,
    ),
    ListAdapter(
        "skplanet-page-data-v1",
        "SK플래닛 TECH TOPIC",
        "techtopic.skplanet.com",
        ("/", "/page-data/index/page-data.json"),
        "/page-data/index/page-data.json",
        1000,
    ),
)


def adapter_for_url(url: str) -> ListAdapter | None:
    value = urlsplit(normalize_url(url))
    if value.query or value.scheme != "https":
        return None
    return next(
        (
            adapter
            for adapter in ADAPTERS
            if adapter.host == value.hostname and value.path in adapter.input_paths
        ),
        None,
    )


# Publishers whose feed lives at a non-standard path. A listed URL is only a lead: it still has
# to parse as a usable feed before it is offered.
KNOWN_FEEDS = {"d2.naver.com": "https://d2.naver.com/d2.atom"}


def known_feed_for_url(url: str) -> str | None:
    host = urlsplit(normalize_url(url)).hostname
    return KNOWN_FEEDS.get(host) if host else None


def parse_list(body: bytes, adapter: ListAdapter) -> ParsedFeed:
    if len(body) > MAX_BODY_BYTES:
        raise CollectionError("RESPONSE_TOO_LARGE")
    try:
        document = json.loads(body)
        values = (
            document
            if adapter.key == "samsung-insights-v1"
            else document["result"]["data"]["allMarkdownRemark"]["nodes"]
        )
        if not isinstance(values, list):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise CollectionError("INVALID_FEED") from None
    if len(values) > adapter.max_items:
        raise CollectionError("ITEM_LIMIT")
    entries, issues = [], []
    for index, value in enumerate(values):
        fingerprint = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        hashes: list[tuple[str, str]] = []
        try:
            if not isinstance(value, dict):
                raise CollectionError("INVALID_ENTRY")
            if adapter.key == "samsung-insights-v1":
                title, link = value["title"], value["detailLink"]
                raw_date = value.get("releaseDate", "")
                guid = str(value["id"]) if value.get("id") else None
                intro, tags = (
                    value.get("content", ""),
                    [v["name"] for v in value.get("category", [])],
                )
            else:
                metadata = value["frontmatter"]
                title, link = metadata["title"], value["fields"]["slug"]
                raw_date, guid = metadata.get("date", ""), None
                intro = metadata.get("description") or value.get("excerpt", "")
                tags = metadata.get("tags") or []
            if guid:
                hashes.append(("guid", hashlib.sha256(guid.encode()).hexdigest()))
            if not isinstance(link, str) or not link:
                raise CollectionError("INVALID_ENTRY_URL")
            url = normalize_url(urljoin(adapter.collection_url, link))
            hashes.append(("url", hashlib.sha256(url.encode()).hexdigest()))
            if not isinstance(title, str) or not plain_text(title):
                raise CollectionError("MISSING_TITLE")
            if (
                not isinstance(intro, str)
                or not isinstance(raw_date, str)
                or not isinstance(tags, list)
                or not all(isinstance(t, str) for t in tags)
            ):
                raise CollectionError("INVALID_ENTRY")
            for field in [title, intro, raw_date, *tags]:
                field.encode("utf8")
            parsed_date = raw_date
            if adapter.key == "skplanet-page-data-v1" and raw_date:
                try:
                    parsed_date = datetime.strptime(raw_date, "%B %d, %Y").date().isoformat()
                except ValueError:
                    pass
            publication = replace(
                parse_publication(parsed_date, ZoneInfo("Asia/Seoul")), raw=raw_date or None
            )
            entries.append(
                ParsedEntry(
                    index,
                    plain_text(title),
                    url,
                    guid,
                    publication,
                    plain_text(intro) or None,
                    tuple(dict.fromkeys(plain_text(tag) for tag in tags)),
                    fingerprint,
                )
            )
        except (CollectionError, ValueError, TypeError, KeyError, AttributeError):
            issues.append(EntryIssue(index, "INVALID_ENTRY", tuple(hashes), fingerprint))
    return ParsedFeed(adapter.name, tuple(entries), tuple(issues), "html")
