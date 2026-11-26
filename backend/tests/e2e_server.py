"""Test-only provider injection. Never imported by the production entrypoint."""

import base64
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from levelup.api.app import create_app
from levelup.core.config import Settings
from levelup.infra.db import ensure_owner
from levelup.infra.public_http import PublicResponse
from levelup.migrate import migrate
from levelup.modules.tech.collection import CollectionCore, FeedContract
from levelup.modules.tech.persistence import CollectionStore
from levelup.modules.tech.worker import CollectionWorker

url = os.environ["TEST_DATABASE_URL"]
admin = create_engine(url, poolclass=NullPool)
schema = "e2e_" + uuid4().hex
with admin.begin() as connection:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
engine = create_engine(url, poolclass=NullPool, connect_args={"options": "-csearch_path=" + schema})
settings = Settings(
    _env_file=None,
    app_origin=os.environ.get("E2E_APP_ORIGIN", "http://localhost:3000"),
    database_url=url,
    owner_google_sub="e2e-owner",
    owner_email="owner@example.com",
    google_client_id="test",
    google_client_secret="test",
    token_encryption_key=base64.urlsafe_b64encode(bytes(range(32))).decode(),
)
migrate(engine, Path(__file__).resolve().parents[2] / "db" / "migrations")
ensure_owner(engine, settings)


class BrowserGoogle:
    async def authorize(self, state, nonce, verifier, first):
        return settings.app_origin + "/api/auth/callback/google?code=test&state=" + state

    async def exchange(self, code, verifier, nonce):
        return {
            "claims": {
                "sub": settings.owner_google_sub,
                "email": settings.owner_email,
                "email_verified": True,
            },
            "scope": "openid email",
        }


@asynccontextmanager
async def lifespan(app):
    yield
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


# Public-source fixtures and finite worker control exist only in this test entrypoint.

FIXTURE_URL = "https://example.com/feed.xml"
BASE = b'<rss version="2.0"><channel><title>Fixture Tech</title>{}</channel></rss>'


class BrowserHTTP:
    body = BASE.replace(b"{}", b"")

    async def check_url(self, url):
        if not url.startswith("https://example.com/"):
            raise ValueError("Only fixture host allowed")
        return url, ("93.184.216.34",)

    async def fetch(self, url, **kwargs):
        await self.check_url(url)
        return PublicResponse(url, 200, self.body, "application/rss+xml")


fixture_http = BrowserHTTP()
app = create_app(
    settings,
    engine,
    BrowserGoogle(),
    collection_core=CollectionCore(fixture_http, FeedContract(1000, 16)),
)
app.router.lifespan_context = lifespan


@app.post("/api/__test/collect")
async def collect_fixture():
    store = CollectionStore(engine)
    with engine.connect() as conn:
        owner = conn.execute(text("SELECT id FROM owner_settings")).scalar_one()
    worker = CollectionWorker(store, CollectionCore(fixture_http, FeedContract(1000, 16)))
    fixture_http.body = BASE.replace(b"{}", b"")
    for _ in range(10):
        if await worker.run_next(owner) is None:
            break
    fixture_http.body = BASE.replace(
        b"{}",
        b"<item><guid>fixture-1</guid><title>Fixture engineering article</title>"
        b"<link>https://example.com/article</link>"
        b"<description>Public article introduction</description></item>"
        b"<item><guid>fixture-2</guid><title>Fixture event</title>"
        b"<link>https://example.com/event</link></item>",
    )
    for source in store.list_sources(owner):
        if source["status"] == "active":
            store.enqueue(owner, source["id"], "e2e-" + uuid4().hex)
    for _ in range(10):
        if await worker.run_next(owner) is None:
            break
    return {"data": {"done": True}}
