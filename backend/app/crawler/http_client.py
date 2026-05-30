from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import os
import ssl
from typing import TypeVar
from urllib.parse import urlparse

import httpx


T = TypeVar("T")
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
}

DEFAULT_LEGACY_TLS_HOSTS = ("sen.ms.kr", "gen.ms.kr")


def make_async_client(
    *,
    timeout: float = 15.0,
    legacy_tls: bool = False,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
        verify=legacy_ssl_context() if legacy_tls else True,
    )


def make_async_client_for_url(*, url: str, timeout: float = 15.0) -> httpx.AsyncClient:
    return make_async_client(timeout=timeout, legacy_tls=uses_legacy_tls(url))


def uses_legacy_tls(url: str) -> bool:
    host = _hostname(url)
    return any(_host_matches(host, pattern) for pattern in legacy_tls_hosts())


def legacy_tls_hosts() -> tuple[str, ...]:
    raw = os.getenv("CRAWLER_TLS_LEGACY_HOSTS", ",".join(DEFAULT_LEGACY_TLS_HOSTS))
    hosts = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    return hosts or DEFAULT_LEGACY_TLS_HOSTS


def legacy_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        context.minimum_version = ssl.TLSVersion.TLSv1
    except AttributeError:
        pass
    try:
        context.set_ciphers("ALL:@SECLEVEL=0")
    except ssl.SSLError:
        pass
    return context


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def same_origin(left: str, right: str) -> bool:
    left_url = urlparse(left)
    right_url = urlparse(right)
    return left_url.scheme == right_url.scheme and left_url.netloc == right_url.netloc


def _host_matches(host: str, pattern: str) -> bool:
    normalized = pattern.strip().lower()
    return bool(normalized) and (host == normalized or host.endswith(f".{normalized}"))


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int = 2,
    base_delay: float = 0.5,
    retry_status_codes: set[int] | None = None,
) -> T:
    retryable_status_codes = retry_status_codes or RETRYABLE_STATUS_CODES
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await operation()
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in retryable_status_codes:
                break
            if attempt >= retries:
                break
            await asyncio.sleep(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc

