"""Feed parsing and discovery, independent of HTTP, authentication and persistence."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from levelup.infra.public_http import MAX_BODY_BYTES, CollectionError, normalize_url

ATOM = "http://www.w3.org/2005/Atom"
RSS = "http://purl.org/rss/1.0/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC = "http://purl.org/dc/elements/1.1/"
XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"


@dataclass(frozen=True)
class Publication:
    at: datetime | None
    precision: Literal["timestamp", "date", "missing", "invalid"]
    raw: str | None


@dataclass(frozen=True)
class ParsedEntry:
    index: int
    title: str
    url: str
    guid: str | None
    publication: Publication
    intro: str | None
    tags: tuple[str, ...]
    content_hash: str

    @property
    def keys(self) -> tuple[tuple[str, str], ...]:
        values = [("url", self.url)]
        if self.guid:
            values.append(("guid", self.guid))
        return tuple(values)


@dataclass(frozen=True)
class EntryIssue:
    index: int
    code: str
    # Independent hashes retain strong identity without storing the malformed item body.
    identity_hashes: tuple[tuple[str, str], ...]
    content_hash: str


@dataclass(frozen=True)
class ParsedFeed:
    name: str
    entries: tuple[ParsedEntry, ...]
    issues: tuple[EntryIssue, ...]
    collector_type: Literal["rss", "atom", "html"] = "rss"

    @property
    def result(self) -> Literal["success", "partial", "failed"]:
        if not self.issues:
            return "success"
        return "partial" if self.entries else "failed"

    @property
    def baseline_usable(self) -> bool:
        return self.result != "failed"


class _SafeTreeBuilder(ET.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise CollectionError("INVALID_FEED")


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.blocked += 1
        if tag in ("p", "br", "div", "li") and not self.blocked:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.blocked = max(0, self.blocked - 1)
        if not self.blocked:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.blocked:
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _Text()
    parser.feed(value)
    return " ".join("".join(parser.parts).split())


def _value(element: ET.Element, path: str) -> str:
    child = element.find(path)
    return "" if child is None else "".join(child.itertext()).strip()


def parse_publication(value: str, source_timezone: ZoneInfo | None) -> Publication:
    raw = value.strip()
    if not raw:
        return Publication(None, "missing", None)
    try:
        date_only = re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) is not None
        try:
            at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            at = parsedate_to_datetime(raw)
        if at.tzinfo is None:
            if source_timezone is None:
                return Publication(None, "invalid", raw)
            at = at.replace(tzinfo=source_timezone)
            if at.astimezone(UTC).astimezone(source_timezone).replace(tzinfo=None) != at.replace(
                tzinfo=None
            ):
                return Publication(None, "invalid", raw)
            if at.utcoffset() != at.replace(fold=1).utcoffset():
                return Publication(None, "invalid", raw)
        return Publication(at.astimezone(UTC), "date" if date_only else "timestamp", raw)
    except (ValueError, TypeError, OverflowError):
        return Publication(None, "invalid", raw)


def parse_feed(
    body: bytes, url: str, *, max_items: int, source_timezone: ZoneInfo | None = None
) -> ParsedFeed:
    """Limits/timezones come from the reviewed adapter contract, never from the URL owner."""
    if max_items < 1:
        raise ValueError("max_items must be positive")
    url = normalize_url(url)
    if len(body) > MAX_BODY_BYTES:
        raise CollectionError("RESPONSE_TOO_LARGE")
    try:
        root = ET.fromstring(body, parser=ET.XMLParser(target=_SafeTreeBuilder()))
    except (ET.ParseError, ValueError):
        raise CollectionError("INVALID_FEED") from None
    base = urljoin(url, root.get(XML_BASE, ""))
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise CollectionError("INVALID_FEED")
        container, prefix, atom = channel, "", False
        base = urljoin(base, channel.get(XML_BASE, ""))
        items = channel.findall("item")
    elif root.tag == f"{{{ATOM}}}feed":
        container, prefix, atom = root, f"{{{ATOM}}}", True
        items = root.findall(f"{prefix}entry")
    elif root.tag == f"{{{RDF}}}RDF":
        channel = root.find(f"{{{RSS}}}channel")
        if channel is None:
            raise CollectionError("INVALID_FEED")
        container, prefix, atom = channel, f"{{{RSS}}}", False
        items = root.findall(f"{prefix}item")
    else:
        raise CollectionError("INVALID_FEED")
    if len(items) > max_items:
        raise CollectionError("ITEM_LIMIT")
    entries: list[ParsedEntry] = []
    issues: list[EntryIssue] = []
    for index, item in enumerate(items):
        content_hash = hashlib.sha256(ET.tostring(item)).hexdigest()
        entry_base = urljoin(base, item.get(XML_BASE, ""))
        guid = _value(item, f"{prefix}id" if atom else "guid") or None
        link = _value(item, f"{prefix}link")
        if atom:
            link = ""
            for child in item.findall(f"{prefix}link"):
                if child.get("rel", "alternate") == "alternate" and child.get("type", "") in (
                    "",
                    "text/html",
                    "application/xhtml+xml",
                ):
                    link = (
                        urljoin(urljoin(entry_base, child.get(XML_BASE, "")), child.get("href", ""))
                        if child.get("href")
                        else ""
                    )
                    break
        elif not link:
            identifier = item.find("guid")
            if identifier is not None and identifier.get("isPermaLink", "true").lower() == "true":
                link = guid or ""
        hashes: list[tuple[str, str]] = []
        if guid:
            hashes.append(("guid", hashlib.sha256(guid.encode()).hexdigest()))
        try:
            if not link:
                raise CollectionError("INVALID_ENTRY_URL")
            canonical_url = normalize_url(urljoin(entry_base, link))
            hashes.append(("url", hashlib.sha256(canonical_url.encode()).hexdigest()))
            title = plain_text(_value(item, f"{prefix}title"))
            if not title:
                raise CollectionError("MISSING_TITLE")
            date = _value(item, f"{prefix}published" if atom else "pubDate")
            if not atom and not date:
                date = _value(item, f"{{{DC}}}date")
            intro = plain_text(_value(item, f"{prefix}summary" if atom else f"{prefix}description"))
            categories = item.findall(f"{prefix}category")
            tags = tuple(
                dict.fromkeys(
                    text
                    for category in categories
                    if (
                        text := plain_text(
                            category.get("term", "") if atom else "".join(category.itertext())
                        )
                    )
                )
            )
            entries.append(
                ParsedEntry(
                    index,
                    title,
                    canonical_url,
                    guid,
                    parse_publication(date, source_timezone),
                    intro or None,
                    tags,
                    content_hash,
                )
            )
        except CollectionError as exc:
            issues.append(EntryIssue(index, exc.code, tuple(hashes), content_hash))
    return ParsedFeed(
        plain_text(_value(container, f"{prefix}title")),
        tuple(entries),
        tuple(issues),
        "atom" if atom else "rss",
    )


class _Alternates(HTMLParser):
    def __init__(self, url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.url = url
        self.base = url
        self.base_seen = False
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        href = values.get("href")
        if tag == "base" and href and not self.base_seen:
            self.base = urljoin(self.url, href)
            self.base_seen = True
        if tag == "link" and href and "alternate" in (values.get("rel") or "").lower().split():
            if (values.get("type") or "").lower().split(";", 1)[0].strip() in (
                "application/rss+xml",
                "application/atom+xml",
            ):
                self.links.append((href, values.get("title") or ""))


def discover_feeds(body: bytes, url: str, *, max_candidates: int) -> tuple[str, ...]:
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    if len(body) > MAX_BODY_BYTES:
        raise CollectionError("RESPONSE_TOO_LARGE")
    parser = _Alternates(normalize_url(url))
    try:
        parser.feed(body.decode("utf-8-sig"))
    except UnicodeError:
        raise CollectionError("INVALID_RESPONSE") from None
    candidates = tuple(
        dict.fromkeys(normalize_url(urljoin(parser.base, href)) for href, _ in parser.links)
    )
    if len(candidates) > max_candidates:
        raise CollectionError("CANDIDATE_LIMIT")
    return candidates
