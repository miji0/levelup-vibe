from datetime import timedelta
from pathlib import Path

import pytest
from conftest import login
from sqlalchemy import text

from levelup.api.app import BINDING, SESSION
from levelup.core.security import digest
from levelup.infra.db import ensure_owner
from levelup.migrate import migrate


def test_owner_login_database_session_and_private_home(auth, db):
    client, provider, _ = auth
    assert client.get("/api/v1/home").status_code == 401
    response = login(client, provider, "/settings")
    assert response.status_code == 303
    assert response.headers["location"] == "/settings"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    session = client.get("/api/v1/session")
    assert session.json()["data"]["owner"]["email"] == "owner@example.com"
    assert session.headers["cache-control"] == "private, no-store"
    home = client.get("/api/v1/home").json()["data"]
    assert len(home["homeCards"]) == 3
    assert all(c["path"] is None for c in home["homeCards"][1:])
    assert home["tech"]["count"] is None
    assert "reports" in [s["id"] for s in home["sections"]]
    with db.connect() as conn:
        row = conn.execute(text("SELECT * FROM auth_sessions")).mappings().one()
        assert row["token_hash"] == digest(client.cookies[SESSION])
        assert client.cookies[SESSION] not in str(row)
        gmail = conn.execute(text("SELECT * FROM gmail_connections")).mappings().one()
        assert gmail["state"] == "connected"
        assert b"test-refresh-secret" not in bytes(gmail["refresh_token_ciphertext"])
        assert (
            conn.execute(text("SELECT notifications_enabled FROM owner_settings")).scalar() is False
        )


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "intruder"},
        {"email_verified": False},
        {"email_verified": "true"},
        {"email": ""},
    ],
)
def test_rejects_nonowner_or_unverified_email(auth, db, claims):
    client, provider, _ = auth
    provider.claims.update(claims)
    assert login(client, provider).status_code == 403
    assert client.get("/api/v1/session").status_code == 401
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM auth_sessions")).scalar() == 0


def test_fixed_seven_day_expiry(auth):
    client, provider, instant = auth
    login(client, provider)
    instant[0] += timedelta(days=7, microseconds=-1)
    assert client.get("/api/v1/session").status_code == 200
    instant[0] += timedelta(microseconds=1)
    assert client.get("/api/v1/session").status_code == 401


def test_current_session_logout_requires_csrf_and_preserves_gmail(auth, db):
    client, provider, _ = auth
    login(client, provider)
    first = client.cookies[SESSION]
    login(client, provider)
    current = client.cookies[SESSION]
    csrf = client.get("/api/v1/session").json()["data"]["csrfToken"]
    assert client.post("/api/auth/signout").status_code == 403
    assert (
        client.post(
            "/api/auth/signout", headers={"Origin": "https://evil.test", "X-CSRF-Token": csrf}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/signout", headers={"Origin": "https://testserver", "X-CSRF-Token": csrf}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/session").status_code == 401
    client.cookies.set(SESSION, current)
    assert client.get("/api/v1/session").status_code == 401
    client.cookies.set(SESSION, first)
    assert client.get("/api/v1/session").status_code == 200
    with db.connect() as conn:
        assert conn.execute(text("SELECT state FROM gmail_connections")).scalar() == "connected"


def test_state_binding_replay_and_expiry(auth):
    client, provider, instant = auth
    client.get("/api/auth/signin")
    state, binding = provider.state, client.cookies[BINDING]
    client.cookies.clear()
    params = {"state": state, "code": "valid"}
    assert client.get("/api/auth/callback/google", params=params).status_code == 400
    client.cookies.set(BINDING, binding)
    assert client.get("/api/auth/callback/google", params=params).status_code == 303
    client.cookies.set(BINDING, binding)
    assert client.get("/api/auth/callback/google", params=params).status_code == 400
    assert provider.exchanges == 1
    client.get("/api/auth/signin")
    instant[0] += timedelta(minutes=10)
    assert (
        client.get(
            "/api/auth/callback/google", params={"state": provider.state, "code": "valid"}
        ).status_code
        == 400
    )


def test_invalid_code_and_cancel_consume_state_without_session(auth):
    client, provider, _ = auth
    for extra in [{"code": "invalid"}, {"error": "access_denied"}]:
        client.get("/api/auth/signin")
        response = client.get(
            "/api/auth/callback/google", params={"state": provider.state, **extra}
        )
        assert response.status_code == 400
        assert "secret must not" not in response.text
        assert "requestId" in response.json()["error"]
    assert client.get("/api/v1/session").status_code == 401


def test_later_login_does_not_restore_disconnected_gmail(auth, db):
    client, provider, _ = auth
    provider.scope = "openid email"
    login(client, provider)
    assert provider.first is True
    provider.scope += " https://www.googleapis.com/auth/gmail.send"
    login(client, provider)
    assert provider.first is False
    with db.connect() as conn:
        assert conn.execute(text("SELECT state FROM gmail_connections")).scalar() == "disconnected"


def test_changed_email_requires_reauth(auth, db):
    client, provider, _ = auth
    login(client, provider)
    provider.claims["email"] = "new@example.com"
    login(client, provider)
    assert client.get("/api/v1/session").json()["data"]["owner"]["email"] == "new@example.com"
    with db.connect() as conn:
        assert (
            conn.execute(text("SELECT state FROM gmail_connections")).scalar() == "reauth_required"
        )


def test_migrations_repeat_and_owner_cannot_be_replaced(db, settings):
    with db.connect() as conn:
        applied_before = dict(
            conn.execute(text("SELECT name, checksum FROM schema_migrations")).all()
        )
    migrate(db, Path(__file__).resolve().parents[2] / "db" / "migrations")
    settings.owner_google_sub = "different-owner"
    with pytest.raises(ValueError, match="refusing replacement"):
        ensure_owner(db, settings)
    with db.connect() as conn:
        assert (
            dict(conn.execute(text("SELECT name, checksum FROM schema_migrations")).all())
            == applied_before
        )


@pytest.mark.parametrize("failure", ["owner", "cancel", "invalid", "state"])
def test_browser_oauth_errors_redirect_to_safe_recovery(auth, failure):
    client, provider, _ = auth
    client.get("/api/auth/signin")
    params = {"state": provider.state, "code": "valid"}
    expected = "OWNER_ONLY"
    if failure == "owner":
        provider.claims["sub"] = "intruder"
    elif failure == "cancel":
        params["error"] = "access_denied"
        expected = "OAUTH_CANCELLED"
    elif failure == "invalid":
        params["code"] = "invalid"
        expected = "OAUTH_INVALID"
    else:
        params["state"] = "invalid-state"
        expected = "OAUTH_STATE_INVALID"
    response = client.get(
        "/api/auth/callback/google", params=params, headers={"Accept": "text/html"}
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=" + expected
    assert "code=" not in response.headers["location"]
    assert BINDING not in client.cookies
    assert client.get("/api/v1/session").status_code == 401
