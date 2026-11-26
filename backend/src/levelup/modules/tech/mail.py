"""Durable briefing snapshots and one-shot Gmail dispatch; uncertain receipts remain reserved."""

import hashlib
import html
import json
from collections.abc import Callable
from datetime import date, datetime
from email.message import EmailMessage
from email.policy import SMTP
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from levelup.core.config import Settings
from levelup.core.security import Cipher
from levelup.infra.gmail import Gmail, SendOutcome
from levelup.infra.google import GMAIL_SCOPE
from levelup.infra.public_http import CollectionError, normalize_url
from levelup.modules.tech.digests import schedule
from levelup.modules.tech.eligibility import Eligibility, compute_eligibility
from levelup.modules.tech.persistence import (
    LEASE_SECONDS,
    OWNER_LOCK,
    locked_connection,
    now,
    prepare_transaction,
)


def pending(conn: Connection, owner: UUID, day: date) -> list[RowMapping]:
    return list(
        conn.execute(
            text("""SELECT a.*,s.name AS source_name FROM articles a JOIN
                     sources s ON s.id=a.source_id WHERE s.owner_id=:owner AND
                     s.status= 'active' AND s.initialization_state= 'ready' AND
                     a.notification_state= 'pending' AND a.eligible_on<=:day AND
                     NOT EXISTS (SELECT 1 FROM digest_items i WHERE
                     i.article_id=a.id AND i.reservation_state IN ( 'held' ,
                     'consumed' )) ORDER BY
                     COALESCE(a.published_at,a.first_seen_at) DESC,a.id DESC"""),
            {"owner": owner, "day": day},
        ).mappings()
    )


def mime_payload(
    identifier: UUID, origin: str, email: str, day: date | None, items: list[RowMapping]
) -> tuple[str, str, bytes]:
    host = urlsplit(origin).hostname
    if not host or any(c in email for c in "\r\n") or "@" not in email:
        raise CollectionError("GMAIL_ADDRESS_INVALID")
    message_id = f"<{identifier}@{host}>"
    subject = (
        f"모닝 테크 · {day.isoformat()} · {len(items)}개" if day else "LevelUp · Gmail 연결 테스트"
    )
    message = EmailMessage(policy=SMTP)
    message["From"] = message["To"] = email
    message["Subject"], message["Message-ID"] = subject, message_id
    plain = [subject, "Gmail 접수와 받은편지함 도착은 별도입니다.", ""]
    fragments = ["<!doctype html><html lang='ko'><body>", "<h1>" + html.escape(subject) + "</h1>"]
    if day is None:
        plain.append(
            "LevelUp에서 직접 요청한 테스트 메일입니다. 정기 브리핑의 글 상태는 변경하지 않습니다."
        )
        fragments.append("<p>LevelUp에서 직접 요청한 테스트 메일입니다.</p>")
    else:
        groups: dict[str, list[RowMapping]] = {}
        for item in items[:20]:
            groups.setdefault(item["source_name_snapshot"], []).append(item)
        for name, articles in groups.items():
            plain.append(name)
            fragments.append("<h2>" + html.escape(name) + "</h2><ul>")
            for article in articles:
                url = normalize_url(article["url_snapshot"])
                title = article["title_snapshot"]
                plain.append(f"- {title}\n  {url}")
                fragments.append(
                    '<li><a href="'
                    + html.escape(url, quote=True)
                    + '">'
                    + html.escape(title)
                    + "</a></li>"
                )
            fragments.append("</ul>")
        link = origin + "/tech?date=" + day.isoformat()
        plain.append(
            f"\n전체 {len(items)}개 · 메일에는 최신 20개까지 표시합니다.\n전체 글 보기: {link}"
        )
        fragments.append(
            "<p>전체 "
            + str(len(items))
            + '개 · 최신 20개 표시</p><a href="'
            + html.escape(link, quote=True)
            + '">전체 글 보기</a>'
        )
    fragments.append("</body></html>")
    message.set_content("\n".join(plain))
    message.add_alternative("".join(fragments), subtype="html")
    return subject, message_id, message.as_bytes()


class MailService:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        transport: Any = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.engine, self.settings = engine, settings
        self.transport = transport or Gmail(settings)
        self.clock = clock
        self.cipher = Cipher(settings.token_encryption_key)

    def instant(self, conn: Connection) -> datetime:
        return self.clock() if self.clock else now(conn)

    @staticmethod
    def connection(conn: Connection, owner: UUID) -> RowMapping | None:
        return (
            conn.execute(
                text("SELECT * FROM gmail_connections WHERE owner_id=:owner"), {"owner": owner}
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def valid_connection(owner: RowMapping, connection: RowMapping | None) -> bool:
        return bool(
            connection is not None
            and connection["state"] == "connected"
            and connection["google_subject"] == owner["auth_subject"]
            and connection["email"] == owner["auth_email"]
            and GMAIL_SCOPE in connection["scopes"]
            and connection["refresh_token_ciphertext"] is not None
        )

    def enqueue_digest(self, owner: UUID, day: date) -> UUID:
        start, _ = schedule(day)
        return self._enqueue(owner, "digest", f"digest/{owner}/{day}", {"date": str(day)}, start)

    def enqueue_test(self, owner: UUID, request: UUID) -> UUID:
        with locked_connection(self.engine, OWNER_LOCK, owner) as conn, conn.begin():
            account = (
                conn.execute(text("SELECT * FROM owner_settings WHERE id=:id"), {"id": owner})
                .mappings()
                .one()
            )
            if not self.valid_connection(account, self.connection(conn, owner)):
                raise CollectionError("GMAIL_NOT_CONNECTED")
            return self._insert_job(
                conn, owner, "test_email", f"test/{owner}/{request}", {}, self.instant(conn)
            )

    def _enqueue(self, owner: UUID, kind: str, key: str, data: dict, available: datetime) -> UUID:
        with self.engine.begin() as conn:
            return self._insert_job(conn, owner, kind, key, data, available)

    @staticmethod
    def _insert_job(
        conn: Connection, owner: UUID, kind: str, key: str, data: dict, available: datetime
    ) -> UUID:
        identifier = uuid4()
        value = conn.execute(
            text("""INSERT INTO job_runs(id,owner_id,kind,dedup_key,input,available_at)
            VALUES (:id,:owner,:kind,:key,CAST(:input AS jsonb),:at)
            ON CONFLICT (dedup_key) DO NOTHING RETURNING id"""),
            {
                "id": identifier,
                "owner": owner,
                "kind": kind,
                "key": key,
                "input": json.dumps(data),
                "at": available,
            },
        ).scalar_one_or_none()
        if value is not None:
            return value
        return conn.execute(
            text("SELECT id FROM job_runs WHERE owner_id=:owner AND dedup_key=:key"),
            {"owner": owner, "key": key},
        ).scalar_one()

    def _recover(self, conn: Connection, owner: UUID) -> None:
        expired = (
            conn.execute(
                text("""SELECT * FROM job_runs WHERE owner_id=:owner AND kind
                         IN ( 'digest' , 'test_email' ) AND state= 'running' AND
                         lease_expires_at<=clock_timestamp() FOR UPDATE"""),
                {"owner": owner},
            )
            .mappings()
            .all()
        )
        for job in expired:
            identifier = (job["result_summary"] or {}).get("deliveryId")
            delivery = (
                None
                if not identifier
                else conn.execute(
                    text("SELECT * FROM deliveries WHERE id=:id AND owner_id=:owner"),
                    {"id": UUID(identifier), "owner": owner},
                )
                .mappings()
                .one_or_none()
            )
            if delivery and (
                delivery["submitted_at"] is not None
                or delivery["state"] in ("sending", "unknown", "accepted")
            ):
                if delivery["state"] == "sending":
                    conn.execute(
                        text(
                            """UPDATE deliveries SET state= 'unknown'
                                ,last_error_code= 'WORKER_INTERRUPTED' WHERE
                                id=:id"""
                        ),
                        {"id": delivery["id"]},
                    )
                    if delivery["digest_id"]:
                        conn.execute(
                            text(
                                """UPDATE digests SET state= 'unknown' ,reason_code=
                'WORKER_INTERRUPTED' WHERE id=:id"""
                            ),
                            {"id": delivery["digest_id"]},
                        )
                state = "succeeded" if delivery["state"] == "accepted" else "failed"
                conn.execute(
                    text(
                        """UPDATE job_runs SET state=:state,result_code=
                            'RECOVERED_RECEIPT' ,finished_at=clock_timestamp()
                            WHERE id=:id"""
                    ),
                    {"id": job["id"], "state": state},
                )
            else:
                conn.execute(
                    text(
                        """UPDATE job_runs SET state= 'queued'
                            ,lease_token=NULL,lease_expires_at=NULL WHERE id=:id"""
                    ),
                    {"id": job["id"]},
                )

    def _claim(
        self, conn: Connection, owner: UUID, only_job: UUID | None = None
    ) -> RowMapping | None:
        self._recover(conn, owner)
        if conn.execute(
            text(
                "SELECT 1 FROM job_runs WHERE owner_id=:owner AND state='running' "
                "AND kind IN ('digest','test_email') LIMIT 1"
            ),
            {"owner": owner},
        ).scalar_one_or_none():
            return None
        token = uuid4()
        return (
            conn.execute(
                text("""WITH candidate AS (SELECT id FROM job_runs WHERE
                         owner_id=:owner AND kind IN ( 'digest' , 'test_email' )
                         AND state= 'queued' AND available_at<=:at
                         AND id=COALESCE(CAST(:only_job AS uuid),id) ORDER BY CASE
                         WHEN kind= 'digest' THEN 0 ELSE 1 END,available_at,id
                         LIMIT 1 FOR UPDATE SKIP LOCKED) UPDATE job_runs j SET
                         state= 'running' ,lease_token=:token,
                         lease_expires_at=clock_timestamp()+make_interval(secs=>:lease),
                         heartbeat_at=clock_timestamp(),started_at=COALESCE(started_at,clock_timestamp()),
                         attempt_count=attempt_count+1 FROM candidate c WHERE
                         j.id=c.id RETURNING j.*"""),
                {
                    "owner": owner,
                    "at": self.instant(conn),
                    "token": token,
                    "lease": LEASE_SECONDS,
                    "only_job": only_job,
                },
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def _finish_job(conn: Connection, job: RowMapping, state: str, code: str | None = None) -> None:
        conn.execute(
            text(
                """UPDATE job_runs SET
                    state=:state,result_code=:code,finished_at=clock_timestamp()"""
                "WHERE id=:id AND lease_token=:token AND state='running'"
            ),
            {"id": job["id"], "token": job["lease_token"], "state": state, "code": code},
        )

    def _snapshot(self, conn: Connection, job: RowMapping, owner: RowMapping) -> RowMapping | None:
        day = date.fromisoformat(job["input"]["date"])
        start, deadline = schedule(day)
        existing = (
            conn.execute(
                text("SELECT * FROM digests WHERE owner_id=:owner AND digest_date=:day"),
                {"owner": owner["id"], "day": day},
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            return existing
        conn.execute(
            text("SELECT id FROM sources WHERE owner_id=:owner ORDER BY id FOR UPDATE"),
            {"owner": owner["id"]},
        ).all()
        items = pending(conn, owner["id"], day)
        if items:
            conn.execute(
                text(
                    """SELECT id FROM articles WHERE id=ANY(CAST(:ids AS
                        uuid[])) ORDER BY id FOR UPDATE"""
                ),
                {"ids": [item["id"] for item in items]},
            ).all()
        at = self.instant(conn)
        state, reason, snapshot = "ready", None, True
        if owner["created_at"] > start:
            self._finish_job(conn, job, "skipped", "NOT_SCHEDULED")
            return None
        if at < start:
            raise CollectionError("NOT_SCHEDULED")
        if at >= deadline:
            state, reason, snapshot = "missed", "START_DEADLINE_MISSED", False
        elif not items:
            state, reason = "empty", "NO_ELIGIBLE_ITEMS"
        elif not owner["notifications_enabled"]:
            state, reason = "paused", "NOTIFICATIONS_PAUSED"
        elif not self.valid_connection(owner, self.connection(conn, owner["id"])):
            state, reason = "failed", "GMAIL_NOT_CONNECTED"
        identifier = uuid4()
        row = (
            conn.execute(
                text("""INSERT INTO digests(id,owner_id,digest_date,state,reason_code,
            scheduled_at,start_deadline_at,started_at,snapshot_at,created_at,updated_at)
            VALUES (:id,:owner,:day,:state,:reason,:start,:deadline,:snapshot,:snapshot,:at,:at)
            RETURNING *"""),
                {
                    "id": identifier,
                    "owner": owner["id"],
                    "day": day,
                    "state": state,
                    "reason": reason,
                    "start": start,
                    "deadline": deadline,
                    "snapshot": at if snapshot else None,
                    "at": at,
                },
            )
            .mappings()
            .one()
        )
        if snapshot:
            for position, item in enumerate(items, 1):
                conn.execute(
                    text("""INSERT INTO
                             digest_items(digest_id,article_id,title_snapshot,
                             url_snapshot,source_name_snapshot,sort_position,shown_in_email,reservation_state,
                             created_at) VALUES
                             (:digest,:article,:title,:url,:name,:position,:shown,:state,:at)"""),
                    {
                        "digest": identifier,
                        "article": item["id"],
                        "title": item["title"],
                        "url": item["canonical_url"],
                        "name": item["source_name"],
                        "position": position,
                        "shown": position <= 20,
                        "state": "held" if state == "ready" else "none",
                        "at": at,
                    },
                )
        return row

    def _items(self, conn: Connection, digest_id: UUID) -> list[RowMapping]:
        return list(
            conn.execute(
                text(
                    "SELECT * FROM digest_items WHERE digest_id=:id "
                    "AND exclusion_reason IS NULL ORDER BY sort_position"
                ),
                {"id": digest_id},
            ).mappings()
        )

    def _cancel(self, conn: Connection, delivery: RowMapping, code: str) -> None:
        conn.execute(
            text(
                """UPDATE deliveries SET state= 'cancelled'
                    ,last_error_code=:code,finished_at=clock_timestamp()"""
                "WHERE id=:id AND submitted_at IS NULL"
            ),
            {"id": delivery["id"], "code": code},
        )
        if delivery["digest_id"]:
            conn.execute(
                text(
                    "UPDATE digest_items SET reservation_state='released' WHERE digest_id=:id "
                    "AND reservation_state='held'"
                ),
                {"id": delivery["digest_id"]},
            )

    def _prepare(
        self,
        conn: Connection,
        job: RowMapping,
        owner: RowMapping,
        connection: RowMapping,
        briefing: RowMapping | None,
    ) -> RowMapping | None:
        digest_id = briefing["id"] if briefing else None
        if briefing and briefing["state"] != "ready":
            self._finish_job(
                conn, job, "skipped", briefing["reason_code"] or briefing["state"].upper()
            )
            return None
        if digest_id:
            assert briefing is not None
            all_deliveries = (
                conn.execute(
                    text("SELECT * FROM deliveries WHERE digest_id=:id ORDER BY revision"),
                    {"id": digest_id},
                )
                .mappings()
                .all()
            )
            if any(row["submitted_at"] is not None for row in all_deliveries):
                self._finish_job(conn, job, "skipped", "ALREADY_REQUESTED")
                return None
            for delivery in all_deliveries:
                if delivery["state"] == "prepared":
                    self._cancel(conn, delivery, "REBUILD_REQUIRED")
            # Only the original snapshot may shrink; never pull in newly collected articles.
            conn.execute(
                text("""SELECT s.id FROM sources s JOIN articles a ON a.source_id=s.id
                JOIN digest_items i ON i.article_id=a.id WHERE i.digest_id=:id ORDER BY s.id
                FOR UPDATE OF s"""),
                {"id": digest_id},
            ).all()
            conn.execute(
                text("""SELECT a.id FROM articles a JOIN digest_items i ON i.article_id=a.id
                WHERE i.digest_id=:id ORDER BY a.id FOR UPDATE OF a"""),
                {"id": digest_id},
            ).all()
            conn.execute(
                text("""UPDATE digest_items i SET exclusion_reason=
                         'INELIGIBLE' ,reservation_state= 'released' FROM
                         articles a,sources s WHERE i.digest_id=:id AND
                         i.article_id=a.id AND s.id=a.source_id AND (s.status<>
                         'active' OR a.notification_state<> 'pending' OR
                         a.eligible_on>:day) AND i.reservation_state<>
                         'consumed'"""),
                {"id": digest_id, "day": briefing["digest_date"]},
            )
            items = self._items(conn, digest_id)
            conn.execute(
                text("""UPDATE digest_items SET shown_in_email=
                (article_id=ANY(CAST(:ids AS uuid[]))) WHERE digest_id=:id"""),
                {"id": digest_id, "ids": [item["article_id"] for item in items[:20]]},
            )
            if not items:
                conn.execute(
                    text(
                        """UPDATE digests SET state= 'empty' ,reason_code=
                            'NO_ELIGIBLE_ITEMS' ,updated_at=clock_timestamp()
                            WHERE id=:id"""
                    ),
                    {"id": digest_id},
                )
                self._finish_job(conn, job, "succeeded", "NO_ELIGIBLE_ITEMS")
                return None
            if self.instant(conn) >= schedule(briefing["digest_date"])[1]:
                conn.execute(
                    text(
                        """UPDATE digest_items SET reservation_state=
                            'released' WHERE digest_id=:id AND
                            reservation_state= 'held'"""
                    ),
                    {"id": digest_id},
                )
                conn.execute(
                    text(
                        """UPDATE digests SET state= 'failed' ,reason_code=
                            'RECOVERY_WINDOW_EXPIRED' WHERE id=:id"""
                    ),
                    {"id": digest_id},
                )
                self._finish_job(conn, job, "failed", "RECOVERY_WINDOW_EXPIRED")
                return None
            conn.execute(
                text(
                    """UPDATE digest_items SET reservation_state= 'held' WHERE
                        digest_id=:id AND exclusion_reason IS NULL AND
                        reservation_state IN ( 'none' , 'released' )"""
                ),
                {"id": digest_id},
            )
            revision = len(all_deliveries) + 1
        else:
            items, revision = [], 1
            existing = (
                conn.execute(
                    text("SELECT * FROM deliveries WHERE request_key=:key"),
                    {"key": job["dedup_key"]},
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                return existing
        identifier = uuid4()
        day = briefing["digest_date"] if briefing else None
        subject, message_id, payload = mime_payload(
            identifier, self.settings.app_origin, connection["email"], day, items
        )
        key = f"digest/{owner['id']}/{day}/{revision}" if briefing else job["dedup_key"]
        row = (
            conn.execute(
                text("""INSERT INTO
                         deliveries(id,owner_id,kind,digest_id,gmail_connection_id,
                         connection_version,revision,request_key,mime_message_id,from_address,to_address,subject,
                         mime_payload,payload_sha256,state,prepared_at) VALUES
                         (:id,:owner,:kind,:digest,:connection,
                         :version,:revision,:key,:message,:email,:email,:subject,:payload,:hash,
                         'prepared' ,:at) RETURNING *"""),
                {
                    "id": identifier,
                    "owner": owner["id"],
                    "kind": "digest" if briefing else "test",
                    "digest": digest_id,
                    "connection": connection["id"],
                    "version": connection["version"],
                    "revision": revision,
                    "key": key,
                    "message": message_id,
                    "email": connection["email"],
                    "subject": subject,
                    "payload": payload,
                    "hash": hashlib.sha256(payload).hexdigest(),
                    "at": self.instant(conn),
                },
            )
            .mappings()
            .one()
        )
        conn.execute(
            text(
                """UPDATE job_runs SET result_summary=jsonb_build_object(
                    'deliveryId' ,CAST(:id AS text)) WHERE id=:job"""
            ),
            {"id": identifier, "job": job["id"]},
        )
        return row

    @staticmethod
    def _lock_items(conn: Connection, digest_id: UUID | None) -> None:
        if digest_id is None:
            return
        conn.execute(
            text("""SELECT s.id FROM sources s JOIN articles a ON a.source_id=s.id
            JOIN digest_items i ON i.article_id=a.id WHERE i.digest_id=:id ORDER BY s.id
            FOR UPDATE OF s"""),
            {"id": digest_id},
        ).all()
        conn.execute(
            text("""SELECT a.id FROM articles a JOIN digest_items i ON i.article_id=a.id
            WHERE i.digest_id=:id ORDER BY a.id FOR UPDATE OF a"""),
            {"id": digest_id},
        ).all()

    def _release(self, conn: Connection, digest_id: UUID) -> None:
        articles = (
            conn.execute(
                text("""SELECT a.*,s.status,s.id AS sid,e.reason,e.started_at
            FROM articles a JOIN sources s ON s.id=a.source_id
            JOIN digest_items i ON i.article_id=a.id LEFT JOIN subscription_epochs e
                ON e.source_id=s.id AND e.ended_at IS NULL
            WHERE i.digest_id=:id AND i.reservation_state='held' ORDER BY a.id"""),
                {"id": digest_id},
            )
            .mappings()
            .all()
        )
        for article in articles:
            if article["notification_state"] != "pending":
                continue
            reason: str | None
            if article["status"] != "active":
                result = Eligibility("suppressed", None)
                reason = "source_deleted" if article["status"] == "deleted" else "source_disabled"
            else:
                result = compute_eligibility(
                    baseline=False,
                    epoch_kind=article["reason"],
                    epoch_started_at=article["started_at"],
                    first_seen_at=article["first_seen_at"],
                    published_at=article["published_at"],
                )
                reason = "inactive_period" if result.state == "suppressed" else None
            conn.execute(
                text(
                    "UPDATE articles SET notification_state=:state,eligible_on=:day,"
                    "suppression_reason=:reason WHERE id=:id"
                ),
                {
                    "state": result.state,
                    "day": result.eligible_on,
                    "reason": reason,
                    "id": article["id"],
                },
            )
        conn.execute(
            text(
                "UPDATE digest_items SET reservation_state='released' "
                "WHERE digest_id=:id AND reservation_state='held'"
            ),
            {"id": digest_id},
        )

    def _fail_before(
        self, conn: Connection, job: RowMapping, briefing: RowMapping | None, code: str
    ) -> None:
        if briefing:
            self._lock_items(conn, briefing["id"])
            conn.execute(
                text("""UPDATE deliveries SET state='cancelled',last_error_code=:code,
                finished_at=clock_timestamp() WHERE digest_id=:id AND state='prepared'
                AND submitted_at IS NULL"""),
                {"id": briefing["id"], "code": code},
            )
            self._release(conn, briefing["id"])
            conn.execute(
                text(
                    """UPDATE digests SET state= 'failed'
                        ,reason_code=:code,updated_at=clock_timestamp()"""
                    "WHERE id=:id AND state NOT IN ('accepted','sending','unknown')"
                ),
                {"id": briefing["id"], "code": code},
            )
        self._finish_job(conn, job, "failed", code)

    def _submit(
        self,
        conn: Connection,
        job: RowMapping,
        owner: RowMapping,
        connection: RowMapping,
        briefing: RowMapping | None,
        delivery: RowMapping,
    ) -> RowMapping | None:
        digest_id = delivery["digest_id"]
        self._lock_items(conn, digest_id)
        current = self.connection(conn, owner["id"])
        owner = (
            conn.execute(text("SELECT * FROM owner_settings WHERE id=:id"), {"id": owner["id"]})
            .mappings()
            .one()
        )
        valid = (
            self.valid_connection(owner, current)
            and current is not None
            and (
                current["id"] == delivery["gmail_connection_id"]
                and current["version"] == delivery["connection_version"]
                and current["email"] == delivery["from_address"] == delivery["to_address"]
            )
        )
        if not valid or (briefing and not owner["notifications_enabled"]):
            self._cancel(conn, delivery, "CONNECTION_CHANGED")
            self._fail_before(conn, job, briefing, "CONNECTION_CHANGED")
            return None
        if digest_id:
            assert briefing is not None and current is not None
            invalid = conn.execute(
                text("""SELECT 1 FROM digest_items i JOIN articles a ON
                         a.id=i.article_id JOIN sources s ON s.id=a.source_id
                         WHERE i.digest_id=:id AND i.exclusion_reason IS NULL
                         AND (s.status<> 'active' OR a.notification_state<>
                         'pending' OR a.eligible_on>:day) LIMIT 1"""),
                {"id": digest_id, "day": briefing["digest_date"]},
            ).scalar_one_or_none()
            if invalid:
                rebuilt = self._prepare(conn, job, owner, current, briefing)
                if rebuilt is None:
                    return None
                delivery = rebuilt
            if self.instant(conn) >= schedule(briefing["digest_date"])[1]:
                self._cancel(conn, delivery, "RECOVERY_WINDOW_EXPIRED")
                self._fail_before(conn, job, briefing, "RECOVERY_WINDOW_EXPIRED")
                return None
        if delivery["state"] != "prepared" or delivery["submitted_at"] is not None:
            self._finish_job(conn, job, "skipped", "ALREADY_REQUESTED")
            return None
        payload = bytes(delivery["mime_payload"])
        if hashlib.sha256(payload).hexdigest() != delivery["payload_sha256"]:
            self._cancel(conn, delivery, "PAYLOAD_MISMATCH")
            self._fail_before(conn, job, briefing, "PAYLOAD_MISMATCH")
            return None
        row = (
            conn.execute(
                text("""UPDATE deliveries SET state='sending',submitted_at=:at
            WHERE id=:id AND state='prepared' AND submitted_at IS NULL RETURNING *"""),
                {"id": delivery["id"], "at": self.instant(conn)},
            )
            .mappings()
            .one()
        )
        lease = conn.execute(
            text("""SELECT 1 FROM job_runs WHERE id=:id AND lease_token=:token
            AND state='running' AND lease_expires_at>clock_timestamp() FOR UPDATE"""),
            {"id": job["id"], "token": job["lease_token"]},
        ).scalar_one_or_none()
        if not lease:
            raise CollectionError("STALE_JOB")
        if digest_id:
            conn.execute(
                text("UPDATE digests SET state='sending',reason_code=NULL WHERE id=:id"),
                {"id": digest_id},
            )
        return row

    def _record(
        self,
        conn: Connection,
        owner: UUID,
        delivery_id: UUID,
        payload_hash: str,
        outcome: SendOutcome,
    ) -> str:
        saved = (
            conn.execute(
                text("SELECT * FROM deliveries WHERE id=:id AND owner_id=:owner"),
                {"id": delivery_id, "owner": owner},
            )
            .mappings()
            .one()
        )
        self._lock_items(conn, saved["digest_id"])
        saved = (
            conn.execute(
                text("SELECT * FROM deliveries WHERE id=:id FOR UPDATE"), {"id": delivery_id}
            )
            .mappings()
            .one()
        )
        if saved["payload_sha256"] != payload_hash or saved["submitted_at"] is None:
            raise CollectionError("INVALID_RECEIPT")
        if saved["state"] == "accepted":
            return "accepted"
        state = (
            "accepted"
            if outcome.kind == "accepted"
            else "unknown"
            if outcome.kind == "unknown"
            else "failed"
        )
        if state == "accepted" and not outcome.provider_id:
            raise CollectionError("INVALID_RECEIPT")
        at = self.instant(conn)
        conn.execute(
            text("""UPDATE deliveries SET
                     state=:state,provider_message_id=:provider,
                     accepted_at=:accepted,finished_at=:at,http_status=:http,last_error_code=:code
                     WHERE id=:id"""),
            {
                "state": state,
                "provider": outcome.provider_id,
                "accepted": at if state == "accepted" else None,
                "at": at,
                "http": outcome.http_status,
                "code": outcome.code,
                "id": delivery_id,
            },
        )
        digest_id = saved["digest_id"]
        if digest_id:
            if state == "accepted":
                conn.execute(
                    text("""UPDATE articles a SET notification_state=
                             'notified' ,notified_digest_id=:id FROM
                             digest_items i WHERE i.digest_id=:id AND
                             i.article_id=a.id AND i.exclusion_reason IS NULL"""),
                    {"id": digest_id},
                )
                conn.execute(
                    text(
                        """UPDATE digest_items SET reservation_state=
                            'consumed' WHERE digest_id=:id AND exclusion_reason
                            IS NULL"""
                    ),
                    {"id": digest_id},
                )
            elif state == "failed":
                self._release(conn, digest_id)
            conn.execute(
                text("""UPDATE digests SET state=:state,reason_code=:code,
                accepted_at=:accepted,updated_at=:at WHERE id=:id"""),
                {
                    "state": state,
                    "code": outcome.code,
                    "accepted": at if state == "accepted" else None,
                    "at": at,
                    "id": digest_id,
                },
            )
        if outcome.code == "GMAIL_REAUTH_REQUIRED":
            conn.execute(
                text(
                    """UPDATE gmail_connections SET state= 'reauth_required'
                        ,version=version+1,last_error_code=:code,updated_at=:at
                        WHERE id=:id AND version=:version"""
                ),
                {
                    "id": saved["gmail_connection_id"],
                    "version": saved["connection_version"],
                    "at": at,
                    "code": outcome.code,
                },
            )
        return state

    def record_receipt(
        self, owner: UUID, delivery_id: UUID, payload_hash: str, outcome: SendOutcome
    ) -> str:
        with locked_connection(self.engine, OWNER_LOCK, owner) as conn, conn.begin():
            prepare_transaction(conn)
            return self._record(conn, owner, delivery_id, payload_hash, outcome)

    async def run_next(self, owner_id: UUID, only_job: UUID | None = None) -> str | None:
        with locked_connection(self.engine, OWNER_LOCK, owner_id) as conn:
            with conn.begin():
                prepare_transaction(conn)
                job = self._claim(conn, owner_id, only_job)
                if job is None:
                    return None
                owner = (
                    conn.execute(
                        text("SELECT * FROM owner_settings WHERE id=:id"), {"id": owner_id}
                    )
                    .mappings()
                    .one()
                )
                briefing = self._snapshot(conn, job, owner) if job["kind"] == "digest" else None
                if job["kind"] == "digest" and (briefing is None or briefing["state"] != "ready"):
                    if briefing:
                        self._finish_job(
                            conn,
                            job,
                            "skipped",
                            briefing["reason_code"] or briefing["state"].upper(),
                        )
                    return briefing["state"] if briefing else "not_scheduled"
                connection = self.connection(conn, owner_id)
                if not self.valid_connection(owner, connection):
                    self._fail_before(conn, job, briefing, "GMAIL_NOT_CONNECTED")
                    return "failed"
                if not self.settings.mail_delivery_enabled:
                    self._fail_before(conn, job, briefing, "DELIVERY_DISABLED")
                    return "failed"
                assert connection is not None
                try:
                    refresh = self.cipher.decrypt(
                        bytes(connection["refresh_token_ciphertext"]), str(owner_id)
                    )
                except Exception:
                    self._fail_before(conn, job, briefing, "GMAIL_TOKEN_FAILED")
                    return "failed"
            try:
                token = await self.transport.refresh(refresh)
            except CollectionError as exc:
                with conn.begin():
                    if exc.code == "GMAIL_REAUTH_REQUIRED":
                        conn.execute(
                            text(
                                """UPDATE gmail_connections SET state= 'reauth_required'
                ,version=version+1,last_error_code=:code,updated_at=clock_timestamp()
                WHERE id=:id"""
                            ),
                            {"id": connection["id"], "code": exc.code},
                        )
                    self._fail_before(conn, job, briefing, exc.code)
                return "failed"
            with conn.begin():
                delivery = self._prepare(conn, job, owner, connection, briefing)
                if delivery is None:
                    return "empty" if briefing else "failed"
            with conn.begin():
                delivery = self._submit(conn, job, owner, connection, briefing, delivery)
                if delivery is None:
                    return "cancelled"
            # Commit sending before HTTP; no row lock spans the external request.
            try:
                outcome = await self.transport.send(token, bytes(delivery["mime_payload"]))
            except Exception:
                outcome = SendOutcome("unknown", "GMAIL_REQUEST_UNCLEAR")
            with conn.begin():
                state = self._record(
                    conn, owner_id, delivery["id"], delivery["payload_sha256"], outcome
                )
                self._finish_job(
                    conn, job, "succeeded" if state == "accepted" else "failed", outcome.code
                )
            return state
