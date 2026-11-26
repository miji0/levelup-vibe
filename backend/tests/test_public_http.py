import asyncio
import gzip
import socket
import zlib

import httpcore
import httpx
import pytest

from levelup.infra import public_http
from levelup.infra.public_http import CollectionError, SafePublicHTTP, normalize_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/a",
        "http://sub.localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "https://169.254.169.254/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://192.0.2.1/",
        "http://224.0.0.1/",
        "http://user:secret@public.example/",
        "file:///etc/passwd",
        "ftp://public.example/a",
        "https://public.example:8000/",
        "http://public.example/%0d\nCookie:secret",
        "http://public.example\\@127.0.0.1/",
        "http://[fe80::1%25eth0]/",
    ],
)
def test_rejects_unsafe_url_without_network(url):
    with pytest.raises(CollectionError):
        normalize_url(url)


def test_normalization_preserves_path_and_query_and_removes_only_documented_parts():
    assert normalize_url(" HTTPS://BLOG.Example:443/Tech/?b=2&a=1#top ") == (
        "https://blog.example/Tech/?b=2&a=1"
    )
    assert normalize_url("https://blog.example/Tech") != normalize_url("https://blog.example/tech/")
    with pytest.raises(CollectionError):
        normalize_url("https://blog.example/" + "가" * 1000)


@pytest.fixture
async def dns(monkeypatch):
    mapping = {}

    async def resolve(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
            for ip in mapping.get(host, ["93.184.216.34"])
        ]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    return mapping


@pytest.mark.asyncio
@pytest.mark.parametrize("ips", [["127.0.0.1"], ["93.184.216.34", "10.0.0.1"], []])
async def test_dns_checks_all_answers_and_rejects_empty(ips, monkeypatch):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    with pytest.raises(CollectionError):
        await SafePublicHTTP().check_url("https://blog.example/feed")


def install_mock(monkeypatch, handler):
    client_class = httpx.AsyncClient
    settings = []

    def client(**kwargs):
        settings.append(kwargs)
        return client_class(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return settings


def response(body=b"ok", *, status=200, headers=None):
    return httpx.Response(status, headers=headers or {}, stream=httpx.ByteStream(body))


@pytest.mark.asyncio
async def test_pinned_ip_host_sni_no_proxy_cookie_or_auth(monkeypatch, dns):
    requests = []

    def handler(request):
        requests.append(request)
        return response()

    settings = install_mock(monkeypatch, handler)
    result = await SafePublicHTTP().fetch("https://blog.example/Feed?b=2&a=1")
    request = requests[0]
    assert request.url.host == "93.184.216.34"
    assert request.headers["host"] == "blog.example"
    assert request.extensions["sni_hostname"] == "blog.example"
    assert request.url.raw_path == b"/Feed?b=2&a=1"
    assert "cookie" not in request.headers and "authorization" not in request.headers
    assert settings[0]["trust_env"] is False and settings[0]["follow_redirects"] is False
    assert result.url == "https://blog.example/Feed?b=2&a=1"


@pytest.mark.asyncio
async def test_tls_transport_uses_original_hostname_and_certificate_verification(monkeypatch, dns):
    seen = []

    class Stream(httpcore.AsyncMockStream):
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            seen.append((ssl_context.check_hostname, ssl_context.verify_mode, server_hostname))
            return self

    async def connect(self, host, port, **kwargs):
        assert host == "93.184.216.34"
        return Stream([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"])

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    assert (await SafePublicHTTP().fetch("https://blog.example/feed")).body == b"ok"
    assert seen == [(True, 2, "blog.example")]


@pytest.mark.asyncio
async def test_private_redirect_is_rejected_before_second_connection(monkeypatch, dns):
    requests = []
    dns["private.example"] = ["10.1.1.1"]

    def handler(request):
        requests.append(request)
        return response(status=302, headers={"Location": "http://private.example/secret"})

    install_mock(monkeypatch, handler)
    with pytest.raises(CollectionError, match="PRIVATE_URL"):
        await SafePublicHTTP().fetch("https://blog.example/feed")
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_relative_redirect_revalidates_dns_and_drops_validators(monkeypatch, dns):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return response(status=302, headers={"Location": "/new"})
        assert "if-none-match" not in request.headers
        assert "if-modified-since" not in request.headers
        return response(headers={"ETag": '"new"'})

    install_mock(monkeypatch, handler)
    result = await SafePublicHTTP().fetch(
        "https://blog.example/feed", etag='"old"', last_modified="Wed, 25 Nov 2026 00:00:00 GMT"
    )
    assert result.url == "https://blog.example/new" and result.etag == '"new"'
    assert requests[0].headers["if-none-match"] == '"old"'


@pytest.mark.asyncio
async def test_redirect_loop_stops_after_three_hops(monkeypatch, dns):
    requests = []

    def handler(request):
        requests.append(request)
        return response(status=302, headers={"Location": "/loop"})

    install_mock(monkeypatch, handler)
    with pytest.raises(CollectionError, match="REDIRECT_LIMIT"):
        await SafePublicHTTP().fetch("https://blog.example/feed")
    assert len(requests) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
async def test_decompression_is_bounded_and_truncation_is_failure(
    monkeypatch, dns, encoding, compress
):
    monkeypatch.setattr(public_http, "MAX_BODY_BYTES", 100)
    current = [compress(b"short")]
    install_mock(
        monkeypatch, lambda request: response(current[0], headers={"Content-Encoding": encoding})
    )
    assert (await SafePublicHTTP().fetch("https://blog.example/feed")).body == b"short"
    current[0] = compress(b"x" * 1000)
    with pytest.raises(CollectionError, match="RESPONSE_TOO_LARGE"):
        await SafePublicHTTP().fetch("https://blog.example/feed")
    current[0] = compress(b"short")[:-3]
    with pytest.raises(CollectionError, match="INVALID_RESPONSE"):
        await SafePublicHTTP().fetch("https://blog.example/feed")


@pytest.mark.asyncio
async def test_body_limit_and_http_error_and_304(monkeypatch, dns):
    monkeypatch.setattr(public_http, "MAX_BODY_BYTES", 5)
    current = [response(b"123456")]
    install_mock(monkeypatch, lambda request: current[0])
    with pytest.raises(CollectionError, match="RESPONSE_TOO_LARGE"):
        await SafePublicHTTP().fetch("https://blog.example/feed")
    current[0] = response(status=503)
    with pytest.raises(CollectionError, match="HTTP_ERROR"):
        await SafePublicHTTP().fetch("https://blog.example/feed")
    current[0] = response(status=304)
    assert (await SafePublicHTTP().fetch("https://blog.example/feed")).status == 304


@pytest.mark.asyncio
async def test_total_deadline_covers_dns(monkeypatch):
    monkeypatch.setattr(public_http, "HTTP_TIMEOUT", 0.01)

    async def slow(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", slow)
    with pytest.raises(CollectionError, match="FETCH_TIMEOUT"):
        await SafePublicHTTP().fetch("https://blog.example/feed")


@pytest.mark.asyncio
async def test_connection_errors_do_not_expose_query_credentials(monkeypatch, dns):
    def handler(request):
        raise httpx.ConnectError("secret-token and full URL")

    install_mock(monkeypatch, handler)
    with pytest.raises(CollectionError) as caught:
        await SafePublicHTTP().fetch("https://blog.example/feed?token=secret")
    assert str(caught.value) == "CONNECTION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["2130706433", "127.1", "0x7f000001", "0177.0.0.1"])
async def test_numeric_alias_is_checked_after_dns_resolution(monkeypatch, dns, alias):
    dns[alias] = ["127.0.0.1"]
    with pytest.raises(CollectionError) as caught:
        await SafePublicHTTP().check_url(f"http://{alias}/private")
    assert caught.value.code in {"PRIVATE_URL", "INVALID_URL"}


def test_invalid_unicode_is_a_safe_input_error():
    with pytest.raises(CollectionError, match="INVALID_URL"):
        normalize_url("https://blog.example/\ud800")


@pytest.mark.asyncio
async def test_dns_rebinding_on_redirect_cannot_reach_private_address(monkeypatch, dns):
    requests = []

    def handler(request):
        requests.append(request)
        dns["blog.example"] = ["127.0.0.1"]
        return response(status=302, headers={"Location": "/rebound"})

    install_mock(monkeypatch, handler)
    with pytest.raises(CollectionError, match="PRIVATE_URL"):
        await SafePublicHTTP().fetch("https://blog.example/feed")
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_total_deadline_interrupts_a_slow_stream(monkeypatch, dns):
    monkeypatch.setattr(public_http, "HTTP_TIMEOUT", 0.01)
    closed = []

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"first"
            await asyncio.Event().wait()

        async def aclose(self):
            closed.append(True)

    install_mock(monkeypatch, lambda request: httpx.Response(200, stream=SlowBody()))
    with pytest.raises(CollectionError, match="FETCH_TIMEOUT"):
        await SafePublicHTTP().fetch("https://blog.example/feed")
    assert closed


@pytest.mark.asyncio
async def test_two_fetch_slots_and_cancellation_release_resources(monkeypatch, dns):
    release = asyncio.Event()
    started = asyncio.Event()
    count = 0
    peak = 0

    async def handler(request):
        nonlocal count, peak
        count += 1
        peak = max(count, peak)
        if count == 2:
            started.set()
        try:
            await release.wait()
            return response()
        finally:
            count -= 1

    install_mock(monkeypatch, handler)
    http = SafePublicHTTP()
    tasks = [asyncio.create_task(http.fetch("https://blog.example/feed")) for _ in range(3)]
    await asyncio.wait_for(started.wait(), 1)
    assert peak == 2
    tasks[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await tasks[0]
    release.set()
    await asyncio.gather(*tasks[1:])
    assert peak == 2 and count == 0
    assert (await http.fetch("https://blog.example/feed")).body == b"ok"


@pytest.mark.asyncio
async def test_third_party_logs_do_not_expose_source_query(monkeypatch, dns, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    install_mock(monkeypatch, lambda request: response())
    await SafePublicHTTP().fetch("https://blog.example/feed?token=source-secret")
    assert "source-secret" not in caplog.text
    assert "HTTP Request" not in caplog.text
    logging.getLogger("httpx").info("unrelated operation")
    assert "unrelated operation" in caplog.text
