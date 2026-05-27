from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.crawler.homepage_client import extract_js_redirect_url
from app.crawler.http_client import DEFAULT_HEADERS, make_async_client_for_url
from extractor.html_text_extractor import extract_html_text


WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


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
        redirect_url = extract_js_redirect_url(str(response.url), response.text)
        if redirect_url:
            response = await client.get(redirect_url, headers=DEFAULT_HEADERS)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    title = _page_title(soup)
    text = extract_html_text(response.text)
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


def _normalize_text(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = WHITESPACE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)
    return BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()
