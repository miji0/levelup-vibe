import base64
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from levelup.api.app import create_app
from levelup.core.config import Settings
from levelup.infra.db import ensure_owner
from levelup.infra.google import GMAIL_SCOPE
from levelup.migrate import migrate


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        app_origin="https://testserver",
        database_url="postgresql+psycopg://unused/test",
        owner_google_sub="owner-123",
        owner_email="owner@example.com",
        google_client_id="test-client",
        google_client_secret="test-secret",
        token_encryption_key=base64.urlsafe_b64encode(bytes(range(32))).decode(),
    )


@pytest.fixture
def db(settings):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL database")
    admin = create_engine(url, poolclass=NullPool)
    schema = "test_" + uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, poolclass=NullPool, connect_args={"options": "-csearch_path=" + schema}
    )
    migrate(engine, Path(__file__).resolve().parents[2] / "db" / "migrations")
    ensure_owner(engine, settings)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


class FakeGoogle:
    def __init__(self):
        self.claims = {"sub": "owner-123", "email": "owner@example.com", "email_verified": True}
        self.scope = "openid email " + GMAIL_SCOPE
        self.refresh = "test-refresh-secret"
        self.exchanges = 0
        self.first = None
        self.state = ""

    async def authorize(self, state, nonce, verifier, first):
        self.state, self.first = state, first
        return "https://accounts.google.com/o/oauth2/v2/auth?state=" + state

    async def exchange(self, code, verifier, nonce):
        self.exchanges += 1
        if code == "invalid":
            raise ValueError("secret must not be exposed")
        return {"claims": self.claims, "scope": self.scope, "refresh_token": self.refresh}


@pytest.fixture
def auth(db, settings):
    provider = FakeGoogle()
    instant = [datetime(2026, 11, 26, 0, 0, tzinfo=UTC)]
    app = create_app(settings, db, provider, clock=lambda: instant[0])
    with TestClient(app, base_url=settings.app_origin, follow_redirects=False) as client:
        yield client, provider, instant


def login(client, provider, return_to="/"):
    response = client.get("/api/auth/signin", params={"returnTo": return_to})
    assert response.status_code == 303
    return client.get(
        "/api/auth/callback/google", params={"code": "valid", "state": provider.state}
    )
