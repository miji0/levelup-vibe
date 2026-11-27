from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from levelup.api.errors import ApiError
from levelup.api.inputs import body, identifier, version
from levelup.infra.public_http import CollectionError
from levelup.modules.tech.collection import CollectionCore
from levelup.modules.tech.digests import KST, DigestViews, parse_day
from levelup.modules.tech.persistence import (
    CollectionStore,
    SourceAlreadyExists,
    SubscriptionService,
)
from levelup.modules.tech.reading import ReadingStore


def source_json(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "inputUrl": row["input_url"],
        "collectionUrl": row["collection_url"],
        "collectorType": row["collector_type"],
        "status": row["status"],
        "enabled": row["status"] == "active",
        "initializationState": row["initialization_state"],
        "version": row["version"],
        "lastAttemptAt": row["last_attempt_at"],
        "lastSuccessAt": row["last_success_at"],
        "lastUsableAt": row["last_usable_at"],
        "lastResult": row["last_result"],
        "openIssueCount": row.get("open_issue_count", 0),
        "lastError": {"code": row["last_error_code"], "message": "연결·수집 상태를 확인해주세요."}
        if row["last_error_code"]
        else None,
    }


def translate(error: CollectionError) -> ApiError:
    code = error.code
    status = {
        "NOT_FOUND": 404,
        "VERSION_CONFLICT": 412,
        "SOURCE_ALREADY_EXISTS": 409,
        "RESOURCE_BUSY": 409,
        "PRIVATE_URL": 422,
        "UNSUPPORTED_SOURCE": 422,
        "INVALID_FEED": 422,
        "FETCH_TIMEOUT": 504,
        "CONNECTION_FAILED": 502,
        "HTTP_ERROR": 502,
        "RESPONSE_TOO_LARGE": 502,
        "ITEM_LIMIT": 422,
        "CANDIDATE_LIMIT": 422,
        "GMAIL_NOT_CONNECTED": 409,
        "GMAIL_REAUTH_REQUIRED": 409,
    }.get(code, 400)
    message = {
        "SOURCE_ALREADY_EXISTS": "이미 등록한 출처입니다.",
        "VERSION_CONFLICT": "다른 작업에서 변경되었습니다. 새로고침 후 다시 시도해주세요.",
        "PRIVATE_URL": "공개된 웹사이트나 RSS·Atom 주소를 입력해주세요.",
        "RESOURCE_BUSY": "다른 작업을 처리 중입니다. 잠시 후 다시 시도해주세요.",
        "UNSUPPORTED_SOURCE": (
            "이 사이트에서 RSS·Atom 피드를 찾지 못했습니다. "
            "사이트가 RSS를 제공하지 않을 수 있습니다. RSS·Atom 주소를 직접 입력해주세요."
        ),
    }.get(code, "요청을 완료하지 못했습니다. 입력과 연결 상태를 확인해주세요.")
    fields = (
        {"existingSourceId": str(error.existing_source_id)}
        if isinstance(error, SourceAlreadyExists)
        else None
    )
    return ApiError(status, code, message, fields=fields)


def create_tech_router(
    database: Callable[[], Engine],
    session: Callable,
    csrf: Callable,
    clock: Callable[[], datetime],
    core: CollectionCore,
    secret: str,
    *,
    settings=None,
    google=None,
    gmail_transport=None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def current(request: Request, scope="read") -> UUID:
        value = session(request)
        if request.method not in ("GET", "HEAD"):
            csrf(request, value)
        owner = value["owner_id"]
        minute = int(clock().timestamp()) // 60
        quota = {"read": 120, "write": 30, "resolve": 5, "test": 2, "gmail": 5}[scope]
        with database().begin() as conn:
            count = conn.execute(
                text("""INSERT INTO request_limits(owner_id,scope,minute,count)
                VALUES (:owner,:scope,:minute,1) ON CONFLICT (owner_id,scope,minute)
                DO UPDATE SET count=request_limits.count+1 RETURNING count"""),
                {"owner": owner, "scope": scope, "minute": minute},
            ).scalar_one()
            conn.execute(
                text("DELETE FROM request_limits WHERE owner_id=:owner AND minute<:before"),
                {"owner": owner, "before": minute - 2},
            )
        if count > quota:
            raise ApiError(
                429,
                "RATE_LIMITED",
                "요청이 많습니다. 잠시 후 다시 시도해주세요.",
                retry_after=60 - int(clock().timestamp()) % 60,
            )
        return owner

    def store() -> CollectionStore:
        return CollectionStore(database())

    def reading() -> ReadingStore:
        return ReadingStore(database(), secret)

    @router.post("/tech/sources/resolve")
    async def resolve(request: Request):
        owner = current(request, "resolve")
        value = await body(request, {"inputUrl": str}, required={"inputUrl"})
        result = await core.resolve(value["inputUrl"])
        existing = {row["collection_url"]: row["id"] for row in store().list_sources(owner)}
        return {
            "data": {
                "inputUrl": result.input_url,
                "options": [
                    {
                        "name": option.name,
                        "collectionUrl": option.collection_url,
                        "collectorType": option.collector_type,
                        "adapterKey": option.adapter_key,
                        **(
                            {"existingSourceId": str(existing[option.collection_url])}
                            if option.collection_url in existing
                            else {}
                        ),
                    }
                    for option in result.options
                ],
                "requiresSelection": result.requires_selection,
                "warnings": result.candidate_errors,
            }
        }

    @router.get("/tech/sources")
    def sources(request: Request):
        owner = current(request)
        return {"data": {"items": [source_json(row) for row in store().list_sources(owner)]}}

    @router.post("/tech/sources", status_code=202)
    async def add_source(request: Request):
        owner = current(request, "resolve")
        value = await body(
            request, {"inputUrl": str, "collectionUrl": str}, required={"inputUrl", "collectionUrl"}
        )
        source, job = await SubscriptionService(store(), core).add(
            owner, value["inputUrl"], value["collectionUrl"]
        )
        return {"data": {"source": source_json(source), "jobId": str(job)}}

    @router.patch("/tech/sources/{source_id}")
    async def toggle(request: Request, source_id: str):
        owner = current(request, "write")
        value = await body(request, {"enabled": bool}, required={"enabled"})
        source, job = store().change_source(
            owner, identifier(source_id), version(request), enabled=value["enabled"]
        )
        return JSONResponse(
            jsonable_encoder(
                {"data": {"source": source_json(source), "jobId": str(job) if job else None}}
            ),
            status_code=202 if job else 200,
        )

    @router.delete("/tech/sources/{source_id}")
    def delete_source(request: Request, source_id: str):
        owner = current(request, "write")
        source, _ = store().change_source(
            owner, identifier(source_id), version(request), delete=True
        )
        return {
            "data": {
                "id": str(source["id"]),
                "status": "deleted",
                "preserved": {"articles": True, "readingState": True, "deliveryHistory": True},
            }
        }

    @router.get("/tech/articles")
    def articles(request: Request):
        owner = current(request)
        query = request.query_params
        if query.keys() - {"view", "q", "sourceId", "read", "hidden", "cursor", "limit"}:
            raise ApiError(400, "INVALID_REQUEST", "지원하지 않는 목록 조건입니다.")
        try:
            limit = int(query.get("limit", "20"))
        except ValueError:
            raise ApiError(400, "INVALID_REQUEST", "페이지 크기를 확인해주세요.") from None
        return reading().articles(
            owner,
            view=query.get("view", "all"),
            q=query.get("q", ""),
            source_id=identifier(query["sourceId"]) if query.get("sourceId") else None,
            read=query.get("read", "all"),
            hidden=query.get("hidden", "exclude"),
            cursor=query.get("cursor"),
            limit=limit,
        )

    @router.get("/tech/digests")
    def digest_history(request: Request):
        owner = current(request)
        at = clock()
        query = request.query_params
        if query.keys() - {"dateFrom", "dateTo", "cursor", "limit"}:
            raise ApiError(400, "INVALID_REQUEST", "조회 기간을 확인해주세요.")
        end = parse_day(query.get("dateTo", at.astimezone(KST).date().isoformat()), at)
        start = parse_day(query.get("dateFrom", (end - timedelta(days=6)).isoformat()), at)
        try:
            limit = int(query.get("limit", "20"))
        except ValueError:
            raise ApiError(400, "INVALID_REQUEST", "페이지 크기를 확인해주세요.") from None
        return DigestViews(database(), secret).history(
            owner, start, end, at, limit=limit, cursor=query.get("cursor")
        )

    @router.get("/tech/digests/{day}")
    def digest_detail(request: Request, day: str):
        owner = current(request)
        query = request.query_params
        if query.keys() - {"q", "sourceId", "read", "hidden", "cursor", "limit"}:
            raise ApiError(400, "INVALID_REQUEST", "조회 조건을 확인해주세요.")
        try:
            limit = int(query.get("limit", "20"))
        except ValueError:
            raise ApiError(400, "INVALID_REQUEST", "페이지 크기를 확인해주세요.") from None
        return DigestViews(database(), secret).detail(
            owner,
            parse_day(day, clock()),
            clock(),
            q=query.get("q", ""),
            read=query.get("read", "all"),
            hidden=query.get("hidden", "exclude"),
            source_id=identifier(query["sourceId"]) if query.get("sourceId") else None,
            cursor=query.get("cursor"),
            limit=limit,
        )

    @router.patch("/tech/articles/{article_id}/state")
    async def article_state(request: Request, article_id: str):
        owner = current(request, "write")
        value = await body(request, {"isRead": bool, "isSaved": bool, "isHidden": bool})
        return {"data": reading().set_state(owner, identifier(article_id), version(request), value)}

    @router.get("/tech/collection-status")
    def collection_status(request: Request):
        owner = current(request)
        return {"data": {"sources": [source_json(row) for row in store().list_sources(owner)]}}

    @router.get("/jobs/{job_id}")
    def job(request: Request, job_id: str):
        owner = current(request)
        with database().connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT id,state,result_code,result_summary FROM job_runs "
                        "WHERE id=:id AND owner_id=:owner"
                    ),
                    {"id": identifier(job_id), "owner": owner},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ApiError(404, "NOT_FOUND", "작업을 찾지 못했습니다.")
        return {
            "data": {
                "id": str(row["id"]),
                "state": row["state"],
                "resultCode": row["result_code"],
                "resultSummary": row["result_summary"],
            }
        }

    from levelup.api.gmail import create_mail_router

    router.include_router(
        create_mail_router(database, session, current, clock, settings, google, gmail_transport)
    )
    return router


def register_errors(app, error_handler):
    @app.exception_handler(CollectionError)
    async def collection_error(request: Request, exc: CollectionError):
        return await error_handler(request, translate(exc))

    @app.exception_handler(DBAPIError)
    async def database_error(request: Request, exc: DBAPIError):
        code = (
            "RESOURCE_BUSY"
            if getattr(exc.orig, "sqlstate", None) in ("55P03", "57014")
            else "INTERNAL_ERROR"
        )
        return await error_handler(
            request,
            ApiError(
                409 if code == "RESOURCE_BUSY" else 500,
                code,
                "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.",
            ),
        )
