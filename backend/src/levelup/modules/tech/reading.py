"""Owner-only reading views and independent manual state, with signed keyset cursors."""

import base64
import hashlib
import hmac
import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from levelup.infra.public_http import CollectionError


def article_json(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "source": {
            "id": str(row["source_id"]),
            "name": row["source_name"],
            "status": row["source_status"],
        },
        "title": row["title"],
        "originalUrl": row["canonical_url"],
        "publishedAt": row["published_at"],
        "publicationPrecision": row["publication_precision"],
        "firstSeenAt": row["first_seen_at"],
        "intro": row["intro"],
        "tags": row["tags"],
        "state": state_json(row),
    }


def state_json(row: RowMapping) -> dict[str, Any]:
    return {
        "isRead": row["is_read"],
        "isSaved": row["is_saved"],
        "isHidden": row["is_hidden"],
        "version": row["version"],
    }


class Cursors:
    def __init__(self, secret: str):
        self.key = hashlib.sha256(secret.encode()).digest()

    def encode(self, owner_id: UUID, scope: dict, position: list) -> str:
        raw = json.dumps(
            [str(owner_id), scope, position], sort_keys=True, separators=(",", ":")
        ).encode()
        signature = hmac.digest(self.key, raw, "sha256")
        return base64.urlsafe_b64encode(signature + raw).decode().rstrip("=")

    def decode(self, cursor: str, owner_id: UUID, scope: dict) -> list:
        try:
            if len(cursor) > 4096:
                raise ValueError
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            signature, payload = raw[:32], raw[32:]
            if not hmac.compare_digest(signature, hmac.digest(self.key, payload, "sha256")):
                raise ValueError
            owner, filters, position = json.loads(payload)
            if owner != str(owner_id) or filters != scope or not isinstance(position, list):
                raise ValueError
            return position
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise CollectionError("INVALID_CURSOR") from None


class ReadingStore:
    def __init__(self, engine: Engine, secret: str):
        self.engine, self.cursors = engine, Cursors(secret)

    def articles(
        self,
        owner_id: UUID,
        *,
        view="all",
        q="",
        source_id: UUID | None = None,
        read="all",
        hidden="exclude",
        cursor: str | None = None,
        limit=20,
        digest_id: UUID | None = None,
        eligible_date: date | None = None,
    ) -> dict:
        if view not in ("all", "saved") or read not in ("all", "read", "unread"):
            raise CollectionError("INVALID_REQUEST")
        if hidden not in ("exclude", "include", "only") or not 1 <= limit <= 100 or len(q) > 200:
            raise CollectionError("INVALID_REQUEST")
        scope = {
            "view": view,
            "q": q,
            "source": str(source_id) if source_id else None,
            "read": read,
            "hidden": hidden,
            "limit": limit,
            "digest": str(digest_id) if digest_id else None,
            "eligible": str(eligible_date) if eligible_date else None,
        }
        conditions = ["s.owner_id=:owner"]
        params: dict[str, Any] = {"owner": owner_id, "limit": limit + 1}
        joins = (
            " FROM articles a JOIN sources s ON s.id=a.source_id "
            "JOIN article_states st ON st.article_id=a.id "
        )
        title, url, source_name = "a.title", "a.canonical_url", "s.name"
        if digest_id:
            joins += "JOIN digest_items di ON di.article_id=a.id AND di.digest_id=:digest "
            params["digest"] = digest_id
            conditions.append("di.exclusion_reason IS NULL")
            title, url, source_name = (
                "di.title_snapshot",
                "di.url_snapshot",
                "di.source_name_snapshot",
            )
        if eligible_date:
            conditions.extend(
                [
                    "s.status='active'",
                    "s.initialization_state='ready'",
                    "a.notification_state='pending'",
                    "a.eligible_on<=:eligible",
                    "NOT EXISTS (SELECT 1 FROM digest_items r WHERE r.article_id=a.id "
                    "AND r.reservation_state IN ('held','consumed'))",
                ]
            )
            params["eligible"] = eligible_date
        if view == "saved":
            conditions.append("st.is_saved")
        if read != "all":
            conditions.append("st.is_read=:read")
            params["read"] = read == "read"
        if hidden != "include":
            conditions.append("st.is_hidden=:hidden")
            params["hidden"] = hidden == "only"
        if q:
            conditions.append(title + " ILIKE :q ESCAPE '\\'")
            params["q"] = (
                "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            )
        if source_id:
            conditions.append("s.id=:source")
            params["source"] = source_id
        count_where = " AND ".join(conditions)
        if cursor:
            try:
                position = self.cursors.decode(cursor, owner_id, scope)
                if len(position) != 2:
                    raise ValueError
                params["after_id"] = UUID(position[1])
                if digest_id:
                    if type(position[0]) is not int or position[0] < 1:
                        raise ValueError
                    params["after_position"] = position[0]
                else:
                    params["after_at"] = datetime.fromisoformat(position[0])
                    if params["after_at"].utcoffset() is None:
                        raise ValueError
            except (ValueError, TypeError, IndexError):
                raise CollectionError("INVALID_CURSOR") from None
            conditions.append(
                "di.sort_position>:after_position"
                if digest_id
                else "(COALESCE(a.published_at,a.first_seen_at),a.id)<(:after_at,:after_id)"
            )
        columns = (
            "SELECT a.id,a.source_id,a.published_at,a.publication_precision,a.first_seen_at,"
            "a.intro,a.tags,"
            + title
            + " AS title,"
            + url
            + " AS canonical_url,"
            + source_name
            + " AS source_name,s.status AS source_status,st.is_read,"
            "st.is_saved,st.is_hidden,st.version" + (",di.sort_position" if digest_id else "")
        )
        order = (
            "di.sort_position"
            if digest_id
            else "COALESCE(a.published_at,a.first_seen_at) DESC,a.id DESC"
        )
        with self.engine.connect() as conn:
            if (
                source_id
                and not conn.execute(
                    text("SELECT 1 FROM sources WHERE id=:id AND owner_id=:o"),
                    {"id": source_id, "o": owner_id},
                ).scalar_one_or_none()
            ):
                raise CollectionError("NOT_FOUND")
            if (
                digest_id
                and not conn.execute(
                    text("SELECT 1 FROM digests WHERE id=:id AND owner_id=:o"),
                    {"id": digest_id, "o": owner_id},
                ).scalar_one_or_none()
            ):
                raise CollectionError("NOT_FOUND")
            count = conn.execute(
                text("SELECT count(*)" + joins + " WHERE " + count_where), params
            ).scalar_one()
            rows = (
                conn.execute(
                    text(
                        columns
                        + joins
                        + " WHERE "
                        + " AND ".join(conditions)
                        + " ORDER BY "
                        + order
                        + " LIMIT :limit"
                    ),
                    params,
                )
                .mappings()
                .all()
            )
        more, items = len(rows) > limit, rows[:limit]
        next_cursor = None
        if more:
            last = items[-1]
            key = (
                last["sort_position"]
                if digest_id
                else (last["published_at"] or last["first_seen_at"]).isoformat()
            )
            next_cursor = self.cursors.encode(owner_id, scope, [key, str(last["id"])])
        return {
            "data": {"items": [article_json(row) for row in items], "filteredCount": count},
            "meta": {"nextCursor": next_cursor, "hasMore": more},
        }

    def set_state(self, owner_id: UUID, article_id: UUID, version: int, changes: dict) -> dict:
        mapping = {
            "isRead": ("is_read", "read_at"),
            "isSaved": ("is_saved", "saved_at"),
            "isHidden": ("is_hidden", "hidden_at"),
        }
        if not changes or any(k not in mapping or type(v) is not bool for k, v in changes.items()):
            raise CollectionError("INVALID_REQUEST")
        with self.engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '2s'"))
            exists = conn.execute(
                text("""SELECT 1 FROM articles a JOIN sources s ON s.id=a.source_id
                WHERE a.id=:article AND s.owner_id=:owner"""),
                {"article": article_id, "owner": owner_id},
            ).scalar_one_or_none()
            if not exists:
                raise CollectionError("NOT_FOUND")
            row = (
                conn.execute(
                    text("SELECT * FROM article_states WHERE article_id=:id FOR UPDATE"),
                    {"id": article_id},
                )
                .mappings()
                .one_or_none()
            )
            if (row["version"] if row else 0) != version:
                raise CollectionError("VERSION_CONFLICT")
            if row is None:
                conn.execute(
                    text("""INSERT INTO article_states(article_id,created_at,updated_at,version)
                    VALUES (:id,clock_timestamp(),clock_timestamp(),0)"""),
                    {"id": article_id},
                )
            assignments = ["updated_at=clock_timestamp()", "version=version+1"]
            params: dict[str, Any] = {"id": article_id}
            for key, value in changes.items():
                column, time_column = mapping[key]
                assignments.extend(
                    [
                        f"{column}=:{column}",
                        f"{time_column}=CASE WHEN :{column} THEN clock_timestamp() ELSE NULL END",
                    ]
                )
                params[column] = value
            updated = (
                conn.execute(
                    text(
                        "UPDATE article_states SET "
                        + ",".join(assignments)
                        + " WHERE article_id=:id RETURNING *"
                    ),
                    params,
                )
                .mappings()
                .one()
            )
            return state_json(updated)
