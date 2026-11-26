import json
import re
from uuid import UUID

from fastapi import Request

from levelup.api.errors import ApiError


def identifier(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise ApiError(400, "INVALID_REQUEST", "식별자를 확인해주세요.") from None


def version(request: Request) -> int:
    value = request.headers.get("if-match")
    if value is None:
        raise ApiError(428, "PRECONDITION_REQUIRED", "최신 상태를 조회한 뒤 다시 시도해주세요.")
    if not re.fullmatch(r'"\d{1,18}"', value):
        raise ApiError(400, "INVALID_REQUEST", "변경 버전 형식을 확인해주세요.")
    return int(value[1:-1])


async def body(
    request: Request,
    fields: dict[str, type],
    *,
    required: set[str] | None = None,
    allow_empty: bool = False,
) -> dict:
    try:
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 16 * 1024:
                raise ApiError(413, "REQUEST_TOO_LARGE", "입력 내용이 너무 큽니다.")
            data.extend(chunk)
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            raise ValueError
        result = json.loads(data)
        if (
            not isinstance(result, dict)
            or (not result and not allow_empty)
            or result.keys() - fields.keys()
        ):
            raise ValueError
        if required and required - result.keys():
            raise ValueError
        if any(type(value) is not fields[key] for key, value in result.items()):
            raise ValueError
        return result
    except (ValueError, UnicodeError):
        raise ApiError(400, "INVALID_REQUEST", "입력 항목과 형식을 확인해주세요.") from None
