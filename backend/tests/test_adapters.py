import json

import pytest

from levelup.infra.public_http import CollectionError
from levelup.modules.tech.adapters import ADAPTERS, adapter_for_url, parse_list


def samsung(**changes):
    return dict(
        id="1",
        title="<b>행사 모집</b>",
        detailLink="/kr/insights/demo.html",
        releaseDate="2026-11-25",
        content="공개 소개",
        category=[{"name": "채용"}],
        **changes,
    )


def test_samsung_keeps_all_types_and_explicit_kst_date():
    feed = parse_list(json.dumps([samsung()]).encode(), ADAPTERS[0])
    assert feed.collector_type == "html" and len(feed.entries) == 1
    entry = feed.entries[0]
    assert entry.title == "행사 모집" and entry.tags == ("채용",)
    assert entry.publication.at.isoformat() == "2026-11-24T15:00:00+00:00"


def test_skplanet_explicit_list_contract():
    data = {
        "result": {
            "data": {
                "allMarkdownRemark": {
                    "nodes": [
                        {
                            "fields": {"slug": "/demo/"},
                            "frontmatter": {
                                "title": "모집",
                                "date": "November 25, 2026",
                                "tags": ["공지"],
                            },
                            "excerpt": "소개",
                        }
                    ]
                }
            }
        }
    }
    feed = parse_list(json.dumps(data).encode(), ADAPTERS[1])
    assert feed.entries[0].url == "https://techtopic.skplanet.com/demo/"
    assert feed.entries[0].publication.precision == "date"


@pytest.mark.parametrize("value", [None, 42, [], {"title": "missing"}, "bad"])
def test_bad_entries_quarantined(value):
    feed = parse_list(json.dumps([value, samsung()]).encode(), ADAPTERS[0])
    assert len(feed.entries) == 1 and len(feed.issues) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://www.samsungsds.com/kr/insights/index.html?category=1",
        "https://www.samsungsds.com.evil.com/kr/insights/index.html",
        "http://techtopic.skplanet.com/",
        "https://techtopic.skplanet.com/custom/",
    ],
)
def test_registry_is_fixed_and_does_not_guess(url):
    assert adapter_for_url(url) is None


def test_whole_corrupt_or_overflow_fails_not_empty_baseline():
    for body in [b"{}", b"null", b"<html>error</html>", json.dumps([samsung()] * 2001).encode()]:
        with pytest.raises(CollectionError):
            parse_list(body, ADAPTERS[0])
