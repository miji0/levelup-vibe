"""Gmail send-only transport. No mailbox reads or automatic retries."""

import asyncio
import base64
from dataclasses import dataclass
from typing import Literal

import httpx

from levelup.core.config import Settings
from levelup.infra.public_http import CollectionError


@dataclass(frozen=True)
class SendOutcome:
    kind: Literal["accepted", "rejected", "unknown"]
    code: str | None = None
    provider_id: str | None = None
    http_status: int | None = None


class Gmail:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def refresh(self, refresh_token: str) -> str:
        try:
            async with (
                asyncio.timeout(15),
                httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False, timeout=15
                ) as client,
            ):
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": self.settings.google_client_id,
                        "client_secret": self.settings.google_client_secret,
                    },
                )
            data = response.json()
            if (
                response.status_code == 400
                and isinstance(data, dict)
                and data.get("error") == "invalid_grant"
            ):
                raise CollectionError("GMAIL_REAUTH_REQUIRED")
            token = data.get("access_token") if isinstance(data, dict) else None
            if response.status_code != 200 or not isinstance(token, str) or not token:
                raise CollectionError("GMAIL_TOKEN_FAILED")
            return token
        except CollectionError:
            raise
        except (httpx.HTTPError, ValueError, TimeoutError):
            raise CollectionError("GMAIL_TOKEN_FAILED") from None

    async def send(self, access_token: str, payload: bytes) -> SendOutcome:
        try:
            async with (
                asyncio.timeout(15),
                httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False, timeout=15
                ) as client,
            ):
                response = await client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    headers={"Authorization": "Bearer " + access_token},
                    json={"raw": base64.urlsafe_b64encode(payload).decode()},
                )
            try:
                data = response.json()
            except ValueError:
                return SendOutcome(
                    "unknown", "GMAIL_RESPONSE_UNCLEAR", http_status=response.status_code
                )
            if 200 <= response.status_code < 300 and isinstance(data, dict):
                identifier = data.get("id")
                if isinstance(identifier, str) and identifier:
                    return SendOutcome(
                        "accepted", provider_id=identifier, http_status=response.status_code
                    )
            error = data.get("error") if isinstance(data, dict) else None
            if response.status_code in (400, 401, 403, 404, 429) and isinstance(error, dict):
                if error.get("code") == response.status_code:
                    code = (
                        "GMAIL_REAUTH_REQUIRED" if response.status_code == 401 else "GMAIL_REJECTED"
                    )
                    return SendOutcome("rejected", code, http_status=response.status_code)
            return SendOutcome(
                "unknown", "GMAIL_RESPONSE_UNCLEAR", http_status=response.status_code
            )
        except (httpx.HTTPError, TimeoutError):
            return SendOutcome("unknown", "GMAIL_REQUEST_UNCLEAR")

    async def revoke(self, refresh_token: str) -> bool:
        try:
            async with (
                asyncio.timeout(15),
                httpx.AsyncClient(trust_env=False, timeout=15) as client,
            ):
                result = await client.post(
                    "https://oauth2.googleapis.com/revoke", data={"token": refresh_token}
                )
            return result.status_code == 200
        except (httpx.HTTPError, TimeoutError):
            return False
