import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient

from levelup.api.app import create_app
from levelup.core.config import Settings
from levelup.core.security import Cipher, safe_return_to


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test",
        "//evil.test",
        "/\\evil.test",
        "/%2f%2fevil.test",
        "/\nevil",
        "javascript:alert(1)",
    ],
)
def test_external_return_paths_are_rejected(url):
    assert safe_return_to(url) == "/"


def test_valid_internal_path():
    assert safe_return_to("/settings?tab=gmail") == "/settings?tab=gmail"


def test_authenticated_cipher_rejects_wrong_purpose(settings):
    cipher = Cipher(settings.token_encryption_key)
    encrypted = cipher.encrypt("refresh", "owner")
    assert cipher.decrypt(encrypted, "owner") == "refresh"
    with pytest.raises(InvalidTag):
        cipher.decrypt(encrypted, "different-owner")


def test_requires_https_for_nonlocal_cookies():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_origin="http://example.com")


def test_unconfigured_app_fails_closed():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/v1/home").status_code == 401
        response = client.get("/api/auth/signin")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SETUP_REQUIRED"
        assert client.get("/api/v1/not-an-api").json()["error"]["code"] == "NOT_FOUND"


def test_vercel_cannot_use_local_insecure_cookie_defaults(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ValueError, match="HTTPS APP_ORIGIN"):
        Settings(_env_file=None)
