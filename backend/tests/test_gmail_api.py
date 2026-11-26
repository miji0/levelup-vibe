from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import FakeGoogle, login
from fastapi.testclient import TestClient
from test_collection_store import rows
from test_tech_api import headers

from levelup.api.app import create_app


class ConnectGoogle(FakeGoogle):
    async def connect_authorize(self, state, nonce, verifier, subject):
        assert subject == "owner-123"
        self.connect_state = state
        return "https://accounts.google.com/o/oauth2/v2/auth?state=" + state

    async def connect_exchange(self, code, verifier, nonce):
        return await self.exchange(code, verifier, nonce)


class Revocation:
    def __init__(self):
        self.tokens = []

    async def revoke(self, token):
        self.tokens.append(token)
        return False


@pytest.fixture
def connected(db, settings):
    google = ConnectGoogle()
    transport = Revocation()
    app = create_app(
        settings,
        db,
        google,
        clock=lambda: datetime(2026, 11, 27, tzinfo=UTC),
        gmail_transport=transport,
    )
    with TestClient(app, base_url=settings.app_origin, follow_redirects=False) as client:
        login(client, google)
        csrf = client.get("/api/v1/session").json()["data"]["csrfToken"]
        yield client, google, transport, headers(settings, csrf)


def start(client, h):
    response = client.post("/api/v1/integrations/gmail/connect", json={}, headers=h)
    assert response.status_code == 200


def test_connect_one_use_same_owner_and_refusal_preserves_old(connected, db):
    client, g, _, h = connected
    start(client, h)
    g.claims["sub"] = "intruder"

    def callback():
        return client.get(
            "/api/v1/integrations/gmail/callback", params={"state": g.connect_state, "code": "ok"}
        )

    assert callback().headers["location"] == "/settings?gmail=error"
    assert (
        rows(db, "SELECT google_subject FROM gmail_connections")[0]["google_subject"] == "owner-123"
    )
    g.claims["sub"] = "owner-123"
    assert callback().headers["location"] == "/settings?gmail=error"
    start(client, h)
    version = rows(db, "SELECT version FROM gmail_connections")[0]["version"]
    assert (
        client.get(
            "/api/v1/integrations/gmail/callback",
            params={"state": g.connect_state, "error": "access_denied"},
        ).status_code
        == 303
    )
    assert rows(db, "SELECT version FROM gmail_connections")[0]["version"] == version
    start(client, h)
    assert callback().headers["location"] == "/settings?gmail=connected"
    assert rows(db, "SELECT version FROM gmail_connections")[0]["version"] == version + 1


def test_disconnect_local_first_version_and_regular_login_no_revival(connected, db):
    client, g, t, h = connected
    path = "/api/v1/integrations/gmail"
    assert client.delete(path, headers=h).status_code == 428
    version = client.get("/api/v1/settings").json()["data"]["gmail"]["version"]
    h["If-Match"] = f'"{version}"'
    result = client.delete(path, headers=h)
    assert result.status_code == 200 and result.json()["data"]["remoteRevocation"] == "unconfirmed"
    assert t.tokens == ["test-refresh-secret"]
    row = rows(db, "SELECT * FROM gmail_connections")[0]
    assert row["refresh_token_ciphertext"] is None and row["state"] == "disconnected"
    assert client.delete(path, headers=h).status_code == 412
    login(client, g)
    assert rows(db, "SELECT state FROM gmail_connections")[0]["state"] == "disconnected"


def test_testmail_key_duplicate_and_settings_explicit_bool(connected, db):
    client, _, _, h = connected
    h["Idempotency-Key"] = str(uuid4())
    first = client.post("/api/v1/tech/test-emails", json={}, headers=h)
    again = client.post("/api/v1/tech/test-emails", json={}, headers=h)
    assert first.status_code == 202 and first.json() == again.json()
    assert len(rows(db, "SELECT * FROM job_runs WHERE kind='test_email'")) == 1
    v = client.get("/api/v1/settings").json()["data"]["version"]
    h["If-Match"] = f'"{v}"'
    assert (
        client.patch(
            "/api/v1/settings", json={"notificationsEnabled": "false"}, headers=h
        ).status_code
        == 400
    )
    assert (
        client.patch("/api/v1/settings", json={"notificationsEnabled": True}, headers=h).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/v1/settings", json={"notificationsEnabled": False}, headers=h
        ).status_code
        == 412
    )


def test_callback_bound_to_current_login_session(connected):
    client, g, _, h = connected
    start(client, h)
    state = g.connect_state
    login(client, g)
    result = client.get(
        "/api/v1/integrations/gmail/callback", params={"state": state, "code": "ok"}
    )
    assert result.headers["location"] == "/settings?gmail=error"
