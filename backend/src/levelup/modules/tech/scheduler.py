"""Finite scheduled invocation. No startup workers or work after the response."""

import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import text

from levelup.infra.public_http import CollectionError
from levelup.modules.tech.digests import KST
from levelup.modules.tech.mail import MailService
from levelup.modules.tech.persistence import CollectionStore
from levelup.modules.tech.worker import CollectionWorker


async def tick(
    engine, settings, core, transport, scheduled: datetime, at: datetime, kind: str, clock=None
):
    local = scheduled.astimezone(KST)
    actual = at.astimezone(KST)
    # Never turn a stale catch-up delivery into a new day's regular email.
    if scheduled > at + timedelta(seconds=30) or at - scheduled > timedelta(hours=2):
        raise CollectionError("INVALID_REQUEST")
    with engine.connect() as conn:
        owner = conn.execute(text("SELECT id FROM owner_settings")).scalar_one()
    store = CollectionStore(engine)
    mail = MailService(engine, settings, transport, clock)
    worker = CollectionWorker(store, core)
    start = time.monotonic()
    if kind in ("hourly", "final"):
        slot = local.strftime("%Y-%m-%dT%H") if kind == "hourly" else local.date().isoformat()
        for source in store.list_sources(owner):
            if source["status"] == "active":
                try:
                    store.enqueue(owner, source["id"], slot, final=kind == "final")
                except CollectionError as exc:
                    if exc.code not in ("SOURCE_INACTIVE", "NOT_FOUND"):
                        raise
    if kind == "digest":
        mail.enqueue_digest(owner, local.date())
    elif actual.hour >= 8:
        # Repair missing starts as missed, never send a new late snapshot.
        mail.enqueue_digest(owner, actual.date())
    # Mail has a separate slot and starts before potentially slow collection.
    mail_result = await mail.run_next(owner)
    results: list[str | None | BaseException] = []
    while time.monotonic() - start < 210:
        try:
            async with asyncio.timeout(max(0.1, 240 - (time.monotonic() - start))):
                batch = await asyncio.gather(
                    worker.run_next(owner), worker.run_next(owner), return_exceptions=True
                )
        except TimeoutError:
            results.append("deferred")
            break
        results.extend("failed" if isinstance(v, Exception) else v for v in batch if v is not None)
        if all(v is None for v in batch):
            break
        if any(isinstance(v, Exception) or v == "busy" for v in batch):
            break
    return {"collectionResults": results, "mailResult": mail_result}
