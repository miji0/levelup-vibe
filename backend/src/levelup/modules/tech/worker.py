"""One finite collection job; scheduling and authenticated API routing are separate."""

import asyncio
from contextlib import suppress
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from levelup.infra.public_http import CollectionError
from levelup.modules.tech.collection import CollectionCore
from levelup.modules.tech.ingestion import apply_collection, begin_attempt
from levelup.modules.tech.persistence import SOURCE_LOCK, CollectionStore, Lease, locked_connection


class CollectionWorker:
    def __init__(self, store: CollectionStore, core: CollectionCore) -> None:
        self.store = store
        self.core = core

    async def _heartbeat(self, lease: Lease, lost: asyncio.Event) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                renewed = self.store.heartbeat(lease)
            except DBAPIError:
                renewed = False
            if not renewed:
                lost.set()
                return

    async def run(self, lease: Lease) -> str:
        try:
            with locked_connection(self.store.engine, SOURCE_LOCK, lease.source_id) as conn:
                attempt = begin_attempt(conn, lease)
                if attempt is None:
                    return "skipped"
                lost = asyncio.Event()
                heartbeat = asyncio.create_task(self._heartbeat(lease, lost))
                try:
                    try:
                        response, feed = await self.core.collect(
                            attempt.source["collection_url"],
                            baseline=attempt.baseline,
                            has_open_issues=attempt.has_open_issues,
                            etag=attempt.source["etag"],
                            last_modified=attempt.source["last_modified"],
                        )
                        if lost.is_set():
                            raise CollectionError("STALE_JOB")
                    except CollectionError as exc:
                        if exc.code == "STALE_JOB":
                            raise
                        return apply_collection(conn, lease, attempt, error_code=exc.code)
                    try:
                        return apply_collection(conn, lease, attempt, response, feed)
                    except DBAPIError as exc:
                        if getattr(exc.orig, "sqlstate", None) in ("55P03", "57014"):
                            raise CollectionError("RESOURCE_BUSY") from None
                        if exc.connection_invalidated:
                            raise CollectionError("DATABASE_UNAVAILABLE") from None
                        return apply_collection(conn, lease, attempt, error_code="STORE_FAILURE")
                finally:
                    heartbeat.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat
        except CollectionError as exc:
            if exc.code == "STALE_JOB":
                return "stale"
            if exc.code == "RESOURCE_BUSY":
                with self.store.engine.begin() as conn:
                    conn.execute(
                        text("""UPDATE job_runs SET state='queued',lease_token=NULL,
                        lease_expires_at=NULL,available_at=clock_timestamp()+interval '30 seconds',
                        result_code='RESOURCE_BUSY' WHERE id=:id AND owner_id=:owner
                        AND state='running' AND lease_token=:token
                        AND lease_expires_at>clock_timestamp()"""),
                        {"id": lease.id, "owner": lease.owner_id, "token": lease.token},
                    )
                return "busy"
            raise

    async def run_next(self, owner_id: UUID) -> str | None:
        lease = self.store.claim(owner_id)
        return None if lease is None else await self.run(lease)
