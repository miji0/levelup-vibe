import hmac
import json
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from levelup.api.errors import ApiError
from levelup.api.inputs import body, identifier, version
from levelup.core.security import Cipher, digest, random_token
from levelup.infra.gmail import Gmail
from levelup.infra.google import GMAIL_SCOPE
from levelup.infra.public_http import CollectionError
from levelup.modules.tech.mail import MailService
from levelup.modules.tech.persistence import OWNER_LOCK, locked_connection, prepare_transaction
from levelup.modules.tech.reading import Cursors


def create_mail_router(database, session, current, clock, settings, google, transport) -> APIRouter:
    router = APIRouter()
    cipher = Cipher(settings.token_encryption_key) if settings.token_encryption_key else None

    def mail() -> MailService:
        return MailService(database(), settings, transport, clock)

    @router.patch("/settings")
    async def update_settings(request: Request):
        owner = current(request, "write")
        value = await body(
            request, {"notificationsEnabled": bool}, required={"notificationsEnabled"}
        )
        expected = version(request)
        with locked_connection(database(), OWNER_LOCK, owner) as conn, conn.begin():
            prepare_transaction(conn)
            account = (
                conn.execute(
                    text("SELECT * FROM owner_settings WHERE id=:id FOR UPDATE"), {"id": owner}
                )
                .mappings()
                .one()
            )
            if account["version"] != expected:
                raise CollectionError("VERSION_CONFLICT")
            if value["notificationsEnabled"] and not mail().valid_connection(
                account, mail().connection(conn, owner)
            ):
                raise CollectionError("GMAIL_NOT_CONNECTED")
            updated = (
                conn.execute(
                    text("""UPDATE owner_settings SET notifications_enabled=:enabled,
                version=version+1,updated_at=:at WHERE id=:id
                RETURNING version,notifications_enabled"""),
                    {"enabled": value["notificationsEnabled"], "at": clock(), "id": owner},
                )
                .mappings()
                .one()
            )
            if not value["notificationsEnabled"]:
                prepared = (
                    conn.execute(
                        text(
                            "SELECT * FROM deliveries WHERE owner_id=:id AND kind='digest' "
                            "AND state='prepared' AND submitted_at IS NULL"
                        ),
                        {"id": owner},
                    )
                    .mappings()
                    .all()
                )
                for delivery in prepared:
                    mail()._lock_items(conn, delivery["digest_id"])
                    mail()._cancel(conn, delivery, "NOTIFICATIONS_PAUSED")
            return {
                "data": {
                    "version": updated["version"],
                    "notificationsEnabled": updated["notifications_enabled"],
                }
            }

    @router.post("/tech/test-emails", status_code=202)
    async def test_email(request: Request):
        owner = current(request, "test")
        await body(request, {}, allow_empty=True)
        key = request.headers.get("idempotency-key")
        if key is None:
            raise ApiError(400, "INVALID_REQUEST", "테스트 요청 키가 필요합니다.")
        job = mail().enqueue_test(owner, identifier(key))
        await mail().run_next(owner, job)
        return {"data": {"jobId": str(job), "kind": "test"}}

    @router.get("/tech/deliveries")
    def deliveries(request: Request):
        owner = current(request)
        query = request.query_params
        if query.keys() - {"kind", "state", "cursor", "limit"}:
            raise CollectionError("INVALID_REQUEST")
        kind, state = query.get("kind", "all"), query.get("state")
        if kind not in ("digest", "test", "all") or state not in (
            None,
            "prepared",
            "sending",
            "accepted",
            "failed",
            "unknown",
            "cancelled",
        ):
            raise CollectionError("INVALID_REQUEST")
        try:
            limit = int(query.get("limit", "20"))
            if not 1 <= limit <= 100:
                raise ValueError
        except ValueError:
            raise CollectionError("INVALID_REQUEST") from None
        conditions, params = ["d.owner_id=:owner"], {"owner": owner, "limit": limit + 1}
        scope = {"kind": kind, "state": state, "limit": limit}
        cursors = Cursors(settings.token_encryption_key)
        if kind != "all":
            conditions.append("d.kind=:kind")
            params["kind"] = kind
        if state:
            conditions.append("d.state=:state")
            params["state"] = state
        if query.get("cursor"):
            from datetime import datetime

            try:
                position = cursors.decode(query["cursor"], owner, scope)
                if len(position) != 2:
                    raise ValueError
                at = datetime.fromisoformat(position[0])
                if at.utcoffset() is None:
                    raise ValueError
                params.update(at=at, id=identifier(position[1]))
                conditions.append("(d.prepared_at,d.id)<(:at,:id)")
            except (ValueError, TypeError, ApiError):
                raise CollectionError("INVALID_CURSOR") from None
        with database().connect() as conn:
            rows = (
                conn.execute(
                    text(
                        """SELECT d.id,d.kind,d.state,d.subject,d.prepared_at,
                d.submitted_at,d.accepted_at,d.last_error_code,g.digest_date FROM deliveries d
                LEFT JOIN digests g ON g.id=d.digest_id WHERE """
                        + " AND ".join(conditions)
                        + " ORDER BY d.prepared_at DESC,d.id DESC LIMIT :limit"
                    ),
                    params,
                )
                .mappings()
                .all()
            )
        items = rows[:limit]
        next_cursor = (
            cursors.encode(
                owner, scope, [items[-1]["prepared_at"].isoformat(), str(items[-1]["id"])]
            )
            if len(rows) > limit
            else None
        )
        return {
            "data": {
                "items": [
                    {
                        "id": str(row["id"]),
                        "kind": row["kind"],
                        "state": row["state"],
                        "subject": row["subject"],
                        "preparedAt": row["prepared_at"],
                        "submittedAt": row["submitted_at"],
                        "acceptedAt": row["accepted_at"],
                        "lastErrorCode": row["last_error_code"],
                        "digestDate": row["digest_date"],
                    }
                    for row in items
                ]
            },
            "meta": {"nextCursor": next_cursor, "hasMore": len(rows) > limit},
        }

    @router.get("/tech/deliveries/{delivery_id}")
    def delivery_detail(request: Request, delivery_id: str):
        owner = current(request)
        with database().connect() as conn:
            row = (
                conn.execute(
                    text("""SELECT d.*,g.digest_date FROM deliveries d LEFT JOIN digests g
                ON g.id=d.digest_id WHERE d.id=:id AND d.owner_id=:owner"""),
                    {"id": identifier(delivery_id), "owner": owner},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise CollectionError("NOT_FOUND")
        mapping = {
            "id": "id",
            "kind": "kind",
            "state": "state",
            "providerMessageId": "provider_message_id",
            "mimeMessageId": "mime_message_id",
            "subject": "subject",
            "fromAddress": "from_address",
            "toAddress": "to_address",
            "digestDate": "digest_date",
            "preparedAt": "prepared_at",
            "submittedAt": "submitted_at",
            "acceptedAt": "accepted_at",
            "lastErrorCode": "last_error_code",
            "verificationOutcome": "verification_outcome",
            "verificationNote": "verification_note",
            "verifiedAt": "verified_at",
        }
        return {
            "data": {
                public: str(row[column]) if column == "id" else row[column]
                for public, column in mapping.items()
            }
        }

    @router.post("/integrations/gmail/connect")
    async def connect(request: Request):
        owner = current(request, "gmail")
        await body(request, {}, allow_empty=True)
        current_session = session(request)
        state, nonce, verifier = random_token(), random_token(), random_token()
        assert cipher is not None
        with locked_connection(database(), OWNER_LOCK, owner) as conn, conn.begin():
            connection = mail().connection(conn, owner)
            payload = json.dumps(
                {
                    "nonce": nonce,
                    "verifier": verifier,
                    "version": connection["version"] if connection else 0,
                }
            )
            conn.execute(
                text("""INSERT INTO oauth_states(state_hash,owner_id,purpose,
                session_binding_hash,verifier_ciphertext,nonce_hash,created_at,expires_at)
                VALUES (:state,:owner,'gmail_connect',:binding,:payload,:nonce,:at,:expiry)"""),
                {
                    "state": digest(state),
                    "owner": owner,
                    "binding": current_session["token_hash"],
                    "payload": cipher.encrypt(payload, digest(state)),
                    "nonce": digest(nonce),
                    "at": clock(),
                    "expiry": clock() + timedelta(minutes=10),
                },
            )
        url = await google.connect_authorize(state, nonce, verifier, settings.owner_google_sub)
        return {"data": {"authorizationUrl": url}}

    @router.get("/integrations/gmail/callback")
    async def callback(request: Request, state: str = "", code: str = "", error: str = ""):
        try:
            current_session = session(request)
            if not state or len(state) > 256:
                raise CollectionError("OAUTH_STATE_INVALID")
            with database().begin() as conn:
                saved = (
                    conn.execute(
                        text("""UPDATE oauth_states SET consumed_at=:at WHERE state_hash=:state
                    AND purpose='gmail_connect' AND owner_id=:owner
                    AND session_binding_hash=:binding
                    AND consumed_at IS NULL AND expires_at>:at RETURNING *"""),
                        {
                            "at": clock(),
                            "state": digest(state),
                            "owner": current_session["owner_id"],
                            "binding": current_session["token_hash"],
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
            if saved is None or error or not code:
                raise CollectionError("OAUTH_STATE_INVALID")
            assert cipher is not None
            payload = json.loads(cipher.decrypt(bytes(saved["verifier_ciphertext"]), digest(state)))
            if not hmac.compare_digest(digest(payload["nonce"]), saved["nonce_hash"]):
                raise CollectionError("OAUTH_STATE_INVALID")
            result = await google.connect_exchange(code, payload["verifier"], payload["nonce"])
            current_session = session(request)
            claims = result["claims"]
            if (
                claims.get("sub") != settings.owner_google_sub
                or claims.get("email_verified") is not True
            ):
                raise CollectionError("OWNER_ONLY")
            if (
                claims.get("email") != current_session["auth_email"]
                or GMAIL_SCOPE not in result.get("scope", "").split()
            ):
                raise CollectionError("GMAIL_SCOPE_REQUIRED")
            owner = current_session["owner_id"]
            with locked_connection(database(), OWNER_LOCK, owner) as conn, conn.begin():
                old = mail().connection(conn, owner)
                if (old["version"] if old else 0) != payload["version"]:
                    raise CollectionError("VERSION_CONFLICT")
                refresh = result.get("refresh_token")
                encrypted = (
                    cipher.encrypt(refresh, str(owner))
                    if isinstance(refresh, str) and refresh
                    else (
                        old["refresh_token_ciphertext"]
                        if old is not None
                        and old["state"] == "connected"
                        and old["google_subject"] == claims["sub"]
                        and old["email"] == claims["email"]
                        else None
                    )
                )
                if encrypted is None:
                    raise CollectionError("GMAIL_TOKEN_MISSING")
                conn.execute(
                    text("""INSERT INTO gmail_connections(id,owner_id,google_subject,email,scopes,
                    state,refresh_token_ciphertext,encryption_key_id,connected_at,created_at,updated_at)
                    VALUES (:id,:owner,:subject,:email,:scopes,'connected',:token,:key,:at,:at,:at)
                    ON CONFLICT (owner_id) DO UPDATE SET google_subject=EXCLUDED.google_subject,
                    email=EXCLUDED.email,scopes=EXCLUDED.scopes,state='connected',
                    refresh_token_ciphertext=EXCLUDED.refresh_token_ciphertext,
                    encryption_key_id=EXCLUDED.encryption_key_id,connected_at=EXCLUDED.connected_at,
                    updated_at=EXCLUDED.updated_at,disconnected_at=NULL,last_error_code=NULL,
                    version=gmail_connections.version+1"""),
                    {
                        "id": uuid4(),
                        "owner": owner,
                        "subject": claims["sub"],
                        "email": claims["email"],
                        "scopes": result["scope"].split(),
                        "token": encrypted,
                        "key": settings.token_encryption_key_id,
                        "at": clock(),
                    },
                )
            return RedirectResponse("/settings?gmail=connected", status_code=303)
        except ApiError as exc:
            return RedirectResponse(
                "/login?returnTo=%2Fsettings" if exc.status == 401 else "/settings?gmail=error",
                status_code=303,
            )
        except Exception:
            return RedirectResponse("/settings?gmail=error", status_code=303)

    @router.delete("/integrations/gmail")
    async def disconnect(request: Request):
        owner = current(request, "write")
        expected = version(request)
        token = None
        with locked_connection(database(), OWNER_LOCK, owner) as conn, conn.begin():
            connection = mail().connection(conn, owner)
            if connection is None:
                raise CollectionError("NOT_FOUND")
            if connection["version"] != expected:
                raise CollectionError("VERSION_CONFLICT")
            if cipher is not None and connection["refresh_token_ciphertext"] is not None:
                try:
                    token = cipher.decrypt(
                        bytes(connection["refresh_token_ciphertext"]), str(owner)
                    )
                except Exception:
                    token = None
            conn.execute(
                text("""UPDATE gmail_connections SET state='disconnected',
                refresh_token_ciphertext=NULL,disconnected_at=:at,updated_at=:at,version=version+1
                WHERE owner_id=:owner"""),
                {"owner": owner, "at": clock()},
            )
            prepared = (
                conn.execute(
                    text(
                        "SELECT * FROM deliveries WHERE owner_id=:owner "
                        "AND state='prepared' AND submitted_at IS NULL"
                    ),
                    {"owner": owner},
                )
                .mappings()
                .all()
            )
            for delivery in prepared:
                mail()._lock_items(conn, delivery["digest_id"])
                mail()._cancel(conn, delivery, "CONNECTION_CHANGED")
        confirmed = await (transport or Gmail(settings)).revoke(token) if token else False
        return {
            "data": {
                "state": "disconnected",
                "remoteRevocation": "confirmed" if confirmed else "unconfirmed",
            }
        }

    return router
