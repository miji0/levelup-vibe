"""Read-only KST briefing views. GET never constructs snapshots or starts a job."""

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from levelup.infra.public_http import CollectionError
from levelup.modules.tech.reading import ReadingStore

KST = ZoneInfo("Asia/Seoul")


def schedule(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(8), KST)
    return start, start + timedelta(minutes=20)


def parse_day(value: str, at: datetime) -> date:
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value or day > at.astimezone(KST).date():
            raise ValueError
        return day
    except ValueError:
        raise CollectionError("INVALID_REQUEST") from None


class DigestViews:
    def __init__(self, engine: Engine, secret: str):
        self.engine, self.reading = engine, ReadingStore(engine, secret)

    def status(self, owner_id: UUID, day: date, at: datetime) -> dict:
        with self.engine.connect() as conn:
            created = conn.execute(
                text("SELECT created_at FROM owner_settings WHERE id=:id"), {"id": owner_id}
            ).scalar_one_or_none()
            if created is None:
                raise CollectionError("NOT_FOUND")
            row = (
                conn.execute(
                    text("SELECT * FROM digests WHERE owner_id=:owner AND digest_date=:day"),
                    {"owner": owner_id, "day": day},
                )
                .mappings()
                .one_or_none()
            )
            start, deadline = schedule(day)
            state, reason = "scheduled", None
            if created > start:
                state = "not_scheduled"
            elif at >= deadline:
                state, reason = "missed", "START_DEADLINE_MISSED"
            elif at >= start:
                state = "delayed"
            result: dict[str, Any] = {
                "date": day.isoformat(),
                "state": state,
                "reasonCode": reason,
                "scheduledAt": start,
                "startDeadlineAt": deadline,
                "startedAt": None,
                "snapshotAt": None,
                "delaySeconds": None,
                "fullCount": None,
                "delivery": None,
            }
            if row is not None:
                result.update(
                    state=row["state"],
                    reasonCode=row["reason_code"],
                    startedAt=row["started_at"],
                    snapshotAt=row["snapshot_at"],
                )
                if row["started_at"]:
                    result["delaySeconds"] = max(
                        0, int((row["started_at"] - start).total_seconds())
                    )
                if row["snapshot_at"] is not None:
                    result["fullCount"] = conn.execute(
                        text(
                            "SELECT count(*) FROM digest_items "
                            "WHERE digest_id=:id AND exclusion_reason IS NULL"
                        ),
                        {"id": row["id"]},
                    ).scalar_one()
                delivery = (
                    conn.execute(
                        text("""SELECT id,state,kind,provider_message_id FROM deliveries
                    WHERE digest_id=:id ORDER BY revision DESC LIMIT 1"""),
                        {"id": row["id"]},
                    )
                    .mappings()
                    .one_or_none()
                )
                if delivery:
                    result["delivery"] = {
                        "id": str(delivery["id"]),
                        "state": delivery["state"],
                        "kind": delivery["kind"],
                        "providerMessageId": delivery["provider_message_id"],
                    }
                result["_id"] = row["id"]
            return result

    def detail(self, owner_id: UUID, day: date, at: datetime, **filters) -> dict:
        state = self.status(owner_id, day, at)
        digest_id = state.pop("_id", None)
        preview = state["snapshotAt"] is None and state["state"] in ("scheduled", "delayed")
        if state["snapshotAt"] is not None or preview:
            page = self.reading.articles(
                owner_id,
                digest_id=digest_id if not preview else None,
                eligible_date=day if preview else None,
                **filters,
            )
            if preview:
                full = self.reading.articles(owner_id, eligible_date=day, hidden="include", limit=1)
                state["fullCount"] = full["data"]["filteredCount"]
            state.update(
                items=page["data"]["items"],
                filteredCount=page["data"]["filteredCount"],
                isPreview=preview,
                deliveryState=state["delivery"]["state"] if state["delivery"] else None,
            )
            return {"data": state, "meta": page["meta"]}
        # Validate query shape and scoped cursors even when no snapshot exists.
        self.reading.articles(owner_id, eligible_date=day, **filters)
        state.update(items=[], filteredCount=None, isPreview=False, deliveryState=None)
        return {"data": state, "meta": {"nextCursor": None, "hasMore": False}}

    def history(
        self,
        owner_id: UUID,
        start: date,
        end: date,
        at: datetime,
        *,
        limit=20,
        cursor: str | None = None,
    ) -> dict:
        if (
            start > end
            or (end - start).days >= 31
            or end > at.astimezone(KST).date()
            or not 1 <= limit <= 100
        ):
            raise CollectionError("INVALID_REQUEST")
        scope = {"from": str(start), "to": str(end), "limit": limit}
        after = end + timedelta(days=1)
        if cursor:
            position = self.reading.cursors.decode(cursor, owner_id, scope)
            try:
                if len(position) != 1:
                    raise ValueError
                after = date.fromisoformat(position[0])
            except (ValueError, TypeError):
                raise CollectionError("INVALID_CURSOR") from None
        days = [
            end - timedelta(days=n)
            for n in range((end - start).days + 1)
            if end - timedelta(days=n) < after
        ]
        items = [self.status(owner_id, day, at) for day in days[:limit]]
        for item in items:
            item.pop("_id", None)
        more = len(days) > limit
        next_cursor = (
            self.reading.cursors.encode(owner_id, scope, [items[-1]["date"]]) if more else None
        )
        return {"data": {"items": items}, "meta": {"nextCursor": next_cursor, "hasMore": more}}
