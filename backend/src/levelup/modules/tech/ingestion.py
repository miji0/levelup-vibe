"""Atomic collection persistence: source generation and job lease fence every commit."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from levelup.infra.public_http import CollectionError, PublicResponse
from levelup.modules.tech.eligibility import Eligibility, compute_eligibility
from levelup.modules.tech.feeds import EntryIssue, ParsedEntry, ParsedFeed
from levelup.modules.tech.persistence import CollectionStore, Lease, now, prepare_transaction


def identity_hashes(keys: tuple[tuple[str, str], ...]) -> list[str]:
    return [kind + ":" + hashlib.sha256(value.encode()).hexdigest() for kind, value in keys]


@dataclass(frozen=True)
class Attempt:
    source: RowMapping
    epoch: RowMapping
    baseline: bool
    has_open_issues: bool


def begin_attempt(conn: Connection, lease: Lease) -> Attempt | None:
    with conn.begin():
        prepare_transaction(conn)
        source = CollectionStore._source(conn, lease.owner_id, lease.source_id)
        if source["status"] != "active" or source["generation"] != lease.generation:
            CollectionStore.finish(conn, lease, "skipped", "SOURCE_CHANGED")
            return None
        # A read-only lease check does not invert the source -> articles -> job lock order.
        valid = conn.execute(
            text("""SELECT 1 FROM job_runs WHERE id=:id AND lease_token=:token
            AND state='running' AND lease_expires_at>clock_timestamp() AND source_id=:source
            AND owner_id=:owner AND source_generation=:gen"""),
            {
                "id": lease.id,
                "token": lease.token,
                "source": lease.source_id,
                "owner": lease.owner_id,
                "gen": lease.generation,
            },
        ).scalar_one_or_none()
        if not valid:
            raise CollectionError("STALE_JOB")
        epoch = (
            conn.execute(
                text("""SELECT * FROM subscription_epochs
            WHERE source_id=:source AND generation=:gen AND ended_at IS NULL"""),
                {"source": lease.source_id, "gen": lease.generation},
            )
            .mappings()
            .one()
        )
        baseline = epoch["baseline_completed_at"] is None
        open_issues = conn.execute(
            text("""SELECT EXISTS (SELECT 1 FROM collection_entry_issues
            WHERE source_id=:source AND state='open')"""),
            {"source": lease.source_id},
        ).scalar_one()
        conn.execute(
            text("""UPDATE sources SET last_attempt_at=clock_timestamp(),
            initialization_state=CASE WHEN :baseline THEN 'running' ELSE initialization_state END
            WHERE id=:id"""),
            {"id": lease.source_id, "baseline": baseline},
        )
        return Attempt(source, epoch, baseline, bool(open_issues))


def _record_issue(
    conn: Connection, lease: Lease, attempt: Attempt, issue: EntryIssue, instant: datetime
) -> None:
    hashes = sorted(kind + ":" + value for kind, value in issue.identity_hashes)
    fingerprint = next(
        (value for value in hashes if value.startswith("guid:")),
        next(iter(hashes), "content:" + issue.content_hash),
    )
    conn.execute(
        text("""INSERT INTO collection_entry_issues(id,source_id,epoch_id,
        entry_fingerprint,identity_hashes,first_seen_at,last_seen_at,observed_as_baseline,
        error_code,state,last_job_id) VALUES
        (:id,:source,:epoch,:fingerprint,:hashes,:now,:now,:baseline,:code,'open',:job)
        ON CONFLICT (source_id,epoch_id,entry_fingerprint) DO UPDATE SET
        last_seen_at=EXCLUDED.last_seen_at,error_code=EXCLUDED.error_code,
        state='open',resolved_article_id=NULL,resolved_at=NULL,
        identity_hashes=ARRAY(SELECT DISTINCT unnest(collection_entry_issues.identity_hashes ||
            EXCLUDED.identity_hashes)),last_job_id=EXCLUDED.last_job_id
    """),
        {
            "id": uuid4(),
            "source": lease.source_id,
            "epoch": attempt.epoch["id"],
            "fingerprint": fingerprint,
            "hashes": hashes,
            "now": instant,
            "baseline": attempt.baseline,
            "code": issue.code,
            "job": lease.id,
        },
    )


def _upsert_entry(
    conn: Connection, lease: Lease, attempt: Attempt, entry: ParsedEntry, instant: datetime
) -> UUID:
    hashes = identity_hashes(entry.keys)
    aliases = (
        conn.execute(
            text("""SELECT * FROM article_keys WHERE source_id=:source
        AND key_hash=ANY(CAST(:hashes AS text[]))"""),
            {"source": lease.source_id, "hashes": [value.split(":", 1)[1] for value in hashes]},
        )
        .mappings()
        .all()
    )
    keys = dict(entry.keys)
    matches = set()
    for alias in aliases:
        if alias["key_type"] not in keys:
            continue
        expected = keys[alias["key_type"]]
        if hashlib.sha256(expected.encode()).hexdigest() != alias["key_hash"]:
            continue
        if expected != alias["key_value"]:
            raise CollectionError("IDENTITY_CONFLICT")
        matches.add(alias["article_id"])
    issues = (
        conn.execute(
            text("""SELECT * FROM collection_entry_issues
        WHERE source_id=:source AND (identity_hashes && CAST(:hashes AS text[])
            OR entry_fingerprint=:fingerprint) ORDER BY first_seen_at,id"""),
            {
                "source": lease.source_id,
                "hashes": hashes,
                "fingerprint": "content:" + entry.content_hash,
            },
        )
        .mappings()
        .all()
    )
    matches.update(
        issue["resolved_article_id"] for issue in issues if issue["resolved_article_id"] is not None
    )
    if len(matches) > 1:
        raise CollectionError("IDENTITY_CONFLICT")
    article_id = next(iter(matches), None)
    existing = (
        None
        if article_id is None
        else conn.execute(text("SELECT * FROM articles WHERE id=:id"), {"id": article_id})
        .mappings()
        .one()
    )
    first_seen = (
        existing["first_seen_at"]
        if existing is not None
        else min([instant, *(issue["first_seen_at"] for issue in issues)])
    )
    epoch_id = (
        existing["first_epoch_id"]
        if existing is not None
        else (issues[0]["epoch_id"] if issues else attempt.epoch["id"])
    )
    prior = (
        None
        if existing is None
        else Eligibility(existing["notification_state"], existing["eligible_on"])
    )
    reserved = article_id is not None and bool(
        conn.execute(
            text("""SELECT EXISTS (
        SELECT 1 FROM digest_items WHERE article_id=:id
        AND reservation_state IN ('held','consumed'))"""),
            {"id": article_id},
        ).scalar_one()
    )
    # Prepared items stay mutable; submitted snapshots freeze eligibility.
    if reserved:
        reserved = bool(
            conn.execute(
                text("""SELECT EXISTS (
            SELECT 1 FROM digest_items i LEFT JOIN deliveries d ON d.digest_id=i.digest_id
            WHERE i.article_id=:id AND i.reservation_state IN ('held','consumed') AND
            (i.reservation_state='consumed' OR d.submitted_at IS NOT NULL
                OR d.state IN ('sending','unknown','accepted')))"""),
                {"id": article_id},
            ).scalar_one()
        )
    eligibility = compute_eligibility(
        baseline=attempt.baseline or any(issue["observed_as_baseline"] for issue in issues),
        epoch_kind=attempt.epoch["reason"],
        epoch_started_at=attempt.epoch["started_at"],
        first_seen_at=first_seen,
        published_at=entry.publication.at,
        existing=prior,
        reserved=reserved,
    )
    suppression = (
        "initial_import"
        if eligibility.state == "baseline"
        else ("inactive_period" if eligibility.state == "suppressed" else None)
    )
    if existing is not None and eligibility.state == existing["notification_state"]:
        suppression = existing["suppression_reason"]
    article_id = article_id or uuid4()
    params = {
        "id": article_id,
        "source": lease.source_id,
        "epoch": epoch_id,
        "title": entry.title,
        "url": entry.url,
        "intro": entry.intro,
        "tags": list(entry.tags),
        "published": entry.publication.at,
        "precision": entry.publication.precision,
        "raw": entry.publication.raw,
        "first": first_seen,
        "now": instant,
        "eligible": eligibility.eligible_on,
        "state": eligibility.state,
        "reason": suppression,
    }
    conn.execute(
        text("""INSERT INTO articles(id,source_id,first_epoch_id,title,canonical_url,
        intro,tags,published_at,publication_precision,publication_raw,first_seen_at,last_seen_at,
        metadata_updated_at,eligible_on,notification_state,suppression_reason) VALUES
        (:id,:source,:epoch,:title,:url,:intro,:tags,:published,:precision,:raw,:first,:now,:now,
         :eligible,:state,:reason) ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title,
        canonical_url=EXCLUDED.canonical_url,intro=EXCLUDED.intro,tags=EXCLUDED.tags,
        published_at=EXCLUDED.published_at,publication_precision=EXCLUDED.publication_precision,
        publication_raw=EXCLUDED.publication_raw,last_seen_at=EXCLUDED.last_seen_at,
        metadata_updated_at=EXCLUDED.metadata_updated_at,eligible_on=EXCLUDED.eligible_on,
        notification_state=EXCLUDED.notification_state,suppression_reason=EXCLUDED.suppression_reason
    """),
        params,
    )
    for kind, value in entry.keys:
        row = (
            conn.execute(
                text("""INSERT INTO article_keys(source_id,key_type,key_hash,
            article_id,key_value,created_at) VALUES (:source,:kind,:hash,:article,:value,:now)
            ON CONFLICT (source_id,key_type,key_hash) DO UPDATE SET key_hash=EXCLUDED.key_hash
            RETURNING article_id,key_value"""),
                {
                    "source": lease.source_id,
                    "kind": kind,
                    "hash": hashlib.sha256(value.encode()).hexdigest(),
                    "article": article_id,
                    "value": value,
                    "now": instant,
                },
            )
            .mappings()
            .one()
        )
        if row["article_id"] != article_id or row["key_value"] != value:
            raise CollectionError("IDENTITY_CONFLICT")
    if existing is None:
        conn.execute(
            text("""INSERT INTO article_states(article_id,created_at,updated_at)
            VALUES (:id,:now,:now)"""),
            {"id": article_id, "now": instant},
        )
    for issue in issues:
        conn.execute(
            text("""UPDATE collection_entry_issues SET state='resolved',
            resolved_article_id=:article,resolved_at=COALESCE(resolved_at,:now),
            last_seen_at=:now,last_job_id=:job WHERE id=:id"""),
            {"article": article_id, "now": instant, "job": lease.id, "id": issue["id"]},
        )
    return article_id


def apply_collection(
    conn: Connection,
    lease: Lease,
    attempt: Attempt,
    response: PublicResponse | None = None,
    feed: ParsedFeed | None = None,
    *,
    error_code: str | None = None,
) -> str:
    with conn.begin():
        prepare_transaction(conn)
        source = CollectionStore._source(conn, lease.owner_id, lease.source_id)
        if source["generation"] != lease.generation or source["status"] != "active":
            CollectionStore.finish(conn, lease, "skipped", "SOURCE_CHANGED")
            return "skipped"
        # Serialize with snapshot preparation in the same source -> ordered articles lock order.
        conn.execute(
            text("SELECT id FROM articles WHERE source_id=:id ORDER BY id FOR UPDATE"),
            {"id": lease.source_id},
        ).all()
        instant = now(conn)
        issues = [] if feed is None else list(feed.issues)
        stored = 0
        if error_code is None and response is None:
            raise ValueError("Response or error required")
        if error_code is None and response is not None and response.status == 304:
            if attempt.baseline or attempt.has_open_issues:
                error_code = "BODY_REQUIRED"
            result = "success" if error_code is None else "failed"
        elif error_code is None:
            if feed is None:
                raise ValueError("Parsed feed required")
            for entry in feed.entries:
                try:
                    with conn.begin_nested():
                        _upsert_entry(conn, lease, attempt, entry, instant)
                    stored += 1
                except CollectionError as exc:
                    if exc.code != "IDENTITY_CONFLICT":
                        raise
                    hashes = tuple(
                        (kind, hashlib.sha256(value.encode()).hexdigest())
                        for kind, value in entry.keys
                    )
                    issues.append(EntryIssue(entry.index, exc.code, hashes, entry.content_hash))
            result = "partial" if issues and stored else "failed" if issues else "success"
            if issues:
                error_code = "ENTRY_ISSUES"
        else:
            result = "failed"
        for issue in issues:
            _record_issue(conn, lease, attempt, issue, instant)
        open_issues = conn.execute(
            text("""SELECT count(*) FROM collection_entry_issues
            WHERE source_id=:id AND state='open'"""),
            {"id": lease.source_id},
        ).scalar_one()
        if result == "success" and open_issues:
            result, error_code = "partial", "ENTRY_ISSUES"
        usable = result in ("success", "partial")
        if usable and attempt.baseline:
            conn.execute(
                text(
                    "UPDATE subscription_epochs SET baseline_completed_at=:now "
                    "WHERE id=:id AND baseline_completed_at IS NULL"
                ),
                {"id": attempt.epoch["id"], "now": instant},
            )
        conn.execute(
            text("""UPDATE sources SET last_result=:result,last_error_code=:error,
            last_error_message=NULL,updated_at=:now,
            initialization_state=CASE WHEN :usable THEN 'ready'
                WHEN :baseline THEN 'failed' ELSE initialization_state END,
            last_usable_at=CASE WHEN :usable THEN :now ELSE last_usable_at END,
            last_success_at=CASE WHEN :result='success' THEN :now ELSE last_success_at END,
            etag=CASE WHEN :result='success' AND :body_response THEN :etag ELSE etag END,
            last_modified=CASE WHEN :result='success' AND :body_response THEN :modified
                ELSE last_modified END WHERE id=:id"""),
            {
                "id": lease.source_id,
                "result": result,
                "error": error_code,
                "now": instant,
                "usable": usable,
                "baseline": attempt.baseline,
                "body_response": response is not None and response.status == 200,
                "etag": response.etag if response else None,
                "modified": response.last_modified if response else None,
            },
        )
        CollectionStore.finish(
            conn, lease, "succeeded" if result == "success" else result, error_code
        )
        conn.execute(
            text("""UPDATE job_runs SET result_summary=jsonb_build_object(
            'stored',CAST(:stored AS integer),'issues',CAST(:issues AS integer)) WHERE id=:id"""),
            {"id": lease.id, "stored": stored, "issues": open_issues},
        )
        return result
