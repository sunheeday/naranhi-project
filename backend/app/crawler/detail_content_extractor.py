from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.crawler.homepage_client import extract_js_redirect_url
from app.crawler.http_client import DEFAULT_HEADERS, make_async_client_for_url

WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")
MIN_DETAIL_TEXT_LENGTH = 40


@dataclass(frozen=True)
class NoticeDetailContent:
    url: str
    final_url: str
    title: str
    text: str


async def fetch_notice_detail_content(
    detail_url: str,
    *,
    timeout: float,
) -> NoticeDetailContent:
    async with make_async_client_for_url(url=detail_url, timeout=timeout) as client:
        response = await client.get(detail_url, headers=DEFAULT_HEADERS)
        redirect_url = extract_js_redirect_url(response.text, str(response.url))
        if redirect_url:
            response = await client.get(redirect_url, headers=DEFAULT_HEADERS)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    title = _page_title(soup)
    text = _extract_notice_text(soup)
    return NoticeDetailContent(
        url=detail_url,
        final_url=str(response.url),
        title=title,
        text=text,
    )


def _page_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return _normalize_text(soup.title.string)
    heading = soup.find(["h1", "h2", "h3"])
    return _normalize_text(heading.get_text(" ", strip=True)) if heading else ""


def _extract_notice_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer", "header"]):
        tag.decompose()

    candidates: list[str] = []
    for selector in (
        "article",
        "main",
        ".board-view",
        ".board_view",
        ".bbs-view",
        ".bbs_view",
        ".view",
        ".content",
        ".contents",
        "#content",
        "#contents",
    ):
        for node in soup.select(selector):
            text = _normalize_text(node.get_text("\n", strip=True))
            if len(text) >= MIN_DETAIL_TEXT_LENGTH:
                candidates.append(text)

    body = soup.body or soup
    body_text = _normalize_text(body.get_text("\n", strip=True))
    if len(body_text) >= MIN_DETAIL_TEXT_LENGTH:
        candidates.append(body_text)

    if not candidates:
        return ""

    return max(candidates, key=len)


def _normalize_text(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = WHITESPACE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)
    return BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()


def same_origin(left: str, right: str) -> bool:
    left_url = urlparse(left)
    right_url = urlparse(right)
    return left_url.scheme == right_url.scheme and left_url.netloc == right_url.netloc
