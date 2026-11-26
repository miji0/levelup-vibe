from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from levelup.infra.public_http import CollectionError, PublicResponse
from levelup.modules.tech.collection import CollectionCore, FeedContract
from levelup.modules.tech.eligibility import Eligibility, compute_eligibility, match_article
from levelup.modules.tech.feeds import discover_feeds, parse_feed, parse_publication

FIXTURES = Path(__file__).parent / "fixtures" / "collection"
URL = "https://blog.example/feed.xml"
KST = ZoneInfo("Asia/Seoul")


def test_rss_keeps_all_five_content_types_and_quarantines_bad_item():
    feed = parse_feed((FIXTURES / "rss.xml").read_bytes(), URL, max_items=10)
    assert [entry.title for entry in feed.entries] == [
        "기술 글",
        "채용",
        "행사 모집",
        "일반 기업 소식",
        "홍보",
    ]
    assert feed.entries[0].url == "https://blog.example/Tech?b=2&a=1"
    assert feed.entries[0].intro == "소개 문구"
    assert feed.entries[0].tags == ("기술",)
    assert feed.entries[1].url == "https://blog.example/jobs"
    assert [entry.publication.precision for entry in feed.entries] == [
        "timestamp",
        "missing",
        "invalid",
        "invalid",
        "missing",
    ]
    assert feed.result == "partial" and feed.baseline_usable
    assert feed.issues[0].code == "MISSING_TITLE"
    assert {kind for kind, _ in feed.issues[0].identity_hashes} == {"url", "guid"}


def test_atom_xml_base_alternate_and_publication_not_updated():
    feed = parse_feed((FIXTURES / "atom.xml").read_bytes(), URL, max_items=2)
    first, second = feed.entries
    assert first.url == "https://blog.example/articles/2026/post?x=1&y=2"
    assert first.guid == "urn:entry:1" and first.tags == ("행사",)
    assert first.publication.at == datetime(2026, 11, 25, 14, 59, 59, tzinfo=UTC)
    assert second.publication.precision == "missing"


def test_empty_feed_is_usable_but_all_invalid_items_are_not():
    empty = parse_feed(b"<rss><channel><title>Empty</title></channel></rss>", URL, max_items=2)
    assert empty.result == "success" and empty.baseline_usable
    invalid = parse_feed(
        b"<rss><channel><item><title>No link</title></item></channel></rss>", URL, max_items=2
    )
    assert invalid.result == "failed" and not invalid.baseline_usable


@pytest.mark.parametrize(
    "body",
    [
        b"<rss><channel>",
        b"<html/>",
        b"<rss/>",
        b'<!DOCTYPE rss [<!ENTITY x "EXPAND">]><rss><channel><title>&x;</title></channel></rss>',
        b'<!DOCTYPE rss SYSTEM "file:///etc/passwd"><rss><channel/></rss>',
        '<!DOCTYPE rss [<!ENTITY x "EXPAND">]><rss><channel/></rss>'.encode("utf-16"),
    ],
)
def test_document_failure_and_dtd_are_not_partial_success(body):
    with pytest.raises(CollectionError, match="INVALID_FEED"):
        parse_feed(body, URL, max_items=10)


def test_item_limit_is_whole_failure_instead_of_silent_truncation():
    with pytest.raises(CollectionError, match="ITEM_LIMIT"):
        parse_feed((FIXTURES / "rss.xml").read_bytes(), URL, max_items=5)


def test_original_private_links_are_item_errors_not_opened():
    feed = parse_feed(
        b"<rss><channel><item><title>Bad</title>"
        b"<link>http://127.0.0.1/private</link></item></channel></rss>",
        URL,
        max_items=2,
    )
    assert feed.result == "failed" and feed.issues[0].code == "PRIVATE_URL"


def test_rss_one_and_dc_date():
    body = b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
        <channel><title>RSS1</title></channel><item><title>A</title>
        <link>https://blog.example/a</link><dc:date>2026-11-25T00:00:00Z</dc:date>
        </item></rdf:RDF>"""
    feed = parse_feed(body, URL, max_items=1)
    assert feed.entries[0].publication.at == datetime(2026, 11, 25, tzinfo=UTC)


def test_discovery_resolves_base_deduplicates_and_preserves_choice():
    body = (FIXTURES / "discovery.html").read_bytes()
    assert discover_feeds(body, URL, max_candidates=2) == (
        "https://blog.example/feeds/rss.xml",
        "https://blog.example/feeds/atom.xml",
    )
    with pytest.raises(CollectionError, match="CANDIDATE_LIMIT"):
        discover_feeds(body, URL, max_candidates=1)


def test_date_only_requires_reviewed_source_timezone():
    assert parse_publication("2026-11-25", None).precision == "invalid"
    pub = parse_publication("2026-11-25", KST)
    assert pub.precision == "date" and pub.at == datetime(2026, 11, 24, 15, tzinfo=UTC)
    assert parse_publication("2026-02-30", KST).precision == "invalid"
    assert parse_publication("Wed, 25 Nov 2026 12:00:00", None).precision == "invalid"


@pytest.mark.parametrize("raw", ["2026-03-08T02:30:00", "2026-11-01T01:30:00"])
def test_dst_nonexistent_or_ambiguous_time_not_guessed(raw):
    assert parse_publication(raw, ZoneInfo("America/New_York")).precision == "invalid"


def eligibility(**kwargs):
    args = dict(
        baseline=False,
        epoch_kind="first_add",
        epoch_started_at=datetime(2026, 11, 20, tzinfo=KST),
        first_seen_at=datetime(2026, 11, 26, 8, 3, tzinfo=KST),
        published_at=datetime(2026, 11, 25, 23, 59, 59, tzinfo=KST),
    )
    args.update(kwargs)
    return compute_eligibility(**args)


def test_initial_import_and_recovered_initial_issue_never_notify():
    assert eligibility(baseline=True) == Eligibility("baseline", None)
    prior = Eligibility("baseline", None)
    assert eligibility(existing=prior) is prior


def test_kst_date_boundaries_late_discovery_missing_and_future_dates():
    assert eligibility().eligible_on == date(2026, 11, 26)
    assert eligibility(published_at=datetime(2026, 11, 25, 15, tzinfo=UTC)).eligible_on == date(
        2026, 11, 27
    )
    assert eligibility(published_at=datetime(2026, 1, 1, tzinfo=UTC)).eligible_on == date(
        2026, 11, 26
    )
    assert eligibility(published_at=None).eligible_on == date(2026, 11, 27)
    assert eligibility(published_at=datetime(2026, 12, 1, tzinfo=KST)).eligible_on == date(
        2026, 12, 2
    )


@pytest.mark.parametrize("kind", ["resume", "readd"])
def test_reactivation_suppresses_old_publication_but_first_add_allows_late_discovery(kind):
    old = datetime(2026, 11, 19, tzinfo=KST)
    assert eligibility(epoch_kind=kind, published_at=old) == Eligibility("suppressed", None)
    assert eligibility(published_at=old).state == "pending"
    assert eligibility(epoch_kind=kind, published_at=None).state == "pending"


def test_corrected_publication_recalculates_only_mutable_pending():
    before = Eligibility("pending", date(2026, 11, 26))
    corrected = datetime(2026, 11, 26, tzinfo=KST)
    assert eligibility(existing=before, published_at=corrected).eligible_on == date(2026, 11, 27)
    assert eligibility(existing=before, published_at=corrected, reserved=True) is before
    for state in ("baseline", "suppressed", "notified"):
        existing = Eligibility(state, None)
        assert eligibility(existing=existing, published_at=corrected) is existing
    with pytest.raises(ValueError, match="Timezone-aware"):
        eligibility(first_seen_at=datetime(2026, 11, 26))


def test_guid_or_url_match_updates_identity_but_conflict_never_merges():
    aliases = {("guid", "id1"): "a", ("url", "https://blog.example/a"): "a"}
    assert match_article((("guid", "id1"), ("url", "https://blog.example/new")), aliases) == "a"
    assert match_article((("guid", "changed"), ("url", "https://blog.example/a")), aliases) == "a"
    assert match_article((("guid", "new"),), aliases) is None
    with pytest.raises(CollectionError, match="IDENTITY_CONFLICT"):
        match_article((("guid", "id1"), ("url", "other")), {**aliases, ("url", "other"): "b"})


class FixtureHTTP:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def check_url(self, url):
        if "private.example" in url:
            raise CollectionError("PRIVATE_URL")
        return url, ("93.184.216.34",)

    async def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.pages[url]


@pytest.mark.asyncio
async def test_resolution_checks_candidates_and_registration_revalidates_selection():
    rss_url = "https://blog.example/feeds/rss.xml"
    atom_url = "https://blog.example/feeds/atom.xml"
    pages = {
        URL: PublicResponse(URL, 200, (FIXTURES / "discovery.html").read_bytes(), "text/html"),
        rss_url: PublicResponse(rss_url, 200, (FIXTURES / "rss.xml").read_bytes(), "text/xml"),
        atom_url: PublicResponse(atom_url, 200, (FIXTURES / "atom.xml").read_bytes(), "text/xml"),
    }
    http = FixtureHTTP(pages)
    core = CollectionCore(http, FeedContract(10, 2))
    resolution = await core.resolve(URL)
    assert resolution.requires_selection and len(resolution.options) == 2
    assert resolution.options[0].result == "partial"
    assert (await core.validate_selection(URL, rss_url)).collection_url == rss_url
    with pytest.raises(CollectionError, match="INVALID_SELECTION"):
        await core.validate_selection(URL, "https://other.example/feed")
    assert len(http.calls) == 9


@pytest.mark.asyncio
async def test_baseline_and_open_issues_force_body_and_reject_304():
    http = FixtureHTTP({URL: PublicResponse(URL, 304, b"", "")})
    core = CollectionCore(http, FeedContract(10, 2))
    response, feed = await core.collect(URL, baseline=False, etag='"known"')
    assert response.status == 304 and feed is None
    for baseline, has_open_issues in ((True, False), (False, True)):
        with pytest.raises(CollectionError, match="BODY_REQUIRED"):
            await core.collect(
                URL, baseline=baseline, has_open_issues=has_open_issues, etag='"known"'
            )
        assert http.calls[-1][1] == {"etag": None, "last_modified": None}


@pytest.mark.asyncio
async def test_private_dns_original_url_is_quarantined_with_identity():
    body = b"<rss><channel><item><guid isPermaLink='false'>id</guid><title>A</title>"
    body += b"<link>https://private.example/a</link></item></channel></rss>"
    core = CollectionCore(
        FixtureHTTP({URL: PublicResponse(URL, 200, body, "text/xml")}), FeedContract(10, 2)
    )
    _, feed = await core.collect(URL, baseline=True)
    assert feed.result == "failed" and feed.issues[0].code == "PRIVATE_URL"
    assert {kind for kind, _ in feed.issues[0].identity_hashes} == {"url", "guid"}


def test_unidentifiable_issue_keeps_fingerprint_without_raw_body():
    feed = parse_feed(
        b"<rss><channel><item><description>broken</description></item></channel></rss>",
        URL,
        max_items=1,
    )
    issue = feed.issues[0]
    assert not issue.identity_hashes and len(issue.content_hash) == 64
    assert "broken" not in repr(issue)


@pytest.mark.asyncio
async def test_network_item_errors_preserve_original_feed_indices():
    body = b"<rss><channel><item/><item><title>A</title>"
    body += b"<link>https://private.example/a</link></item></channel></rss>"
    core = CollectionCore(
        FixtureHTTP({URL: PublicResponse(URL, 200, body, "text/xml")}), FeedContract(10, 2)
    )
    _, feed = await core.collect(URL, baseline=True)
    assert {issue.index for issue in feed.issues} == {0, 1}


@pytest.mark.asyncio
async def test_unsupported_html_never_claims_a_collector_exists():
    core = CollectionCore(
        FixtureHTTP({URL: PublicResponse(URL, 200, b"<html></html>", "text/html")}),
        FeedContract(10, 2),
    )
    with pytest.raises(CollectionError, match="UNSUPPORTED_SOURCE"):
        await core.resolve(URL)
