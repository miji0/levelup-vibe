import httpx
import pytest

from levelup.infra.gmail import Gmail
from levelup.infra.public_http import CollectionError


def mock_http(monkeypatch, handler):
    original = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs.get("trust_env") is False
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, {"id": "m1"}, "accepted"),
        (403, {"error": {"code": 403}}, "rejected"),
        (500, {"error": {"code": 500}}, "unknown"),
        (200, {}, "unknown"),
        (403, {"error": "bad"}, "unknown"),
    ],
)
async def test_one_send_no_retry(monkeypatch, settings, status, body, expected):
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        return httpx.Response(status, json=body)

    mock_http(monkeypatch, handle)
    result = await Gmail(settings).send("secret-access", b"fixture mime")
    assert result.kind == expected and len(calls) == 1


async def test_timeout_unknown_no_retry(monkeypatch, settings):
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("must not leak")

    mock_http(monkeypatch, handle)
    result = await Gmail(settings).send("secret", b"payload")
    assert result.kind == "unknown" and len(calls) == 1


async def test_invalid_grant_never_send(monkeypatch, settings):
    mock_http(monkeypatch, lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(CollectionError, match="GMAIL_REAUTH_REQUIRED"):
        await Gmail(settings).refresh("secret")
