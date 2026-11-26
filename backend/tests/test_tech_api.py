from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import FakeGoogle, login
from fastapi.testclient import TestClient
from test_collection import FixtureHTTP
from test_collection_store import URL, Core, add, item, rows, rss

from levelup.api.app import create_app
from levelup.infra.public_http import PublicResponse
from levelup.modules.tech.collection import CollectionCore, FeedContract
from levelup.modules.tech.persistence import CollectionStore
from levelup.modules.tech.reading import ReadingStore
from levelup.modules.tech.worker import CollectionWorker


@pytest.fixture
def tech(db, settings):
    google = FakeGoogle()
    http = FixtureHTTP({URL: PublicResponse(URL, 200, rss(), "application/rss+xml")})
    core = CollectionCore(http, FeedContract(20, 3))
    app = create_app(
        settings, db, google, clock=lambda: datetime(2026, 11, 27, tzinfo=UTC), collection_core=core
    )
    with TestClient(app, base_url=settings.app_origin, follow_redirects=False) as client:
        yield client, google, http


def signin(tech):
    client, google, _ = tech
    login(client, google)
    return client.get("/api/v1/session").json()["data"]["csrfToken"]


def headers(settings, csrf, version=None):
    result = {"Origin": settings.app_origin, "X-CSRF-Token": csrf}
    if version is not None:
        result["If-Match"] = f'"{version}"'
    return result


def test_new_routes_are_owner_only_and_resolve_requires_csrf(tech, settings):
    client, _, http = tech
    assert client.get("/api/v1/tech/sources").status_code == 401
    assert client.get("/api/v1/tech/articles").status_code == 401
    csrf = signin(tech)
    assert client.post("/api/v1/tech/sources/resolve", json={"inputUrl": URL}).status_code == 403
    assert not http.calls
    response = client.post(
        "/api/v1/tech/sources/resolve", json={"inputUrl": URL}, headers=headers(settings, csrf)
    )
    assert response.status_code == 200 and response.json()["data"]["options"]


def test_subscription_api_contract_duplicate_versions_delete_and_readd(tech, settings, db):
    client, _, _ = tech
    csrf = signin(tech)
    payload = {"inputUrl": URL, "collectionUrl": URL}
    response = client.post("/api/v1/tech/sources", json=payload, headers=headers(settings, csrf))
    assert response.status_code == 202
    data = response.json()["data"]
    source, job_id = data["source"], data["jobId"]
    assert source["initializationState"] == "pending"
    status = client.get("/api/v1/jobs/" + job_id).json()["data"]
    assert status["state"] == "queued" and "input" not in status
    duplicate = client.post("/api/v1/tech/sources", json=payload, headers=headers(settings, csrf))
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["fields"]["existingSourceId"] == source["id"]
    path = "/api/v1/tech/sources/" + source["id"]
    assert (
        client.patch(path, json={"enabled": False}, headers=headers(settings, csrf)).status_code
        == 428
    )
    assert (
        client.patch(path, json={"enabled": False}, headers=headers(settings, csrf, 99)).status_code
        == 412
    )
    paused = client.patch(path, json={"enabled": False}, headers=headers(settings, csrf, 1))
    assert paused.status_code == 200 and not paused.json()["data"]["source"]["enabled"]
    assert client.delete(path, headers=headers(settings, csrf, 2)).status_code == 200
    assert client.get("/api/v1/tech/sources").json()["data"]["items"] == []
    restored = client.post("/api/v1/tech/sources", json=payload, headers=headers(settings, csrf))
    assert restored.status_code == 202 and restored.json()["data"]["source"]["id"] == source["id"]
    assert client.get("/api/v1/jobs/" + str(uuid4())).status_code == 404


@pytest.mark.parametrize("payload", [{}, {"inputUrl": 10}, {"inputUrl": URL, "adapter": "execute"}])
def test_unknown_or_invalid_resolve_fields_are_rejected_without_fetch(tech, settings, payload):
    client, _, http = tech
    csrf = signin(tech)
    response = client.post(
        "/api/v1/tech/sources/resolve", json=payload, headers=headers(settings, csrf)
    )
    assert response.status_code == 400 and not http.calls


def test_resolve_rate_limit_is_shared_with_registration(tech, settings):
    client, _, http = tech
    csrf = signin(tech)
    for _ in range(5):
        assert (
            client.post(
                "/api/v1/tech/sources/resolve",
                json={"inputUrl": URL},
                headers=headers(settings, csrf),
            ).status_code
            == 200
        )
    result = client.post(
        "/api/v1/tech/sources",
        json={"inputUrl": URL, "collectionUrl": URL},
        headers=headers(settings, csrf),
    )
    assert result.status_code == 429 and int(result.headers["retry-after"]) > 0
    assert len(http.calls) == 5


@pytest.mark.asyncio
async def test_reading_filters_keyset_cursor_and_manual_states(tech, settings, db):
    client, _, _ = tech
    csrf = signin(tech)
    owner = rows(db, "SELECT id FROM owner_settings")[0]["id"]
    store = CollectionStore(db)
    source, _ = add(store, owner)
    assert (
        await CollectionWorker(
            store, Core(rss(item("a", "100% title"), item("b"), item("c")))
        ).run_next(owner)
        == "success"
    )
    response = client.get("/api/v1/tech/articles?limit=2")
    assert response.status_code == 200
    page = response.json()
    assert len(page["data"]["items"]) == 2 and page["meta"]["hasMore"]
    cursor = page["meta"]["nextCursor"]
    next_page = client.get("/api/v1/tech/articles", params={"limit": 2, "cursor": cursor}).json()
    assert len(next_page["data"]["items"]) == 1
    assert not (
        {a["id"] for a in page["data"]["items"]} & {a["id"] for a in next_page["data"]["items"]}
    )
    assert (
        client.get("/api/v1/tech/articles", params={"limit": 3, "cursor": cursor}).status_code
        == 400
    )
    assert client.get("/api/v1/tech/articles", params={"cursor": "bad"}).status_code == 400
    assert client.get("/api/v1/tech/articles", params={"read": "bad"}).status_code == 400
    assert len(client.get("/api/v1/tech/articles", params={"q": "%"}).json()["data"]["items"]) == 1
    article = page["data"]["items"][0]
    path = "/api/v1/tech/articles/" + article["id"] + "/state"
    changed = client.patch(
        path,
        json={"isRead": True, "isSaved": True, "isHidden": True},
        headers=headers(settings, csrf, article["state"]["version"]),
    )
    assert changed.status_code == 200
    state = changed.json()["data"]
    assert state["isRead"] and state["isSaved"] and state["isHidden"]
    assert len(client.get("/api/v1/tech/articles").json()["data"]["items"]) == 2
    assert (
        len(
            client.get("/api/v1/tech/articles", params={"view": "saved", "hidden": "only"}).json()[
                "data"
            ]["items"]
        )
        == 1
    )
    restored = client.patch(
        path, json={"isHidden": False}, headers=headers(settings, csrf, state["version"])
    )
    assert restored.json()["data"]["isSaved"] and not restored.json()["data"]["isHidden"]
    assert (
        client.patch(path, json={"isRead": False}, headers=headers(settings, csrf, 1)).status_code
        == 412
    )
    assert (
        client.patch(
            path, json={"title": "overwrite"}, headers=headers(settings, csrf, 3)
        ).status_code
        == 400
    )
    store.change_source(owner, source["id"], 1, delete=True)
    assert len(client.get("/api/v1/tech/articles").json()["data"]["items"]) == 3
    assert all(
        row["notification_state"] == "baseline" for row in rows(db, "SELECT * FROM articles")
    )


def test_cursors_are_owner_scoped_and_integrity_checked(db):
    reading = ReadingStore(db, "test-secret")
    owner = uuid4()
    cursor = reading.cursors.encode(owner, {"q": "a"}, ["position"])
    with pytest.raises(Exception, match="INVALID_CURSOR"):
        reading.cursors.decode(cursor, uuid4(), {"q": "a"})
    with pytest.raises(Exception, match="INVALID_CURSOR"):
        reading.cursors.decode(cursor[:-2] + "xx", owner, {"q": "a"})
