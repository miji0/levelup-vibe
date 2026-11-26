import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import RSAKey

from levelup.infra.google import GMAIL_SCOPE, Google


@pytest.mark.parametrize("first", [True, False])
async def test_authorization_pkce_nonce_and_initial_scope(settings, first):
    url = await Google(settings).authorize("state", "nonce", "v" * 43, first)
    params = parse_qs(urlsplit(url).query)
    assert urlsplit(url).hostname == "accounts.google.com"
    assert params["state"] == ["state"]
    assert params["nonce"] == ["nonce"]
    assert params["code_challenge_method"] == ["S256"]
    assert (GMAIL_SCOPE in params["scope"][0]) is first
    assert params["redirect_uri"] == ["https://testserver/api/auth/callback/google"]


@pytest.mark.parametrize("mutation", [None, "signature", "iss", "aud", "nonce", "exp", "iat"])
async def test_real_signed_id_token_validation(settings, monkeypatch, mutation):
    key = RSAKey.generate_key(2048, parameters={"kid": "test"})
    claims = {
        "iss": "https://accounts.google.com",
        "aud": settings.google_client_id,
        "sub": settings.owner_google_sub,
        "nonce": "nonce",
        "email_verified": True,
        "email": settings.owner_email,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    if mutation in {"iss", "aud", "nonce"}:
        claims[mutation] = "wrong"
    if mutation == "exp":
        claims["exp"] = int(time.time()) - 120
    if mutation == "iat":
        del claims["iat"]
    signing_key = (
        RSAKey.generate_key(2048, parameters={"kid": "test"}) if mutation == "signature" else key
    )
    signed = jwt.encode({"alg": "RS256", "kid": "test"}, claims, signing_key)

    async def fetch_token(self, url, **kwargs):
        assert kwargs["code_verifier"] == "verifier"
        assert url == "https://oauth2.googleapis.com/token"
        return {"id_token": signed, "scope": "openid email", "access_token": "access"}

    async def get_jwks(self, url, **kwargs):
        assert url == "https://www.googleapis.com/oauth2/v3/certs"
        return httpx.Response(
            200, json={"keys": [key.as_dict(private=False)]}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(AsyncOAuth2Client, "fetch_token", fetch_token)
    monkeypatch.setattr(httpx.AsyncClient, "get", get_jwks)
    if mutation:
        with pytest.raises(JoseError):
            await Google(settings).exchange("code", "verifier", "nonce")
    else:
        result = await Google(settings).exchange("code", "verifier", "nonce")
        assert result["claims"]["sub"] == settings.owner_google_sub
