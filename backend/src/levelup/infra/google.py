import base64
import hashlib
from typing import Any

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oidc.core import CodeIDToken
from joserfc import jwt
from joserfc.jwk import KeySet

from levelup.core.config import Settings

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


class Google:
    def __init__(self, settings: Settings):
        self.settings = settings

    def client(
        self, scope: str = "openid email", redirect_path: str = "/api/auth/callback/google"
    ) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            self.settings.google_client_id,
            self.settings.google_client_secret,
            scope=scope,
            redirect_uri=self.settings.app_origin + redirect_path,
            token_endpoint_auth_method="client_secret_post",
            timeout=15,
        )

    async def authorize(self, state: str, nonce: str, verifier: str, first: bool) -> str:
        scope = "openid email" + (" " + GMAIL_SCOPE if first else "")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(
            b"="
        )
        async with self.client(scope) as client:
            url, _ = client.create_authorization_url(
                AUTH_URL,
                state=state,
                nonce=nonce,
                code_challenge=challenge.decode(),
                code_challenge_method="S256",
                access_type="offline",
                prompt="select_account",
            )
            return str(url)

    async def exchange(
        self, code: str, verifier: str, nonce: str, redirect_path: str = "/api/auth/callback/google"
    ) -> dict[str, Any]:
        async with self.client(redirect_path=redirect_path) as client:
            token = await client.fetch_token(TOKEN_URL, code=code, code_verifier=verifier)
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(JWKS_URL)
            response.raise_for_status()
        signed = jwt.decode(
            token["id_token"], KeySet.import_key_set(response.json()), algorithms=["RS256"]
        )
        claims = CodeIDToken(
            signed.claims,
            signed.header,
            options={
                "iss": {
                    "essential": True,
                    "values": ["https://accounts.google.com", "accounts.google.com"],
                },
                "aud": {"essential": True, "value": self.settings.google_client_id},
                "exp": {"essential": True},
                "sub": {"essential": True},
            },
            params={
                "nonce": nonce,
                "client_id": self.settings.google_client_id,
                "code": code,
                "access_token": token.get("access_token"),
            },
        )
        claims.validate(leeway=30)
        return {
            "claims": dict(claims),
            "scope": token.get("scope", ""),
            "refresh_token": token.get("refresh_token"),
        }

    async def connect_authorize(self, state: str, nonce: str, verifier: str, subject: str) -> str:
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(
            b"="
        )
        async with self.client(
            "openid email " + GMAIL_SCOPE, "/api/v1/integrations/gmail/callback"
        ) as client:
            url, _ = client.create_authorization_url(
                AUTH_URL,
                state=state,
                nonce=nonce,
                code_challenge=challenge.decode(),
                code_challenge_method="S256",
                access_type="offline",
                prompt="consent select_account",
                login_hint=subject,
            )
            return str(url)

    async def connect_exchange(self, code: str, verifier: str, nonce: str) -> dict[str, Any]:
        return await self.exchange(code, verifier, nonce, "/api/v1/integrations/gmail/callback")
