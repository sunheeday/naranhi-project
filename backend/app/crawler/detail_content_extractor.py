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

# 본문만 정밀하게 잡는 selector (검증 완료)
PRECISE_SELECTORS = (
    "#viewConts",       # 광주 gen xboard CMS
    "div.conts",        # 인천 icees.kr boardCnts CMS
    "td.tch-ctnt",      # 울산/충북/전북 usm CMS
    ".bbsV_cont",       # 대구 dge / selectNtt CMS
)

NOISE_SELECTORS = (
    "script", "style", "noscript", "svg", "iframe",
    "nav", "footer", "header",
    "#securityBox", "#view_top", "#view_t_bar", "#view_button", "#comment_tb",
    ".bbsV_prne", ".bbsV_data", ".snsBox", "#skipArea",
    "#lnb", "#gnb", "#webNavi", "#tabletGnb", "#mgnb", "#mNav", ".snb",
    ".subLocation", ".subvisual", "#quickMenu",
    "table.bbsView.page", ".btn_area",
)


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
    # 1. 노이즈 태그 제거
    for selector in NOISE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    # 2. 정밀 selector 우선 시도
    for selector in PRECISE_SELECTORS:
        for tag in soup.select(selector):
            text = _normalize_text(tag.get_text("\n", strip=True))
            if text:
                return text

    # 3. trafilatura 폴백
    extracted = _trafilatura_extract(str(soup))
    if extracted:
        normalized = _normalize_text(extracted)
        if normalized:
            return normalized

    # 4. body 전체 폴백
    body = soup.body or soup
    body_text = _normalize_text(body.get_text("\n", strip=True))
    return body_text if len(body_text) >= MIN_DETAIL_TEXT_LENGTH else ""


def _trafilatura_extract(html: str) -> str:
    try:
        import trafilatura  # type: ignore
    except ImportError:
        return ""
    try:
        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
        )
        return result or ""
    except Exception:
        return ""


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
