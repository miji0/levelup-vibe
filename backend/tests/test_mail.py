from datetime import date, datetime, timedelta
from email import policy
from email.parser import BytesParser
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import IntegrityError
from test_collection_store import Core, add, execute, item, rows, rss

from levelup.core.security import Cipher
from levelup.infra.gmail import SendOutcome
from levelup.infra.google import GMAIL_SCOPE
from levelup.infra.public_http import CollectionError
from levelup.modules.tech.digests import DigestViews
from levelup.modules.tech.mail import MailService
from levelup.modules.tech.persistence import CollectionStore
from levelup.modules.tech.worker import CollectionWorker

KST = ZoneInfo("Asia/Seoul")
DAY = date(2026, 11, 27)


class FakeGmail:
    def __init__(self):
        self.refreshes = []
        self.calls = []
        self.outcome = None
        self.error = None
        self.refresh_hook = None
        self.send_hook = None

    async def refresh(self, token):
        self.refreshes.append(token)
        if self.error:
            raise CollectionError(self.error)
        if self.refresh_hook:
            await self.refresh_hook()
        return "fake-access"

    async def send(self, token, payload):
        self.calls.append(payload)
        if self.send_hook:
            await self.send_hook()
        return self.outcome or SendOutcome(
            "accepted", provider_id=f"accepted-{len(self.calls)}", http_status=200
        )


@pytest.fixture
def owner(db):
    identifier = rows(db, "SELECT id FROM owner_settings")[0]["id"]
    execute(
        db, "UPDATE owner_settings SET created_at='2020-01-01T00:00:00Z',notifications_enabled=true"
    )
    return identifier


@pytest.fixture
def gmail(db, settings, owner):
    settings.mail_delivery_enabled = True
    identifier = uuid4()
    token = Cipher(settings.token_encryption_key).encrypt("fake-refresh", str(owner))
    execute(
        db,
        """INSERT INTO gmail_connections(id,owner_id,google_subject,email,scopes,state,
        refresh_token_ciphertext,created_at,updated_at) VALUES (:id,:owner,'owner-123',
        'owner@example.com',:scopes,'connected',:token,clock_timestamp(),clock_timestamp())""",
        id=identifier,
        owner=owner,
        scopes=[GMAIL_SCOPE],
        token=token,
    )
    return FakeGmail()


@pytest.fixture
def clock():
    return [datetime(2026, 11, 27, 8, 0, tzinfo=KST)]


def service(db, settings, gmail, clock):
    return MailService(db, settings, gmail, lambda: clock[0])


async def collect_pending(db, owner, count):
    store = CollectionStore(db)
    source, _ = add(store, owner)
    core = Core()
    worker = CollectionWorker(store, core)
    await worker.run_next(owner)
    core.body = rss(*(item(str(n), f"Title {n}") for n in range(count)))
    store.enqueue(owner, source["id"], "new")
    assert await worker.run_next(owner) == "success"
    return store, source, core, worker


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 20, 21])
async def test_zero_twenty_twentyone_one_request_and_whole_snapshot_notified(
    db, settings, owner, gmail, clock, count
):
    await collect_pending(db, owner, count)
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == ("accepted" if count else "empty")
    assert len(gmail.calls) == (1 if count else 0)
    digest = rows(db, "SELECT * FROM digests")[0]
    assert digest["state"] == ("accepted" if count else "empty")
    items = rows(db, "SELECT * FROM digest_items ORDER BY sort_position")
    assert len(items) == count and sum(i["shown_in_email"] for i in items) == min(20, count)
    if count:
        assert all(
            a["notification_state"] == "notified" for a in rows(db, "SELECT * FROM articles")
        )
        assert all(i["reservation_state"] == "consumed" for i in items)
        assert all(not a["is_read"] for a in rows(db, "SELECT * FROM article_states"))
        message = BytesParser(policy=policy.default).parsebytes(gmail.calls[0])
        assert message["From"] == message["To"] == "owner@example.com"
        assert f"{count}개" in message["Subject"]
        assert f"/tech?date={DAY}" in message.get_body(preferencelist=("html",)).get_content()
        assert (
            all(
                i["title_snapshot"] in message.as_string() or i["shown_in_email"] is False
                for i in items
            )
            is not None
        )
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) is None
    assert len(gmail.calls) == (1 if count else 0)


@pytest.mark.asyncio
async def test_reading_hidden_saved_do_not_exclude_mail_and_no_next_day_remainder(
    db, settings, owner, gmail, clock
):
    await collect_pending(db, owner, 21)
    execute(
        db,
        "UPDATE article_states SET is_hidden=true,hidden_at=clock_timestamp(),"
        "is_read=true,read_at=clock_timestamp(),is_saved=true,saved_at=clock_timestamp()",
    )
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == "accepted"
    clock[0] += timedelta(days=1)
    mail.enqueue_digest(owner, DAY + timedelta(days=1))
    assert await mail.run_next(owner) == "empty" and len(gmail.calls) == 1
    assert all(
        s["is_read"] and s["is_saved"] and s["is_hidden"]
        for s in rows(db, "SELECT * FROM article_states")
    )


@pytest.mark.asyncio
async def test_snapshot_does_not_expand_during_token_refresh(db, settings, owner, gmail, clock):
    store, source, core, worker = await collect_pending(db, owner, 1)

    async def later_collection():
        core.body = rss(item("0"), item("late"))
        store.enqueue(owner, source["id"], "late")
        await worker.run_next(owner)

    gmail.refresh_hook = later_collection
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == "accepted"
    assert len(rows(db, "SELECT * FROM digest_items")) == 1
    assert len(rows(db, "SELECT * FROM articles WHERE notification_state='pending'")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("time,expected", [("08:19:59", "accepted"), ("08:20:00", "missed")])
async def test_start_deadline_is_exclusive(db, settings, owner, gmail, clock, time, expected):
    await collect_pending(db, owner, 1)
    clock[0] = datetime.fromisoformat("2026-11-27T" + time).replace(tzinfo=KST)
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == expected
    if expected == "missed":
        assert not gmail.calls and rows(db, "SELECT * FROM digests")[0]["snapshot_at"] is None
        assert rows(db, "SELECT * FROM articles")[0]["notification_state"] == "pending"


@pytest.mark.asyncio
async def test_late_receipt_after_deadline_is_preserved(db, settings, owner, gmail, clock):
    await collect_pending(db, owner, 1)
    clock[0] = clock[0].replace(minute=19, second=59)

    async def delay():
        clock[0] += timedelta(minutes=10)

    gmail.send_hook = delay
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == "accepted"
    assert rows(db, "SELECT * FROM digests")[0]["state"] == "accepted"


@pytest.mark.asyncio
async def test_unknown_is_never_retried_or_reselected_even_after_source_deletion(
    db, settings, owner, gmail, clock
):
    store, source, _, _ = await collect_pending(db, owner, 21)
    gmail.outcome = SendOutcome("unknown", "GMAIL_REQUEST_UNCLEAR")
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == "unknown"
    assert all(i["reservation_state"] == "held" for i in rows(db, "SELECT * FROM digest_items"))
    store.change_source(owner, source["id"], 1, delete=True)
    clock[0] += timedelta(days=1)
    mail.enqueue_digest(owner, DAY + timedelta(days=1))
    assert await mail.run_next(owner) == "empty" and len(gmail.calls) == 1
    delivery = rows(db, "SELECT * FROM deliveries")[0]
    assert (
        mail.record_receipt(
            owner,
            delivery["id"],
            delivery["payload_sha256"],
            SendOutcome("accepted", provider_id="late-id"),
        )
        == "accepted"
    )
    assert all(a["notification_state"] == "notified" for a in rows(db, "SELECT * FROM articles"))
    assert (
        mail.record_receipt(
            owner,
            delivery["id"],
            delivery["payload_sha256"],
            SendOutcome("rejected", "LATE_REJECTION"),
        )
        == "accepted"
    )


@pytest.mark.asyncio
async def test_clear_rejection_releases_and_carries_forward_without_same_day_retry(
    db, settings, owner, gmail, clock
):
    await collect_pending(db, owner, 1)
    gmail.outcome = SendOutcome("rejected", "GMAIL_REJECTED", http_status=429)
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == "failed"
    assert rows(db, "SELECT * FROM digest_items")[0]["reservation_state"] == "released"
    assert rows(db, "SELECT * FROM articles")[0]["notification_state"] == "pending"
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) is None
    clock[0] += timedelta(days=1)
    gmail.outcome = None
    mail.enqueue_digest(owner, DAY + timedelta(days=1))
    assert await mail.run_next(owner) == "accepted" and len(gmail.calls) == 2


@pytest.mark.asyncio
async def test_refresh_failure_before_send_does_not_consume_or_leave_reservations(
    db, settings, owner, gmail, clock
):
    await collect_pending(db, owner, 1)
    gmail.error = "GMAIL_REAUTH_REQUIRED"
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == "failed" and not gmail.calls
    assert rows(db, "SELECT * FROM gmail_connections")[0]["state"] == "reauth_required"
    assert rows(db, "SELECT * FROM digest_items")[0]["reservation_state"] == "released"
    assert rows(db, "SELECT * FROM articles")[0]["notification_state"] == "pending"


@pytest.mark.asyncio
async def test_disabled_live_delivery_never_contacts_google(db, settings, owner, gmail, clock):
    await collect_pending(db, owner, 1)
    settings.mail_delivery_enabled = False
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == "failed"
    assert not gmail.refreshes and not gmail.calls
    assert rows(db, "SELECT * FROM digests")[0]["reason_code"] == "DELIVERY_DISABLED"


@pytest.mark.asyncio
async def test_test_email_idempotency_and_independence_from_notifications_and_articles(
    db, settings, owner, gmail, clock
):
    await collect_pending(db, owner, 1)
    execute(db, "UPDATE owner_settings SET notifications_enabled=false")
    mail = service(db, settings, gmail, clock)
    key = uuid4()
    first = mail.enqueue_test(owner, key)
    assert mail.enqueue_test(owner, key) == first
    before = rows(db, "SELECT * FROM articles")
    assert await mail.run_next(owner) == "accepted"
    assert rows(db, "SELECT * FROM articles") == before
    assert not rows(db, "SELECT * FROM digest_items") and not rows(db, "SELECT * FROM digests")
    assert rows(db, "SELECT * FROM deliveries")[0]["kind"] == "test"


@pytest.mark.asyncio
async def test_recording_failure_after_send_recovers_unknown_without_resend(
    db, settings, owner, gmail, clock, monkeypatch
):
    await collect_pending(db, owner, 1)
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    original = mail._record

    def unavailable(*args, **kwargs):
        raise IntegrityError("safe fixture", {}, Exception("DB unavailable"))

    monkeypatch.setattr(mail, "_record", unavailable)
    with pytest.raises(IntegrityError):
        await mail.run_next(owner)
    assert len(gmail.calls) == 1 and rows(db, "SELECT * FROM deliveries")[0]["state"] == "sending"
    execute(
        db,
        "UPDATE job_runs SET lease_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE kind='digest'",
    )
    monkeypatch.setattr(mail, "_record", original)
    assert await mail.run_next(owner) is None
    assert rows(db, "SELECT * FROM deliveries")[0]["state"] == "unknown" and len(gmail.calls) == 1


@pytest.mark.asyncio
async def test_read_only_digest_views_distinguish_null_empty_preview_and_keep_snapshots(
    db, settings, owner, gmail, clock
):
    await collect_pending(db, owner, 1)
    views = DigestViews(db, settings.token_encryption_key)
    preview = views.detail(owner, DAY, clock[0])["data"]
    assert (
        preview["isPreview"] and preview["fullCount"] == 1 and not rows(db, "SELECT * FROM digests")
    )
    past = views.detail(owner, DAY - timedelta(days=1), clock[0])["data"]
    assert past["state"] == "missed" and past["fullCount"] is None
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    await mail.run_next(owner)
    execute(
        db, "UPDATE articles SET title='Changed later',canonical_url='https://blog.example/changed'"
    )
    fixed = views.detail(owner, DAY, clock[0])["data"]
    assert not fixed["isPreview"] and fixed["items"][0]["title"] == "Title 0"
    assert fixed["items"][0]["originalUrl"] != "https://blog.example/changed"


@pytest.mark.parametrize("outcome", ["confirmed_accepted", "confirmed_not_accepted", "unresolved"])
async def test_op01_verification_never_sends_and_only_releases_confirmed(
    db, settings, owner, gmail, clock, outcome
):
    from levelup.verify_delivery import verify

    await collect_pending(db, owner, 2)
    gmail.outcome = SendOutcome("unknown", "GMAIL_REQUEST_UNCLEAR")
    mail = service(db, settings, gmail, clock)
    mail.enqueue_digest(owner, DAY)
    assert await mail.run_next(owner) == "unknown"
    delivery = rows(db, "SELECT id FROM deliveries")[0]["id"]
    state = verify(
        mail,
        owner,
        delivery,
        outcome,
        "Owner matched MIME Message-ID in sent mailbox",
        "verified-provider-id" if outcome == "confirmed_accepted" else None,
    )
    assert (
        state
        == {
            "confirmed_accepted": "accepted",
            "confirmed_not_accepted": "failed",
            "unresolved": "unknown",
        }[outcome]
    )
    assert len(gmail.calls) == 1
    saved = rows(db, "SELECT * FROM deliveries")[0]
    assert saved["verification_outcome"] == outcome and saved["verified_at"]
    items = rows(db, "SELECT reservation_state FROM digest_items")
    expected = {
        "confirmed_accepted": "consumed",
        "confirmed_not_accepted": "released",
        "unresolved": "held",
    }[outcome]
    assert all(i["reservation_state"] == expected for i in items)
    if outcome != "unresolved":
        with pytest.raises(CollectionError, match="INVALID_RECEIPT"):
            verify(mail, owner, delivery, "confirmed_not_accepted", "Second verdict rejected")
