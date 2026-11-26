"""Owner-scoped subscriptions and fenced collection leases on a direct PostgreSQL connection."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import DBAPIError

from levelup.core.security import digest
from levelup.infra.public_http import CollectionError, normalize_url
from levelup.modules.tech.collection import CollectionCore, FeedOption

OWNER_LOCK = 41082401
SOURCE_LOCK = 41082402
SLOT_LOCK = 41082403
LEASE_SECONDS = 120


def lock_key(value: UUID) -> int:
    return int.from_bytes(value.bytes[:4], "big", signed=True)


@contextmanager
def locked_connection(engine: Engine, namespace: int, value: UUID) -> Iterator[Connection]:
    with engine.connect() as conn:
        acquired = False
        deadline = time.monotonic() + 2
        try:
            while not acquired:
                acquired = bool(
                    conn.execute(
                        text("SELECT pg_try_advisory_lock(:ns, :key)"),
                        {"ns": namespace, "key": lock_key(value)},
                    ).scalar_one()
                )
                conn.commit()
                if not acquired:
                    if time.monotonic() >= deadline:
                        raise CollectionError("RESOURCE_BUSY")
                    time.sleep(0.025)
            yield conn
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) in ("55P03", "57014"):
                raise CollectionError("RESOURCE_BUSY") from None
            raise
        finally:
            if conn.in_transaction():
                conn.rollback()
            if acquired:
                try:
                    unlocked = conn.execute(
                        text("SELECT pg_advisory_unlock(:ns, :key)"),
                        {"ns": namespace, "key": lock_key(value)},
                    ).scalar_one()
                    conn.commit()
                    if not unlocked:
                        conn.invalidate()
                except DBAPIError:
                    conn.invalidate()


def now(conn: Connection) -> datetime:
    return conn.execute(text("SELECT clock_timestamp()")).scalar_one()


def prepare_transaction(conn: Connection) -> None:
    conn.execute(text("SET LOCAL lock_timeout = '2s'"))


@dataclass(frozen=True)
class Lease:
    id: UUID
    owner_id: UUID
    source_id: UUID
    generation: int
    token: UUID


class SourceAlreadyExists(CollectionError):
    def __init__(self, source_id: UUID):
        super().__init__("SOURCE_ALREADY_EXISTS")
        self.existing_source_id = source_id


class CollectionStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_sources(self, owner_id: UUID) -> list[RowMapping]:
        with self.engine.connect() as conn:
            return list(
                conn.execute(
                    text("""
                SELECT s.*, (SELECT count(*) FROM collection_entry_issues i
                    WHERE i.source_id=s.id AND i.state='open') AS open_issue_count
                FROM sources s WHERE owner_id=:owner AND status<>'deleted' ORDER BY created_at, id
            """),
                    {"owner": owner_id},
                ).mappings()
            )

    def add_source(
        self, owner_id: UUID, input_url: str, option: FeedOption
    ) -> tuple[RowMapping, UUID]:
        input_url = normalize_url(input_url)
        collection_url = normalize_url(option.collection_url)
        with locked_connection(self.engine, OWNER_LOCK, owner_id) as conn, conn.begin():
            prepare_transaction(conn)
            if not conn.execute(
                text("SELECT 1 FROM owner_settings WHERE id=:id"), {"id": owner_id}
            ).scalar_one_or_none():
                raise CollectionError("NOT_FOUND")
            existing = (
                conn.execute(
                    text("""SELECT * FROM sources
                WHERE owner_id=:owner AND collection_url_hash=:hash FOR UPDATE"""),
                    {"owner": owner_id, "hash": digest(collection_url)},
                )
                .mappings()
                .one_or_none()
            )
            instant = now(conn)
            if existing is not None:
                if existing["collection_url"] != collection_url:
                    raise CollectionError("IDENTITY_CONFLICT")
                if existing["status"] != "deleted":
                    raise SourceAlreadyExists(existing["id"])
                source_id = existing["id"]
                conn.execute(
                    text("""UPDATE sources SET name=:name, input_url=:input,
                    collector_type=:type, adapter_key=:adapter, status='active', deleted_at=NULL,
                    generation=generation+1, version=version+1, initialization_state='pending',
                    etag=NULL, last_modified=NULL, updated_at=:now WHERE id=:id"""),
                    {
                        "id": source_id,
                        "name": option.name,
                        "input": input_url,
                        "type": option.collector_type,
                        "adapter": option.adapter_key,
                        "now": instant,
                    },
                )
                reason = "readd"
            else:
                source_id = uuid4()
                conn.execute(
                    text("""INSERT INTO sources(id, owner_id, name, input_url,
                    collection_url, collection_url_hash, collector_type, adapter_key,
                    created_at, updated_at)
                    VALUES (:id,:owner,:name,:input,:url,:hash,:type,:adapter,:now,:now)"""),
                    {
                        "id": source_id,
                        "owner": owner_id,
                        "name": option.name,
                        "input": input_url,
                        "url": collection_url,
                        "hash": digest(collection_url),
                        "type": option.collector_type,
                        "adapter": option.adapter_key,
                        "now": instant,
                    },
                )
                reason = "first_add"
            source = self._source(conn, owner_id, source_id)
            job = self._start_epoch(conn, source, reason, instant)
            return source, job

    @staticmethod
    def _source(conn: Connection, owner_id: UUID, source_id: UUID) -> RowMapping:
        row = (
            conn.execute(
                text("SELECT * FROM sources WHERE id=:id AND owner_id=:owner FOR UPDATE"),
                {"id": source_id, "owner": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise CollectionError("NOT_FOUND")
        return row

    @staticmethod
    def _start_epoch(conn: Connection, source: RowMapping, reason: str, instant: datetime) -> UUID:
        conn.execute(
            text("""INSERT INTO subscription_epochs(id,source_id,generation,started_at,reason)
            VALUES (:id,:source,:gen,:now,:reason)"""),
            {
                "id": uuid4(),
                "source": source["id"],
                "gen": source["generation"],
                "now": instant,
                "reason": reason,
            },
        )
        return CollectionStore._enqueue(
            conn, source, "baseline", f"baseline/{source['id']}/{source['generation']}", instant
        )

    @staticmethod
    def _enqueue(
        conn: Connection, source: RowMapping, kind: str, key: str, available_at: datetime
    ) -> UUID:
        row = conn.execute(
            text("""INSERT INTO job_runs(id,owner_id,kind,source_id,
            source_generation,dedup_key,available_at)
            VALUES (:id,:owner,:kind,:source,:gen,:key,:at)
            ON CONFLICT (dedup_key) DO NOTHING RETURNING id"""),
            {
                "id": uuid4(),
                "owner": source["owner_id"],
                "kind": kind,
                "source": source["id"],
                "gen": source["generation"],
                "key": key,
                "at": available_at,
            },
        ).scalar_one_or_none()
        if row is not None:
            return row
        existing = (
            conn.execute(text("SELECT * FROM job_runs WHERE dedup_key=:key"), {"key": key})
            .mappings()
            .one()
        )
        if (existing["source_id"], existing["source_generation"], existing["kind"]) != (
            source["id"],
            source["generation"],
            kind,
        ):
            raise CollectionError("IDENTITY_CONFLICT")
        return existing["id"]

    def enqueue(self, owner_id: UUID, source_id: UUID, slot: str, *, final: bool = False) -> UUID:
        with self.engine.begin() as conn:
            prepare_transaction(conn)
            source = self._source(conn, owner_id, source_id)
            if source["status"] != "active":
                raise CollectionError("SOURCE_INACTIVE")
            kind = "collect_final" if final else "collect"
            return self._enqueue(
                conn, source, kind, f"{kind}/{source_id}/{source['generation']}/{slot}", now(conn)
            )

    def change_source(
        self,
        owner_id: UUID,
        source_id: UUID,
        version: int,
        *,
        enabled: bool | None = None,
        delete: bool = False,
    ) -> tuple[RowMapping, UUID | None]:
        if (enabled is None) == (not delete):
            raise ValueError("Choose enabled or delete")
        with locked_connection(self.engine, OWNER_LOCK, owner_id) as conn, conn.begin():
            prepare_transaction(conn)
            source = self._source(conn, owner_id, source_id)
            if source["status"] == "deleted":
                if delete:
                    return source, None
                raise CollectionError("NOT_FOUND")
            if source["version"] != version:
                raise CollectionError("VERSION_CONFLICT")
            target = "deleted" if delete else "active" if enabled else "paused"
            if source["status"] == target:
                return source, None
            instant = now(conn)
            conn.execute(
                text(
                    "UPDATE subscription_epochs SET ended_at=:now "
                    "WHERE source_id=:id AND ended_at IS NULL"
                ),
                {"id": source_id, "now": instant},
            )
            if target != "active":
                self._suppress(conn, source_id, "source_deleted" if delete else "source_disabled")
            conn.execute(
                text("""UPDATE sources SET status=:status, generation=generation+1,
                version=version+1, updated_at=:now, deleted_at=:deleted,
                initialization_state=CASE WHEN :status='active' THEN 'pending'
                    WHEN initialization_state='running' THEN 'pending'
                    ELSE initialization_state END,
                etag=NULL,last_modified=NULL WHERE id=:id"""),
                {
                    "id": source_id,
                    "status": target,
                    "now": instant,
                    "deleted": instant if delete else None,
                },
            )
            source = self._source(conn, owner_id, source_id)
            job = self._start_epoch(conn, source, "resume", instant) if enabled else None
            return source, job

    @staticmethod
    def _suppress(conn: Connection, source_id: UUID, reason: str) -> None:
        # The source row fences collection; lock articles before touching snapshots/messages.
        conn.execute(
            text("SELECT id FROM articles WHERE source_id=:id ORDER BY id FOR UPDATE"),
            {"id": source_id},
        ).all()
        params = {"id": source_id, "reason": reason}
        conn.execute(
            text("""UPDATE deliveries d SET state='cancelled',
            last_error_code='SUBSCRIPTION_CHANGED', finished_at=clock_timestamp()
            WHERE d.state='prepared' AND d.submitted_at IS NULL AND EXISTS (
                SELECT 1 FROM digest_items i JOIN articles a ON a.id=i.article_id
                WHERE i.digest_id=d.digest_id AND a.source_id=:id AND i.exclusion_reason IS NULL)
            AND NOT EXISTS (SELECT 1 FROM deliveries sent WHERE sent.digest_id=d.digest_id
                AND (sent.submitted_at IS NOT NULL
                    OR sent.state IN ('sending','unknown','accepted')))
        """),
            params,
        )
        conn.execute(
            text("""UPDATE digest_items i SET reservation_state='released',
            exclusion_reason=:reason FROM articles a WHERE a.id=i.article_id AND a.source_id=:id
            AND i.reservation_state IN ('none','held') AND NOT EXISTS (
                SELECT 1 FROM deliveries d WHERE d.digest_id=i.digest_id AND
                (d.submitted_at IS NOT NULL OR d.state IN ('sending','unknown','accepted')))
        """),
            params,
        )
        conn.execute(
            text("""UPDATE articles a SET notification_state='suppressed',
            eligible_on=NULL,suppression_reason=:reason WHERE source_id=:id
            AND notification_state='pending' AND NOT EXISTS (
                SELECT 1 FROM digest_items i WHERE i.article_id=a.id
                AND i.reservation_state IN ('held','consumed'))
        """),
            params,
        )

    def claim(self, owner_id: UUID) -> Lease | None:
        with self.engine.begin() as conn:
            prepare_transaction(conn)
            conn.execute(
                text("SELECT pg_advisory_xact_lock(:ns,:key)"),
                {"ns": SLOT_LOCK, "key": lock_key(owner_id)},
            )
            conn.execute(
                text("""UPDATE job_runs SET state='queued',lease_token=NULL,
                lease_expires_at=NULL WHERE owner_id=:owner AND state='running'
                AND kind IN ('collect','collect_final','baseline')
                AND lease_expires_at<=clock_timestamp()"""),
                {"owner": owner_id},
            )
            conn.execute(
                text("""UPDATE job_runs j SET state='skipped',
                result_code='SOURCE_CHANGED',finished_at=clock_timestamp()
                FROM sources s WHERE j.source_id=s.id AND j.owner_id=:owner AND j.state='queued'
                AND (s.status<>'active' OR s.generation<>j.source_generation)"""),
                {"owner": owner_id},
            )
            active = conn.execute(
                text("""SELECT count(*) FROM job_runs WHERE owner_id=:owner
                AND state='running' AND kind IN ('collect','collect_final','baseline')"""),
                {"owner": owner_id},
            ).scalar_one()
            if active >= 2:
                return None
            token = uuid4()
            row = (
                conn.execute(
                    text("""WITH candidate AS (
                SELECT id FROM job_runs WHERE owner_id=:owner AND state='queued'
                AND kind IN ('collect','collect_final','baseline')
                AND available_at<=clock_timestamp()
                ORDER BY available_at,id LIMIT 1 FOR UPDATE SKIP LOCKED)
                UPDATE job_runs j SET state='running',lease_token=:token,
                lease_expires_at=clock_timestamp()+make_interval(secs=>:lease),
                heartbeat_at=clock_timestamp(),started_at=COALESCE(started_at,clock_timestamp()),
                attempt_count=attempt_count+1 FROM candidate c WHERE j.id=c.id RETURNING j.*"""),
                    {"owner": owner_id, "token": token, "lease": LEASE_SECONDS},
                )
                .mappings()
                .one_or_none()
            )
            return (
                None
                if row is None
                else Lease(row["id"], owner_id, row["source_id"], row["source_generation"], token)
            )

    def heartbeat(self, lease: Lease) -> bool:
        with self.engine.begin() as conn:
            prepare_transaction(conn)
            return (
                conn.execute(
                    text("""UPDATE job_runs SET heartbeat_at=clock_timestamp(),
                lease_expires_at=clock_timestamp()+make_interval(secs=>:seconds)
                WHERE id=:id AND owner_id=:owner AND state='running' AND lease_token=:token
                AND lease_expires_at>clock_timestamp() RETURNING id"""),
                    {
                        "id": lease.id,
                        "owner": lease.owner_id,
                        "token": lease.token,
                        "seconds": LEASE_SECONDS,
                    },
                ).scalar_one_or_none()
                is not None
            )

    @staticmethod
    def finish(conn: Connection, lease: Lease, state: str, code: str | None = None) -> None:
        result = conn.execute(
            text("""UPDATE job_runs SET state=:state,result_code=:code,
            finished_at=clock_timestamp() WHERE id=:id AND owner_id=:owner AND source_id=:source
            AND source_generation=:gen AND state='running' AND lease_token=:token
            AND lease_expires_at>clock_timestamp() RETURNING id"""),
            {
                "id": lease.id,
                "owner": lease.owner_id,
                "source": lease.source_id,
                "gen": lease.generation,
                "token": lease.token,
                "state": state,
                "code": code,
            },
        ).scalar_one_or_none()
        if result is None:
            raise CollectionError("STALE_JOB")


class SubscriptionService:
    def __init__(self, store: CollectionStore, core: CollectionCore) -> None:
        self.store = store
        self.core = core

    async def add(
        self, owner_id: UUID, input_url: str, collection_url: str
    ) -> tuple[RowMapping, UUID]:
        option = await self.core.validate_selection(input_url, collection_url)
        return self.store.add_source(owner_id, input_url, option)
