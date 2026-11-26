from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from levelup.infra.public_http import CollectionError, PublicResponse
from levelup.migrate import migrate
from levelup.modules.tech.collection import FeedOption
from levelup.modules.tech.feeds import parse_feed
from levelup.modules.tech.persistence import CollectionStore, SourceAlreadyExists
from levelup.modules.tech.worker import CollectionWorker

URL = "https://blog.example/feed"


@pytest.fixture
def store(db):
    return CollectionStore(db)


@pytest.fixture
def owner(db):
    with db.connect() as conn:
        return conn.execute(text("SELECT id FROM owner_settings")).scalar_one()


def rows(db, sql, **params):
    with db.connect() as conn:
        return conn.execute(text(sql), params).mappings().all()


def execute(db, sql, **params):
    with db.begin() as conn:
        conn.execute(text(sql), params)


def add(store, owner, url=URL):
    return store.add_source(owner, url, FeedOption("Blog", url, "success"))


def rss(*entries):
    return ("<rss><channel><title>Blog</title>" + "".join(entries) + "</channel></rss>").encode()


def item(key="a", title="Title", path=None, published="2026-11-25T00:00:00Z"):
    path = path or key
    return (
        f"<item><guid isPermaLink='false'>{key}</guid><title>{title}</title>"
        f"<link>https://blog.example/{path}</link><pubDate>{published}</pubDate></item>"
    )


class Core:
    def __init__(self, body=None):
        self.body = body if body is not None else rss()
        self.error = None
        self.hook = None
        self.calls = []
        self.etag = '"first"'
        self.status = 200

    async def collect(self, url, **kwargs):
        self.calls.append(kwargs)
        if self.hook:
            self.hook()
        if self.error:
            raise CollectionError(self.error)
        response = PublicResponse(url, self.status, self.body, "application/rss+xml", self.etag)
        return response, None if self.status == 304 else parse_feed(self.body, url, max_items=1000)


@pytest.mark.asyncio
async def test_add_is_atomic_and_baseline_never_notifies(store, owner, db):
    source, job = add(store, owner)
    assert source["initialization_state"] == "pending"
    assert rows(db, "SELECT * FROM subscription_epochs")[0]["reason"] == "first_add"
    assert rows(db, "SELECT * FROM job_runs")[0]["id"] == job
    assert await CollectionWorker(store, Core(rss(item()))).run_next(owner) == "success"
    article = rows(db, "SELECT * FROM articles")[0]
    assert article["notification_state"] == "baseline" and article["eligible_on"] is None
    assert rows(db, "SELECT * FROM article_states")[0]["is_read"] is False
    saved = rows(db, "SELECT * FROM sources")[0]
    assert saved["initialization_state"] == "ready" and saved["last_success_at"]
    assert rows(db, "SELECT * FROM job_runs")[0]["state"] == "succeeded"


def test_duplicate_and_concurrent_registration_return_existing_id(store, owner, db):
    def create():
        try:
            return add(store, owner)[0]["id"]
        except SourceAlreadyExists as error:
            return error.existing_source_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: create(), range(2)))
    assert ids[0] == ids[1]
    assert len(rows(db, "SELECT id FROM sources")) == 1
    assert len(rows(db, "SELECT id FROM subscription_epochs")) == 1
    assert len(rows(db, "SELECT id FROM job_runs")) == 1
    different, _ = add(store, owner, URL + "-other")
    assert different["id"] != ids[0]


def test_owner_scope_and_version_and_repeat_toggle(store, owner, db):
    source, _ = add(store, owner)
    with pytest.raises(CollectionError, match="NOT_FOUND"):
        store.change_source(uuid4(), source["id"], 1, enabled=False)
    with pytest.raises(CollectionError, match="VERSION_CONFLICT"):
        store.change_source(owner, source["id"], 999, enabled=False)
    paused, job = store.change_source(owner, source["id"], 1, enabled=False)
    assert paused["status"] == "paused" and job is None
    again, _ = store.change_source(owner, source["id"], paused["version"], enabled=False)
    assert again["generation"] == paused["generation"]
    resumed, _ = store.change_source(owner, source["id"], paused["version"], enabled=True)
    assert resumed["generation"] == 3 and resumed["initialization_state"] == "pending"
    epochs = rows(db, "SELECT * FROM subscription_epochs ORDER BY started_at")
    assert [row["reason"] for row in epochs] == ["first_add", "resume"]
    assert epochs[0]["ended_at"] and epochs[1]["ended_at"] is None
    assert not store.list_sources(uuid4())


@pytest.mark.asyncio
async def test_delete_readd_preserves_articles_and_manual_state(store, owner, db):
    source, _ = add(store, owner)
    worker = CollectionWorker(store, Core(rss(item())))
    await worker.run_next(owner)
    article = rows(db, "SELECT * FROM articles")[0]
    execute(
        db,
        "UPDATE article_states SET is_saved=true,saved_at=clock_timestamp(),"
        "is_read=true,read_at=clock_timestamp() WHERE article_id=:id",
        id=article["id"],
    )
    deleted, _ = store.change_source(owner, source["id"], 1, delete=True)
    repeated, _ = store.change_source(owner, source["id"], 999, delete=True)
    assert repeated["generation"] == deleted["generation"]
    assert store.list_sources(owner) == []
    restored, _ = add(store, owner)
    assert restored["id"] == source["id"] and restored["generation"] == 3
    await worker.run_next(owner)
    assert len(rows(db, "SELECT id FROM articles")) == 1
    state = rows(db, "SELECT * FROM article_states")[0]
    assert state["is_saved"] and state["is_read"]
    assert (
        rows(db, "SELECT * FROM subscription_epochs ORDER BY started_at")[-1]["reason"] == "readd"
    )


@pytest.mark.asyncio
async def test_normal_collection_updates_guid_or_url_without_duplicate_notification(
    store, owner, db
):
    source, _ = add(store, owner)
    core = Core()
    worker = CollectionWorker(store, core)
    await worker.run_next(owner)
    core.body = rss(item())
    store.enqueue(owner, source["id"], "slot1")
    assert await worker.run_next(owner) == "success"
    original = rows(db, "SELECT * FROM articles")[0]
    assert original["notification_state"] == "pending"
    core.body = rss(item("new-guid", "Changed", path="a"))
    store.enqueue(owner, source["id"], "slot2")
    await worker.run_next(owner)
    current = rows(db, "SELECT * FROM articles")[0]
    assert current["id"] == original["id"] and current["first_seen_at"] == original["first_seen_at"]
    assert current["title"] == "Changed"
    assert len(rows(db, "SELECT * FROM article_keys")) == 3
    assert (
        store.enqueue(owner, source["id"], "slot2")
        == rows(db, "SELECT id FROM job_runs WHERE dedup_key LIKE '%slot2'")[0]["id"]
    )


@pytest.mark.asyncio
async def test_identity_conflict_is_quarantined_without_merging_or_losing_other_entries(
    store, owner, db
):
    source, _ = add(store, owner)
    core = Core(rss(item("a"), item("b")))
    worker = CollectionWorker(store, core)
    await worker.run_next(owner)
    core.body = rss(item("a", "Conflict", path="b"), item("c"))
    store.enqueue(owner, source["id"], "normal")
    assert await worker.run_next(owner) == "partial"
    assert len(rows(db, "SELECT * FROM articles")) == 3
    assert {row["title"] for row in rows(db, "SELECT * FROM articles")} == {"Title"}
    issue = rows(db, "SELECT * FROM collection_entry_issues")[0]
    assert issue["error_code"] == "IDENTITY_CONFLICT" and issue["state"] == "open"
    assert rows(db, "SELECT * FROM sources")[0]["etag"] == '"first"'


@pytest.mark.asyncio
async def test_partial_baseline_recovery_preserves_initial_marker_and_first_seen(store, owner, db):
    source, _ = add(store, owner)
    core = Core(rss(item("good"), item("recover", title="")))
    worker = CollectionWorker(store, core)
    assert await worker.run_next(owner) == "partial"
    issue = rows(db, "SELECT * FROM collection_entry_issues")[0]
    assert issue["observed_as_baseline"]
    assert rows(db, "SELECT * FROM sources")[0]["last_success_at"] is None
    assert rows(db, "SELECT * FROM subscription_epochs")[0]["baseline_completed_at"]
    core.body = rss(item("good"), item("recover"), item("new"))
    store.enqueue(owner, source["id"], "next")
    assert await worker.run_next(owner) == "success"
    assert core.calls[-1]["has_open_issues"] is True
    recovered = rows(
        db,
        "SELECT a.* FROM articles a JOIN article_keys k ON k.article_id=a.id "
        "WHERE k.key_type='guid' AND k.key_value='recover'",
    )[0]
    assert recovered["notification_state"] == "baseline"
    assert recovered["first_seen_at"] == issue["first_seen_at"]
    resolved = rows(db, "SELECT * FROM collection_entry_issues")[0]
    assert resolved["state"] == "resolved" and resolved["observed_as_baseline"]
    fresh = rows(
        db,
        "SELECT a.* FROM articles a JOIN article_keys k ON k.article_id=a.id "
        "WHERE k.key_type='guid' AND k.key_value='new'",
    )[0]
    assert fresh["notification_state"] == "pending"


@pytest.mark.asyncio
async def test_repeated_invalid_baseline_stays_failed_and_deduplicates_issues(store, owner, db):
    source, _ = add(store, owner)
    core = Core(rss(item(title="")))
    worker = CollectionWorker(store, core)
    assert await worker.run_next(owner) == "failed"
    first = rows(db, "SELECT * FROM collection_entry_issues")[0]
    store.enqueue(owner, source["id"], "retry-slot")
    assert await worker.run_next(owner) == "failed"
    issues = rows(db, "SELECT * FROM collection_entry_issues")
    assert len(issues) == 1 and issues[0]["first_seen_at"] == first["first_seen_at"]
    assert rows(db, "SELECT * FROM subscription_epochs")[0]["baseline_completed_at"] is None
    assert rows(db, "SELECT * FROM sources")[0]["initialization_state"] == "failed"


@pytest.mark.asyncio
async def test_failure_of_one_source_does_not_stop_next_source(store, owner, db):
    first, _ = add(store, owner)
    second, _ = add(store, owner, URL + "2")
    core = Core()
    core.error = "FETCH_TIMEOUT"
    worker = CollectionWorker(store, core)
    assert await worker.run_next(owner) == "failed"
    core.error = None
    assert await worker.run_next(owner) == "success"
    assert (
        rows(db, "SELECT * FROM sources WHERE id=:id", id=first["id"])[0]["last_result"] == "failed"
    )
    assert (
        rows(db, "SELECT * FROM sources WHERE id=:id", id=second["id"])[0]["last_result"]
        == "success"
    )


@pytest.mark.asyncio
async def test_source_deleted_during_http_cannot_commit_old_generation(store, owner, db):
    source, _ = add(store, owner)
    core = Core(rss(item()))
    core.hook = lambda: store.change_source(owner, source["id"], 1, delete=True)
    assert await CollectionWorker(store, core).run_next(owner) == "skipped"
    assert not rows(db, "SELECT * FROM articles")
    assert rows(db, "SELECT * FROM sources")[0]["status"] == "deleted"
    assert rows(db, "SELECT * FROM job_runs")[0]["result_code"] == "SOURCE_CHANGED"


@pytest.mark.asyncio
async def test_expired_and_reclaimed_lease_cannot_commit_or_heartbeat(store, owner, db):
    source, _ = add(store, owner)
    lease = store.claim(owner)
    execute(
        db,
        "UPDATE job_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id",
        id=lease.id,
    )
    assert not store.heartbeat(lease)
    replacement = store.claim(owner)
    assert replacement.id == lease.id and replacement.token != lease.token
    assert await CollectionWorker(store, Core(rss(item()))).run(lease) == "stale"
    assert not rows(db, "SELECT * FROM articles")
    assert await CollectionWorker(store, Core(rss(item()))).run(replacement) == "success"
    assert rows(db, "SELECT * FROM job_runs")[0]["attempt_count"] == 2


def test_claim_enforces_two_collection_slots_and_separates_mail_jobs(store, owner, db):
    for index in range(3):
        add(store, owner, URL + str(index))
    first, second = store.claim(owner), store.claim(owner)
    assert first and second and first.id != second.id
    assert store.claim(owner) is None
    assert store.heartbeat(first)
    with db.begin() as conn:
        CollectionStore.finish(conn, first, "failed", "TEST_FAILURE")
    assert store.claim(owner) is not None


@pytest.mark.asyncio
async def test_malformed_database_entry_rolls_back_whole_attempt(store, owner, db):
    source, _ = add(store, owner)
    core = Core(rss(item("a"), item("b")))
    parsed = parse_feed(core.body, URL, max_items=2)
    broken = replace(parsed, entries=(parsed.entries[0], replace(parsed.entries[1], title=None)))

    async def collect(url, **kwargs):
        return PublicResponse(url, 200, core.body, "text/xml"), broken

    core.collect = collect
    assert await CollectionWorker(store, core).run_next(owner) == "failed"
    assert rows(db, "SELECT * FROM job_runs")[0]["result_code"] == "STORE_FAILURE"
    assert not rows(db, "SELECT * FROM articles")
    assert not rows(db, "SELECT * FROM article_keys")
    assert not rows(db, "SELECT * FROM collection_entry_issues")
    assert rows(db, "SELECT * FROM job_runs")[0]["state"] != "succeeded"


def test_migration_repeat_and_constraints(db, store, owner):
    directory = Path(__file__).resolve().parents[2] / "db" / "migrations"
    migrate(db, directory)
    assert len(rows(db, "SELECT * FROM schema_migrations")) == len(list(directory.glob("*.sql")))
    source, _ = add(store, owner)
    with pytest.raises(IntegrityError):
        execute(
            db,
            "INSERT INTO subscription_epochs(id,source_id,generation,started_at,reason) "
            "VALUES (:id,:source,10,clock_timestamp(),'resume')",
            id=uuid4(),
            source=source["id"],
        )


def reserve(db, owner, article_id, state):
    digest_id, delivery_id, connection_id = uuid4(), uuid4(), uuid4()
    execute(
        db,
        """INSERT INTO gmail_connections(id,owner_id,google_subject,email,scopes,state,
        refresh_token_ciphertext,created_at,updated_at) VALUES
        (:id,:owner,'owner-123','owner@example.com',ARRAY['gmail.send'],'connected',
         :token,clock_timestamp(),clock_timestamp())""",
        id=connection_id,
        owner=owner,
        token=b"encrypted-fixture",
    )
    execute(
        db,
        """INSERT INTO digests(id,owner_id,digest_date,state,scheduled_at,
        start_deadline_at,started_at,snapshot_at,created_at,updated_at) VALUES
        (:id,:owner,current_date,'ready',clock_timestamp(),clock_timestamp()+interval '20 minutes',
         clock_timestamp(),clock_timestamp(),clock_timestamp(),clock_timestamp())""",
        id=digest_id,
        owner=owner,
    )
    execute(
        db,
        """INSERT INTO digest_items(digest_id,article_id,title_snapshot,url_snapshot,
        source_name_snapshot,sort_position,shown_in_email,reservation_state,created_at)
        VALUES (:digest,:article,'Original title','https://blog.example/a','Blog',1,true,
        :reservation,clock_timestamp())""",
        digest=digest_id,
        article=article_id,
        reservation="consumed" if state == "accepted" else "held",
    )
    execute(
        db,
        """INSERT INTO deliveries(id,owner_id,kind,digest_id,gmail_connection_id,
        connection_version,revision,request_key,mime_message_id,from_address,to_address,
        subject,mime_payload,payload_sha256,state,prepared_at,submitted_at) VALUES
        (:id,:owner,'digest',:digest,:connection,1,1,:key,:message,'owner@example.com',
         'owner@example.com','Fixture',:payload,'fixture-hash',:state,clock_timestamp(),:submitted)""",
        id=delivery_id,
        owner=owner,
        digest=digest_id,
        connection=connection_id,
        key=str(uuid4()),
        message=str(uuid4()),
        payload=b"fixture",
        state=state,
        submitted=None if state == "prepared" else datetime.now(UTC),
    )
    return digest_id, delivery_id


async def pending_article(store, owner, db):
    source, _ = add(store, owner)
    core = Core()
    worker = CollectionWorker(store, core)
    await worker.run_next(owner)
    core.body = rss(item())
    store.enqueue(owner, source["id"], "pending")
    await worker.run_next(owner)
    return source, core, worker, rows(db, "SELECT * FROM articles")[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["prepared", "sending", "unknown", "accepted"])
async def test_subscription_change_cancels_only_unsubmitted_reservations(store, owner, db, state):
    source, core, worker, article = await pending_article(store, owner, db)
    reserve(db, owner, article["id"], state)
    store.change_source(owner, source["id"], 1, enabled=False)
    current = rows(db, "SELECT * FROM articles")[0]
    reservation = rows(db, "SELECT * FROM digest_items")[0]
    delivery = rows(db, "SELECT * FROM deliveries")[0]
    if state == "prepared":
        assert current["notification_state"] == "suppressed" and current["eligible_on"] is None
        assert reservation["reservation_state"] == "released"
        assert reservation["exclusion_reason"] == "source_disabled"
        assert delivery["state"] == "cancelled"
    else:
        assert current["notification_state"] == "pending"
        assert current["eligible_on"] == article["eligible_on"]
        assert reservation["reservation_state"] == ("consumed" if state == "accepted" else "held")
        assert delivery["state"] == state and reservation["exclusion_reason"] is None
    assert reservation["title_snapshot"] == "Original title"


@pytest.mark.asyncio
async def test_publication_correction_preserves_submitted_reservation(store, owner, db):
    source, core, worker, article = await pending_article(store, owner, db)
    reserve(db, owner, article["id"], "unknown")
    future = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    core.body = rss(item(title="Corrected", published=future))
    store.enqueue(owner, source["id"], "corrected")
    assert await worker.run_next(owner) == "success"
    current = rows(db, "SELECT * FROM articles")[0]
    assert current["title"] == "Corrected" and current["eligible_on"] == article["eligible_on"]
    assert rows(db, "SELECT * FROM digest_items")[0]["title_snapshot"] == "Original title"
    assert rows(db, "SELECT * FROM deliveries")[0]["state"] == "unknown"


@pytest.mark.asyncio
async def test_prepared_pending_correction_recalculates_without_rewriting_snapshot(
    store, owner, db
):
    source, core, worker, article = await pending_article(store, owner, db)
    reserve(db, owner, article["id"], "prepared")
    future = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    core.body = rss(item(published=future))
    store.enqueue(owner, source["id"], "corrected")
    await worker.run_next(owner)
    assert rows(db, "SELECT * FROM articles")[0]["eligible_on"] > article["eligible_on"]
    assert rows(db, "SELECT * FROM digest_items")[0]["title_snapshot"] == "Original title"


@pytest.mark.asyncio
async def test_resume_does_not_revive_suppressed_or_notify_inactive_period(store, owner, db):
    source, core, worker, original = await pending_article(store, owner, db)
    paused, _ = store.change_source(owner, source["id"], 1, enabled=False)
    resumed, _ = store.change_source(owner, source["id"], paused["version"], enabled=True)
    await worker.run_next(owner)  # resumed baseline contains only the old, already suppressed item
    epoch = rows(db, "SELECT * FROM subscription_epochs WHERE ended_at IS NULL")[0]
    fresh_date = (epoch["started_at"] + timedelta(seconds=1)).isoformat()
    core.body = rss(item(), item("inactive"), item("fresh", published=fresh_date))
    store.enqueue(owner, resumed["id"], "after-resume")
    await worker.run_next(owner)
    results = rows(
        db,
        "SELECT a.*,k.key_value FROM articles a JOIN article_keys k ON k.article_id=a.id "
        "WHERE k.key_type='guid'",
    )
    states = {row["key_value"]: row["notification_state"] for row in results}
    assert states == {"a": "suppressed", "inactive": "suppressed", "fresh": "pending"}


@pytest.mark.asyncio
async def test_expiry_during_fetch_rolls_back_success_and_metadata(store, owner, db):
    source, _ = add(store, owner)
    lease = store.claim(owner)
    core = Core(rss(item()))
    core.hook = lambda: execute(
        db,
        "UPDATE job_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id",
        id=lease.id,
    )
    assert await CollectionWorker(store, core).run(lease) == "stale"
    assert not rows(db, "SELECT * FROM articles")
    assert rows(db, "SELECT * FROM sources")[0]["last_success_at"] is None
    assert rows(db, "SELECT * FROM subscription_epochs")[0]["baseline_completed_at"] is None


@pytest.mark.asyncio
async def test_normal_304_keeps_metadata_and_success_timestamp(store, owner, db):
    source, _ = add(store, owner)
    core = Core(rss(item()))
    worker = CollectionWorker(store, core)
    await worker.run_next(owner)
    before = rows(db, "SELECT * FROM articles")[0]
    core.status = 304
    store.enqueue(owner, source["id"], "not-modified")
    assert await worker.run_next(owner) == "success"
    assert rows(db, "SELECT * FROM articles")[0] == before
    assert rows(db, "SELECT * FROM sources")[0]["last_success_at"]


@pytest.mark.asyncio
async def test_registration_validates_selection_before_any_database_write(store, owner, db):
    from levelup.modules.tech.persistence import SubscriptionService

    class InvalidSelection:
        async def validate_selection(self, input_url, collection_url):
            raise CollectionError("INVALID_SELECTION")

    service = SubscriptionService(store, InvalidSelection())
    with pytest.raises(CollectionError, match="INVALID_SELECTION"):
        await service.add(owner, URL, "https://other.example/feed")
    assert not rows(db, "SELECT * FROM sources")
    assert not rows(db, "SELECT * FROM job_runs")


@pytest.mark.asyncio
async def test_unresolved_issue_absent_from_next_feed_does_not_become_full_success(
    store, owner, db
):
    source, _ = add(store, owner)
    core = Core(rss(item("good"), item("broken", title="")))
    worker = CollectionWorker(store, core)
    assert await worker.run_next(owner) == "partial"
    core.body, core.etag = rss(item("good")), '"new"'
    store.enqueue(owner, source["id"], "still-missing")
    assert await worker.run_next(owner) == "partial"
    current = rows(db, "SELECT * FROM sources")[0]
    assert current["last_success_at"] is None and current["etag"] is None
    assert store.list_sources(owner)[0]["open_issue_count"] == 1


@pytest.mark.asyncio
async def test_successful_200_without_validator_clears_old_validator(store, owner, db):
    source, _ = add(store, owner)
    core = Core()
    worker = CollectionWorker(store, core)
    await worker.run_next(owner)
    assert rows(db, "SELECT * FROM sources")[0]["etag"] == '"first"'
    core.etag = None
    store.enqueue(owner, source["id"], "no-etag")
    await worker.run_next(owner)
    assert rows(db, "SELECT * FROM sources")[0]["etag"] is None


def test_concurrent_claims_do_not_exceed_global_collection_slots(store, owner, db):
    for index in range(4):
        add(store, owner, URL + str(index))
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = list(pool.map(lambda _: store.claim(owner), range(4)))
    active = [lease for lease in claimed if lease is not None]
    assert len(active) == 2 and len({lease.id for lease in active}) == 2


def test_mail_jobs_are_never_recovered_or_claimed_as_collection(store, owner, db):
    source, _ = add(store, owner)
    job_id = uuid4()
    execute(
        db,
        """INSERT INTO job_runs(id,owner_id,kind,dedup_key,state,available_at,
        lease_token,lease_expires_at) VALUES (:id,:owner,'digest','mail-key','running',
        clock_timestamp(),:token,clock_timestamp()-interval '1 minute')""",
        id=job_id,
        owner=owner,
        token=uuid4(),
    )
    assert store.claim(owner).source_id == source["id"]
    assert rows(db, "SELECT * FROM job_runs WHERE id=:id", id=job_id)[0]["state"] == "running"


def test_heartbeat_cannot_revive_terminal_job(store, owner, db):
    add(store, owner)
    lease = store.claim(owner)
    with db.begin() as conn:
        store.finish(conn, lease, "succeeded")
    assert not store.heartbeat(lease)


@pytest.mark.asyncio
async def test_failed_fetch_releases_dedicated_source_session_lock(store, owner, db):
    from levelup.modules.tech.persistence import SOURCE_LOCK, lock_key

    source, _ = add(store, owner)
    core = Core()
    core.error = "FETCH_TIMEOUT"
    assert await CollectionWorker(store, core).run_next(owner) == "failed"
    with db.connect() as conn:
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:ns,:key)"),
            {"ns": SOURCE_LOCK, "key": lock_key(source["id"])},
        ).scalar_one()
        assert acquired
        conn.execute(
            text("SELECT pg_advisory_unlock(:ns,:key)"),
            {"ns": SOURCE_LOCK, "key": lock_key(source["id"])},
        )
        conn.commit()


def test_upgrade_from_identity_only_keeps_owner_session_and_checksum(db, settings, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from levelup.infra.db import ensure_owner

    schema = "upgrade_" + uuid4().hex
    with db.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    legacy = create_engine(
        db.url, poolclass=NullPool, connect_args={"options": "-csearch_path=" + schema}
    )
    directory = Path(__file__).resolve().parents[2] / "db" / "migrations"
    (tmp_path / "001_identity.sql").write_bytes((directory / "001_identity.sql").read_bytes())
    try:
        migrate(legacy, tmp_path)
        ensure_owner(legacy, settings)
        original = rows(legacy, "SELECT * FROM owner_settings")[0]
        session_id = uuid4()
        execute(
            legacy,
            """INSERT INTO auth_sessions(id,owner_id,token_hash,csrf_token,
            created_at,expires_at) VALUES (:id,:owner,'hashed-fixture','csrf-fixture',
            '2026-11-26T00:00:00Z','2026-12-03T00:00:00Z')""",
            id=session_id,
            owner=original["id"],
        )
        checksum = rows(legacy, "SELECT checksum FROM schema_migrations")[0]["checksum"]
        migrate(legacy, directory)
        assert rows(legacy, "SELECT * FROM owner_settings")[0] == original
        assert rows(legacy, "SELECT id FROM auth_sessions")[0]["id"] == session_id
        assert (
            rows(legacy, "SELECT checksum FROM schema_migrations WHERE name='001_identity.sql'")[0][
                "checksum"
            ]
            == checksum
        )
        assert len(rows(legacy, "SELECT * FROM schema_migrations")) == len(
            list(directory.glob("*.sql"))
        )
    finally:
        legacy.dispose()
        with db.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
