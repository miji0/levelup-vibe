"""Server-only public HTTP: DNS validation, pinned connections and bounded responses."""

import asyncio
import ipaddress
import logging
import socket
import zlib
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_URL_BYTES = 2048
HTTP_TIMEOUT = 15
MAX_REDIRECTS = 3
_FETCHING = ContextVar("levelup_public_fetch", default=False)


class _HideFetchLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _FETCHING.get()


# Third-party HTTP debug logs can contain source queries; suppress only this task's fetch.
for _logger in (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
):
    logging.getLogger(_logger).addFilter(_HideFetchLogs())


class CollectionError(ValueError):
    """Only a safe code crosses the service boundary; never expose URLs or exceptions."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def public_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise CollectionError("PRIVATE_URL") from None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise CollectionError("PRIVATE_URL")
    return str(address)


def normalize_url(value: str) -> str:
    value = value.strip()
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise CollectionError("INVALID_URL") from None
    if (
        not value
        or size > MAX_URL_BYTES
        or "\\" in value
        or any(ord(c) <= 32 or ord(c) == 127 for c in value)
    ):
        raise CollectionError("INVALID_URL")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme not in ("http", "https")
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 80 if parsed.scheme == "http" else 443)
            or "%" in host
        ):
            raise ValueError
        host = host.encode("idna").decode("ascii").lower()
        if host.rstrip(".") == "localhost" or host.rstrip(".").endswith(".localhost"):
            raise CollectionError("PRIVATE_URL")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass  # Numeric aliases are resolved and checked before any connection.
        else:
            public_ip(host)
        authority = f"[{host}]" if ":" in host else host
        result = urlunsplit((parsed.scheme, authority, parsed.path, parsed.query, ""))
        # HTTPX defines the actual wire URL; preserve meaningful path/query spelling.
        if len(str(httpx.URL(result)).encode()) > MAX_URL_BYTES:
            raise ValueError
        return result
    except CollectionError:
        raise
    except (ValueError, UnicodeError, httpx.InvalidURL):
        raise CollectionError("INVALID_URL") from None


@dataclass(frozen=True)
class PublicResponse:
    url: str
    status: int
    body: bytes
    content_type: str
    etag: str | None = None
    last_modified: str | None = None


class SafePublicHTTP:
    def __init__(self) -> None:
        self._slots = asyncio.Semaphore(2)

    async def check_url(self, value: str) -> tuple[str, tuple[str, ...]]:
        url = normalize_url(value)
        parsed = urlsplit(url)
        try:
            async with asyncio.timeout(HTTP_TIMEOUT):
                addresses = await asyncio.get_running_loop().getaddrinfo(
                    parsed.hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            ips = tuple(dict.fromkeys(public_ip(str(info[4][0])) for info in addresses))
            if not ips:
                raise CollectionError("CONNECTION_FAILED")
            return url, ips
        except CollectionError:
            raise
        except TimeoutError:
            raise CollectionError("FETCH_TIMEOUT") from None
        except OSError:
            raise CollectionError("CONNECTION_FAILED") from None

    async def fetch(
        self, value: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> PublicResponse:
        token = _FETCHING.set(True)
        try:
            return await self._fetch(value, etag=etag, last_modified=last_modified)
        finally:
            _FETCHING.reset(token)

    async def _fetch(
        self, value: str, *, etag: str | None, last_modified: str | None
    ) -> PublicResponse:
        try:
            async with asyncio.timeout(HTTP_TIMEOUT), self._slots:
                url = normalize_url(value)
                for hop in range(MAX_REDIRECTS + 1):
                    url, ips = await self.check_url(url)
                    parsed = httpx.URL(url)
                    headers = {
                        "Host": parsed.netloc.decode("ascii"),
                        "Accept-Encoding": "gzip, deflate",
                        "User-Agent": "LevelUp/0.1",
                    }
                    if etag is not None:
                        headers["If-None-Match"] = etag
                    if last_modified is not None:
                        headers["If-Modified-Since"] = last_modified
                    # Connect to a checked numeric IP; retain the original Host and TLS identity.
                    pinned = parsed.copy_with(host=ips[0])
                    async with httpx.AsyncClient(
                        trust_env=False, follow_redirects=False, timeout=HTTP_TIMEOUT
                    ) as client:
                        async with client.stream(
                            "GET",
                            pinned,
                            headers=headers,
                            extensions={"sni_hostname": parsed.host},
                        ) as response:
                            if response.status_code in (301, 302, 303, 307, 308):
                                location = response.headers.get("location")
                                if not location or hop == MAX_REDIRECTS:
                                    raise CollectionError("REDIRECT_LIMIT")
                                url = normalize_url(urljoin(url, location))
                                # Validators must not follow redirects to another representation.
                                etag = last_modified = None
                                continue
                            if response.status_code not in (200, 304):
                                raise CollectionError("HTTP_ERROR")
                            body = (
                                b"" if response.status_code == 304 else await _read_body(response)
                            )
                            return PublicResponse(
                                url,
                                response.status_code,
                                body,
                                response.headers.get("content-type", ""),
                                response.headers.get("etag"),
                                response.headers.get("last-modified"),
                            )
                raise CollectionError("REDIRECT_LIMIT")
        except CollectionError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise CollectionError("FETCH_TIMEOUT") from None
        except (httpx.HTTPError, OSError, ValueError):
            raise CollectionError("CONNECTION_FAILED") from None


async def _read_body(response: httpx.Response) -> bytes:
    encoding = response.headers.get("content-encoding", "identity").lower().strip()
    if encoding not in ("identity", "gzip", "deflate"):
        raise CollectionError("UNSUPPORTED_ENCODING")
    decoder = (
        None
        if encoding == "identity"
        else zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
    )
    body = bytearray()
    wire_size = 0
    try:
        async for chunk in response.aiter_raw():
            wire_size += len(chunk)
            if wire_size > MAX_BODY_BYTES:
                raise CollectionError("RESPONSE_TOO_LARGE")
            if decoder is not None:
                chunk = decoder.decompress(chunk, MAX_BODY_BYTES - len(body) + 1)
                if decoder.unconsumed_tail:
                    raise CollectionError("RESPONSE_TOO_LARGE")
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                raise CollectionError("RESPONSE_TOO_LARGE")
        if decoder is not None and (not decoder.eof or decoder.unused_data):
            raise CollectionError("INVALID_RESPONSE")
    except zlib.error:
        raise CollectionError("INVALID_RESPONSE") from None
    return bytes(body)
