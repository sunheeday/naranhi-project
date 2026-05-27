from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from extractor.models import InlineImageRef


CONTENT_SELECTORS = (
    "#viewConts",
    "table.bbsView",
    "div.conts",
    "#usm-content-body-id",
    "table.usm-brd-vew",
    ".subContent_body",
    ".bbsV_cont",
    ".board_view",
    ".view_cont",
    ".bbs_view",
    ".bbs_ViewA",
    ".view-content",
    ".board_view_cont",
    ".BD_view_table",
    ".board_view_table",
    ".view_table",
    ".detail_view",
    ".article",
    ".content",
    ".contents",
    "#contents",
    "#content",
    "main",
)

NOISE_SELECTORS = (
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    ".menu",
    ".gnb",
    ".lnb",
    ".skip",
    ".pagination",
    ".comment",
    ".reply",
    ".attach",
    ".attachment",
    ".file",
    ".fileArea",
    ".file_area",
    ".fileList",
    ".file_list",
    # 광주 gen xboard CMS
    "#securityBox",
    "#view_top",
    "#view_t_bar",
    "#view_button",
    "#comment_tb",
    # dge / selectNtt CMS
    ".bbsV_prne",
    # 공통 네비게이션
    "#lnb",
    "#gnb",
    "#webNavi",
    "#tabletGnb",
    "#mgnb",
    "#mNav",
    ".snb",
    # 브레드크럼 / 비주얼 / 퀵메뉴
    ".subLocation",
    ".subvisual",
    "#quickMenu",
    # boardCnts CMS
    "table.bbsView.page",
    ".btn_area",
)

NOISE_LINES = {
    "첨부",
    "첨부파일",
    "첨부 파일",
    "첨부파일 미리보기",
    "파일첨부",
    "미리보기",
    "바로듣기",
    "듣기",
    "preview",
}

IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|webp|bmp)(?:[?#].*)?$", re.IGNORECASE)
NOISE_IMAGE_TERMS = (
    "logo",
    "icon",
    "banner",
    "btn_",
    "bul_",
    "sns",
    "facebook",
    "twitter",
    "/images/web/",
    "/common/",
    "/subimg/",
)


def extract_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in NOISE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    candidates: list[str] = []
    for selector in CONTENT_SELECTORS:
        for tag in soup.select(selector):
            text = _clean_text(tag.get_text("\n", strip=True))
            if text:
                candidates.append(text)

    if not candidates:
        body = soup.body or soup
        candidates.append(_clean_text(body.get_text("\n", strip=True)))

    return _best_text(candidates)


def extract_inline_images(base_url: str, html: str) -> list[InlineImageRef]:
    soup = BeautifulSoup(html, "html.parser")
    refs: list[InlineImageRef] = []
    seen: set[str] = set()
    roots = _content_roots(soup)
    images = []
    for root in roots:
        images.extend(root.find_all("img"))
    if not images:
        images = soup.find_all("img")

    for image in images:
        src = (image.get("src") or image.get("data-src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        url = urljoin(base_url, src)
        lowered = url.lower()
        if not IMAGE_EXT_RE.search(lowered):
            continue
        if any(term in lowered for term in NOISE_IMAGE_TERMS):
            continue
        if url in seen:
            continue
        seen.add(url)
        alt = _clean_text(image.get("alt") or "")
        parent_text = _clean_text(image.parent.get_text(" ", strip=True) if image.parent else "")
        refs.append(InlineImageRef(url=url, alt=alt, source_text=parent_text[:200]))
    return refs


def _content_roots(soup: BeautifulSoup) -> list[Any]:
    roots = []
    for selector in CONTENT_SELECTORS:
        for tag in soup.select(selector):
            if tag not in roots:
                roots.append(tag)
        if roots:
            return roots
    return []


def _best_text(candidates: list[str]) -> str:
    cleaned = [_clean_text(item) for item in candidates if _clean_text(item)]
    if not cleaned:
        return ""
    meaningful = [
        item for item in cleaned
        if not _looks_like_navigation_dump(item)
    ]
    pool = meaningful or cleaned
    return max(pool, key=len)


def _looks_like_navigation_dump(text: str) -> bool:
    if len(text) < 80:
        return False
    menu_terms = sum(text.count(term) for term in ("로그인", "회원가입", "사이트맵", "메뉴", "학교소개", "알림마당"))
    content_terms = sum(text.count(term) for term in ("작성자", "등록일", "첨부", "가정통신문", "공지"))
    return menu_terms >= 5 and content_terms == 0


def _clean_text(value: str) -> str:
    lines = []
    for raw_line in value.replace("\r", "\n").split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if line.lower() in NOISE_LINES:
            continue
        lines.append(line)
    return "\n".join(lines)
