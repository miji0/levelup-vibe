import hmac
import json
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import text
from sqlalchemy.engine import Engine
from starlette.exceptions import HTTPException

from levelup.api.errors import ApiError
from levelup.api.tech import create_tech_router, register_errors
from levelup.core.config import Settings
from levelup.core.sections import home_cards, menu_sections
from levelup.core.security import Cipher, digest, random_token, safe_return_to
from levelup.infra.db import engine_for
from levelup.infra.google import GMAIL_SCOPE, Google
from levelup.infra.public_http import SafePublicHTTP
from levelup.modules.tech.collection import CollectionCore, FeedContract
from levelup.modules.tech.persistence import OWNER_LOCK, locked_connection

SESSION = "levelup_session"
BINDING = "levelup_login"
SESSION_SECONDS = 604800
logger = logging.getLogger("levelup")


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    google: Any = None,
    clock: Callable[[], datetime] | None = None,
    collection_core: CollectionCore | None = None,
    gmail_transport: Any = None,
) -> FastAPI:
    config = settings or Settings()
    now = clock or (lambda: datetime.now(UTC))
    provider = google or Google(config)
    db = engine or (engine_for(config) if config.ready else None)
    cipher = Cipher(config.token_encryption_key) if config.token_encryption_key else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if db is not None and engine is None:
            db.dispose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def database() -> Engine:
        if db is None or cipher is None:
            raise ApiError(503, "SETUP_REQUIRED", "서버 인증·DB 환경 설정이 필요합니다.")
        return db

    def cookie(response, name: str, value: str, age: int):
        response.set_cookie(
            name,
            value,
            max_age=age,
            httponly=True,
            secure=config.secure_cookie,
            samesite="lax",
            path="/",
        )

    def clear_cookie(response, name: str):
        response.delete_cookie(
            name, path="/", secure=config.secure_cookie, httponly=True, samesite="lax"
        )

    def session(request: Request) -> dict[str, Any]:
        token = request.cookies.get(SESSION)
        if not token or len(token) > 256:
            raise ApiError(401, "UNAUTHENTICATED", "Google 로그인이 필요합니다.")
        with database().connect() as conn:
            row = (
                conn.execute(
                    text("""
                SELECT s.*, o.auth_email, o.auth_subject FROM auth_sessions s
                JOIN owner_settings o ON o.id=s.owner_id
                WHERE s.token_hash=:hash AND s.revoked_at IS NULL AND s.expires_at>:now
                    AND o.auth_subject=:subject
            """),
                    {"hash": digest(token), "now": now(), "subject": config.owner_google_sub},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ApiError(401, "UNAUTHENTICATED", "로그인이 만료되었습니다. 다시 로그인해주세요.")
        return dict(row)

    def csrf(request: Request, current: dict[str, Any]):
        if request.headers.get("origin") != config.app_origin or not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), current["csrf_token"]
        ):
            raise ApiError(403, "CSRF_REJECTED", "요청 출처를 확인할 수 없습니다.")

    @app.middleware("http")
    async def privacy(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            # Never log OAuth codes, token responses, SQL parameters or callback query strings.
            logger.error("request_failed request_id=%s", request.state.request_id)
            response = JSONResponse(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "요청을 처리하지 못했습니다.",
                        "requestId": request.state.request_id,
                    }
                },
                status_code=500,
            )
        response.headers.update(
            {
                "Cache-Control": "private, no-store",
                "X-Request-ID": request.state.request_id,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    @app.exception_handler(ApiError)
    async def error(request: Request, exc: ApiError):
        auth_navigation = request.url.path in {
            "/api/auth/signin",
            "/api/auth/callback/google",
        } and "text/html" in request.headers.get("accept", "")
        if auth_navigation:
            allowed_codes = {
                "OWNER_ONLY",
                "OAUTH_STATE_INVALID",
                "OAUTH_CANCELLED",
                "OAUTH_INVALID",
                "OAUTH_UNAVAILABLE",
                "SETUP_REQUIRED",
            }
            code = exc.code if exc.code in allowed_codes else "OAUTH_INVALID"
            # Only an allowlisted UI code crosses the redirect, never the OAuth query or message.
            response: Response = RedirectResponse("/login?error=" + code, status_code=303)
        else:
            response = JSONResponse(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "requestId": request.state.request_id,
                    }
                },
                status_code=exc.status,
            )
        if request.url.path == "/api/auth/callback/google":
            clear_cookie(response, BINDING)
        if exc.fields is not None and isinstance(response, JSONResponse):
            content = json.loads(bytes(response.body))
            content["error"]["fields"] = exc.fields
            response = JSONResponse(content, status_code=exc.status)
        if exc.retry_after is not None:
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return await error(
            request,
            ApiError(
                exc.status_code,
                "NOT_FOUND" if exc.status_code == 404 else "REQUEST_REJECTED",
                "지원하지 않는 요청입니다.",
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return await error(request, ApiError(422, "VALIDATION_ERROR", "요청 형식을 확인해주세요."))

    @app.get("/api/auth/signin")
    async def signin(request: Request, returnTo: str = "/"):
        database()
        if not config.ready:
            raise ApiError(503, "SETUP_REQUIRED", "Google 로그인 환경 설정이 필요합니다.")
        state, binding, verifier, nonce = (random_token() for _ in range(4))
        assert cipher is not None
        with database().begin() as conn:
            owner = conn.execute(
                text("SELECT id FROM owner_settings WHERE auth_subject=:subject"),
                {"subject": config.owner_google_sub},
            ).scalar_one_or_none()
            if owner is None:
                raise ApiError(503, "SETUP_REQUIRED", "소유자 초기 설정을 완료해주세요.")
            first = (
                conn.execute(
                    text("SELECT id FROM gmail_connections WHERE owner_id=:owner"), {"owner": owner}
                ).scalar_one_or_none()
                is None
            )
            # returnTo and nonce share the encrypted, one-use transaction; no new DB fields.
            payload = json.dumps(
                {"verifier": verifier, "nonce": nonce, "returnTo": safe_return_to(returnTo)}
            )
            conn.execute(
                text("""
                INSERT INTO oauth_states VALUES
                (:state, :owner, 'site_login', :binding, :verifier, :nonce, :now, :expiry, NULL)
            """),
                {
                    "state": digest(state),
                    "owner": owner,
                    "binding": digest(binding),
                    "verifier": cipher.encrypt(payload, digest(state)),
                    "nonce": digest(nonce),
                    "now": now(),
                    "expiry": now() + timedelta(minutes=10),
                },
            )
        try:
            url = await provider.authorize(state, nonce, verifier, first)
        except Exception as exc:
            raise ApiError(
                502, "OAUTH_UNAVAILABLE", "Google 로그인에 연결하지 못했습니다."
            ) from exc
        response = RedirectResponse(url, status_code=303)
        cookie(response, BINDING, binding, 600)
        return response

    @app.get("/api/auth/callback/google")
    async def callback(request: Request, state: str = "", code: str = "", error: str = ""):
        binding = request.cookies.get(BINDING, "")
        if not state or not binding or len(state) > 256 or len(binding) > 256:
            raise ApiError(400, "OAUTH_STATE_INVALID", "로그인 요청을 다시 시작해주세요.")
        with database().begin() as conn:
            row = (
                conn.execute(
                    text("""
                UPDATE oauth_states SET consumed_at=:now
                WHERE state_hash=:state AND purpose='site_login'
                  AND session_binding_hash=:binding AND consumed_at IS NULL AND expires_at>:now
                RETURNING *
            """),
                    {"now": now(), "state": digest(state), "binding": digest(binding)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ApiError(400, "OAUTH_STATE_INVALID", "로그인 요청이 만료되었거나 사용되었습니다.")
        if error or not code:
            raise ApiError(400, "OAUTH_CANCELLED", "Google 로그인이 취소되었습니다.")
        assert cipher is not None
        try:
            payload = json.loads(cipher.decrypt(bytes(row["verifier_ciphertext"]), digest(state)))
            if not hmac.compare_digest(digest(payload["nonce"]), row["nonce_hash"]):
                raise ValueError("Nonce mismatch")
            result = await provider.exchange(code, payload["verifier"], payload["nonce"])
        except Exception as exc:
            raise ApiError(400, "OAUTH_INVALID", "Google 인증 결과를 확인할 수 없습니다.") from exc
        claims = result["claims"]
        if (
            claims.get("sub") != config.owner_google_sub
            or claims.get("email_verified") is not True
            or not isinstance(claims.get("email"), str)
            or not claims["email"]
        ):
            raise ApiError(403, "OWNER_ONLY", "등록한 소유자 계정만 사용할 수 있습니다.")
        token, csrf_token, instant = random_token(), random_token(), now()
        with locked_connection(database(), OWNER_LOCK, row["owner_id"]) as conn, conn.begin():
            owner = (
                conn.execute(
                    text("SELECT * FROM owner_settings WHERE id=:id FOR UPDATE"),
                    {"id": row["owner_id"]},
                )
                .mappings()
                .one()
            )
            if owner["auth_subject"] != claims["sub"]:
                raise ApiError(403, "OWNER_ONLY", "등록한 소유자 계정만 사용할 수 있습니다.")
            conn.execute(
                text("""UPDATE owner_settings SET auth_email=:email, updated_at=:now,
                version=version+1 WHERE id=:id"""),
                {"email": claims["email"], "now": instant, "id": owner["id"]},
            )
            existing = (
                conn.execute(
                    text("SELECT * FROM gmail_connections WHERE owner_id=:id"), {"id": owner["id"]}
                )
                .mappings()
                .one_or_none()
            )
            if existing is None:
                scopes = result.get("scope", "").split()
                refresh = result.get("refresh_token")
                connected = GMAIL_SCOPE in scopes and isinstance(refresh, str) and bool(refresh)
                conn.execute(
                    text("""INSERT INTO gmail_connections
                    (id, owner_id, google_subject, email, scopes, state, refresh_token_ciphertext,
                     encryption_key_id, connected_at, created_at, updated_at)
                    VALUES (:id, :owner, :subject, :email, :scopes, :state, :token, :key,
                            :connected, :now, :now)"""),
                    {
                        "id": uuid4(),
                        "owner": owner["id"],
                        "subject": claims["sub"],
                        "email": claims["email"],
                        "scopes": scopes,
                        "state": "connected" if connected else "disconnected",
                        "token": cipher.encrypt(str(refresh), str(owner["id"]))
                        if connected
                        else None,
                        "key": config.token_encryption_key_id if connected else None,
                        "connected": instant if connected else None,
                        "now": instant,
                    },
                )
            elif existing["email"] != claims["email"]:
                conn.execute(
                    text("""UPDATE gmail_connections SET state='reauth_required',
                    updated_at=:now, version=version+1 WHERE owner_id=:owner"""),
                    {"now": instant, "owner": owner["id"]},
                )
            conn.execute(
                text("""INSERT INTO auth_sessions
                (id, owner_id, token_hash, csrf_token, created_at, expires_at)
                VALUES (:id, :owner, :hash, :csrf, :now, :expiry)"""),
                {
                    "id": uuid4(),
                    "owner": owner["id"],
                    "hash": digest(token),
                    "csrf": csrf_token,
                    "now": instant,
                    "expiry": instant + timedelta(seconds=SESSION_SECONDS),
                },
            )
        response = RedirectResponse(safe_return_to(payload["returnTo"]), status_code=303)
        cookie(response, SESSION, token, SESSION_SECONDS)
        clear_cookie(response, BINDING)
        return response

    @app.get("/api/v1/session")
    def get_session(request: Request):
        current = session(request)
        return {
            "data": {
                "owner": {
                    "id": str(current["owner_id"]),
                    "email": current["auth_email"],
                    "provider": "google",
                },
                "csrfToken": current["csrf_token"],
                "sections": menu_sections(),
            }
        }

    @app.post("/api/auth/signout")
    def signout(request: Request):
        current = session(request)
        csrf(request, current)
        with database().begin() as conn:
            conn.execute(
                text("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id"),
                {"now": now(), "id": current["id"]},
            )
        response = JSONResponse({"data": {"signedOut": True}})
        clear_cookie(response, SESSION)
        return response

    @app.get("/api/v1/home")
    def home(request: Request):
        current = session(request)
        from levelup.modules.tech.digests import KST, DigestViews

        view = DigestViews(database(), config.token_encryption_key).detail(
            current["owner_id"], now().astimezone(KST).date(), now(), limit=1
        )["data"]
        return {
            "data": {
                "sections": menu_sections(),
                "tech": {
                    "digestDate": view["date"],
                    "count": view["fullCount"],
                    "isPreview": view["isPreview"],
                    "state": view["state"],
                    "reasonCode": view["reasonCode"],
                },
                "homeCards": home_cards(),
            }
        }

    @app.get("/api/v1/settings")
    def get_settings(request: Request):
        current = session(request)
        with database().connect() as conn:
            owner = (
                conn.execute(
                    text("SELECT * FROM owner_settings WHERE id=:id"), {"id": current["owner_id"]}
                )
                .mappings()
                .one()
            )
            gmail = (
                conn.execute(
                    text("SELECT state, email, version FROM gmail_connections WHERE owner_id=:id"),
                    {"id": current["owner_id"]},
                )
                .mappings()
                .one_or_none()
            )
        return {
            "data": {
                "notificationsEnabled": owner["notifications_enabled"],
                "version": owner["version"],
                "timezone": owner["timezone"],
                "gmail": {
                    "state": gmail["state"] if gmail else "disconnected",
                    "email": current["auth_email"],
                    "version": gmail["version"] if gmail else None,
                },
            }
        }

    @app.post("/api/internal/schedules/{kind}")
    async def scheduled_run(request: Request, kind: str):
        if len(config.cron_secret) < 16 or not hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + config.cron_secret
        ):
            raise ApiError(401, "UNAUTHENTICATED", "스케줄 인증이 필요합니다.")
        if kind not in ("hourly", "final", "digest") or request.query_params:
            raise ApiError(400, "INVALID_REQUEST", "스케줄 형식이 잘못되었습니다.")
        try:
            planned = datetime.fromisoformat(request.headers.get("ce-vssscheduledat", ""))
            if planned.utcoffset() is None:
                raise ValueError
        except ValueError:
            raise ApiError(400, "INVALID_REQUEST", "예약 시각이 필요합니다.") from None
        from levelup.modules.tech.scheduler import tick

        return {
            "data": await tick(database(), config, core, gmail_transport, planned, now(), kind, now)
        }

    core = collection_core or CollectionCore(SafePublicHTTP(), FeedContract(1000, 16))
    register_errors(app, error)
    app.include_router(
        create_tech_router(
            database,
            session,
            csrf,
            now,
            core,
            config.token_encryption_key,
            settings=config,
            google=provider,
            gmail_transport=gmail_transport,
        )
    )
    return app


app = create_app()
