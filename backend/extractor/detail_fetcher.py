from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from extractor.fetch_variants.sen_ajax import maybe_fetch_via_ajax
from extractor.http_security import assert_public_url, client_verify_for_url, tls_metadata
from extractor.models import FetchedDetail


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
}
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


async def fetch_detail(url: str, *, timeout: float = 20.0, context: dict[str, Any] | None = None) -> FetchedDetail:
    assert_public_url(url)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers=DEFAULT_HEADERS,
        verify=client_verify_for_url(url),
    ) as client:
        response = await _get_following_js_redirect(client, url, max_bytes=_max_fetch_bytes())
        enriched = await maybe_fetch_via_ajax(
            client,
            url,
            response,
            context or {},
            max_bytes=_max_fetch_bytes(),
            send_limited=_send_limited,
        )
        if enriched is not None and _html_richness_score(enriched) > _html_richness_score(response):
            response = enriched
        assert_public_url(str(response.url))
        metadata = tls_metadata(str(response.url))
        return FetchedDetail(
            requested_url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            content=response.content,
            headers={key.lower(): value for key, value in response.headers.items()},
            metadata=metadata,
        )


async def _get_following_js_redirect(
    client: httpx.AsyncClient,
    url: str,
    max_bytes: int,
    max_js_redirects: int = 5,
) -> httpx.Response:
    current_url = url
    seen_urls: set[str] = set()
    response: httpx.Response | None = None
    for _ in range(max_js_redirects + 1):
        assert_public_url(current_url)
        response = await _stream_get_limited(client, current_url, max_bytes=max_bytes)
        if response.status_code in REDIRECT_STATUS_CODES and response.headers.get("location"):
            redirect_url = urljoin(str(response.url), response.headers["location"])
            assert_public_url(redirect_url)
            if redirect_url in seen_urls:
                break
            seen_urls.add(redirect_url)
            current_url = redirect_url
            continue
        response.raise_for_status()
        if "text/html" not in (response.headers.get("content-type", "").lower()):
            break
        redirect_url = extract_js_redirect_url(str(response.url), response.text)
        if not redirect_url or redirect_url in seen_urls:
            break
        seen_urls.add(redirect_url)
        current_url = redirect_url
    if response is None:
        raise RuntimeError(f"fetch failed: {url}")
    return response


async def _stream_get_limited(client: httpx.AsyncClient, url: str, *, max_bytes: int) -> httpx.Response:
    request = client.build_request("GET", url)
    return await _send_limited(client, request, max_bytes=max_bytes)


async def _send_limited(client: httpx.AsyncClient, request: httpx.Request, *, max_bytes: int) -> httpx.Response:
    response = await client.send(request, stream=True)
    try:
        content_length = _content_length(response.headers)
        if content_length is not None and content_length > max_bytes:
            raise RuntimeError(f"detail response too large by content-length: {content_length} bytes > {max_bytes} bytes")

        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > max_bytes:
                raise RuntimeError(f"detail response too large while streaming: {len(data)} bytes > {max_bytes} bytes")
        response._content = bytes(data)  # noqa: SLF001 - httpx has no public setter for streamed content.
        return response
    except Exception:
        await response.aclose()
        raise
    finally:
        if not response.is_closed:
            await response.aclose()


def extract_js_redirect_url(base_url: str, html: str) -> str | None:
    patterns = (
        r"""(?:window|document|top|parent)?\.?location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""",
        r"""(?:window|document|top|parent)?\.?location\.replace\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""(?:window|document|top|parent)?\.?location\.assign\(\s*['"]([^'"]+)['"]\s*\)""",
    )
    compact = re.sub(r"\s+", " ", html[:4000])
    if len(_strip_tags(compact)) > 120:
        return None
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return urljoin(base_url, match.group(1).strip())
    meta = re.search(
        r"""<meta[^>]+http-equiv=["']?refresh["']?[^>]+content=["'][^"']*url=([^"';>]+)""",
        html,
        re.IGNORECASE,
    )
    if meta:
        return urljoin(base_url, meta.group(1).strip())
    return None


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value).strip()


def _content_length(headers: httpx.Headers) -> int | None:
    value = headers.get("content-length")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _max_fetch_bytes() -> int:
    try:
        return int(os.getenv("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024
    except ValueError:
        return 50 * 1024 * 1024


def _html_richness_score(response: httpx.Response) -> int:
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        return 0
    text = response.text
    attachment_markers = sum(
        text.count(marker)
        for marker in (
            "serverFileObj",
            "serverFileObjArray",
            "DEXT5UPLOAD.AddUploadedFile",
            "atchFileId",
            "fileSn",
            "fn_egov_downFile",
            "downFile.do",
            "파일첨부",
            "다운로드",
        )
    )
    plain_chars = len(_strip_tags(text))
    return attachment_markers * 500 + min(plain_chars, 5000)
