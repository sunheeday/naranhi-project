from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.crawler.homepage_client import extract_js_redirect_url
from app.crawler.http_client import DEFAULT_HEADERS, make_async_client_for_url, with_retries
from app.crawler.link_extractor import page_snippet, page_title


NOTICE_TERMS = ("가정통신문", "가정통신", "학부모통신문", "학교통신문")
NOTICE_RAW_TERMS = ("가정(학부모)통신문",)
ANNOUNCEMENT_TERMS = ("공지사항", "학교공지", "학교공지사항")
BOARD_TERMS = ("제목", "등록일", "작성자", "첨부파일", "조회수", "게시글", "게시물", "목록")
WEAK_TERMS = ("검색",)
NEGATIVE_TERMS = ("페이지 없음", "권한 없음", "로그인이 필요", "준비중", "오류가 발생", "잘못된 접근", "authReadError")


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    score: int
    title: str
    snippet: str
    error: str | None = None


async def verify_notice_url(
    url: str,
    warmup_url: str | None = None,
    *,
    timeout: float,
) -> VerificationResult:
    try:
        async with make_async_client_for_url(url=url, timeout=timeout) as client:
            referer = warmup_url
            if warmup_url:
                warmup_response = await with_retries(
                    lambda: _get_following_js_redirect(client, warmup_url),
                    retries=2,
                    base_delay=0.75,
                )
                referer = str(warmup_response.url)

            headers = dict(DEFAULT_HEADERS)
            if referer and _same_origin(referer, url):
                headers["Referer"] = referer

            response = await with_retries(
                lambda: _get_following_js_redirect(client, url, headers=headers),
                retries=2,
                base_delay=0.75,
            )
            html = response.text
    except Exception as exc:  # noqa: BLE001 - POC returns error text to UI.
        return VerificationResult(ok=False, score=0, title="", snippet="", error=str(exc))

    title = page_title(html)
    snippet = page_snippet(html, max_chars=700)
    haystack = f"{response.url} {title} {snippet}"
    compact_haystack = "".join(haystack.split())

    notice_hits = sum(1 for term in NOTICE_TERMS if term in compact_haystack)
    notice_hits += sum(1 for term in NOTICE_RAW_TERMS if term in haystack)
    announcement_hits = sum(1 for term in ANNOUNCEMENT_TERMS if term in compact_haystack)
    board_hits = sum(1 for term in BOARD_TERMS if term in haystack)
    weak_hits = sum(1 for term in WEAK_TERMS if term in haystack)

    score = notice_hits * 20 + announcement_hits * 10 + board_hits * 10 + weak_hits * 5
    for term in NEGATIVE_TERMS:
        if term in haystack:
            score -= 20

    is_schoolbell = "schoolbell-e.com" in urlparse(str(response.url)).netloc and "학교종이" in haystack
    if "schoolbell-e.com" in urlparse(str(response.url)).netloc and "학교종이" in haystack:
        score += 10

    return VerificationResult(
        ok=score > 0 and (
            notice_hits > 0
            or board_hits >= 2
            or (announcement_hits > 0 and board_hits >= 1)
            or is_schoolbell
        ),
        score=score,
        title=title,
        snippet=snippet,
        error=None,
    )


def _same_origin(left: str, right: str) -> bool:
    left_parsed = urlparse(left)
    right_parsed = urlparse(right)
    return left_parsed.scheme == right_parsed.scheme and left_parsed.netloc == right_parsed.netloc


async def _get_following_js_redirect(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str] | None = None,
    max_js_redirects: int = 5,
) -> httpx.Response:
    current_url = url
    seen_urls: set[str] = set()
    response: httpx.Response | None = None

    for _ in range(max_js_redirects + 1):
        response = await client.get(current_url, headers=headers)
        response.raise_for_status()

        js_redirect_url = extract_js_redirect_url(str(response.url), response.text)
        if not js_redirect_url or js_redirect_url in seen_urls:
            break

        seen_urls.add(js_redirect_url)
        current_url = js_redirect_url

    if response is None:
        raise RuntimeError(f"verification fetch failed: {url}")
    return response

