from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from extractor.models import InlineImageRef


# 본문만 정밀하게 잡는 selector (검증 완료)
PRECISE_SELECTORS = (
    "#viewConts",       # 광주 gen xboard CMS
    "div.conts",        # 인천 icees.kr boardCnts CMS
    "td.tch-ctnt",      # 울산/충북/전북 usm CMS
    ".bbsV_cont",       # 대구 dge / selectNtt CMS
)

# 정밀 selector 가 비어있을 때(본문이 이미지뿐이라 텍스트 0)의 텍스트 폴백 — 게시판 '본문 박스'
# 컨테이너들. 페이지 전체(body)로 폴백하면 메뉴/네비게이션까지 긁히므로, 그 전에 이 박스부터 본다.
# (.content/main 같은 너무 넓은 선택자는 제외 — nav 를 품을 수 있어 텍스트엔 안 쓴다.)
FALLBACK_CONTENT_SELECTORS = (
    ".subContent_body",
    "#usm-content-body-id",
    "table.usm-brd-vew",
    "table.bbsView",
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
)

# 이미지 추출용 광범위 컨테이너 (텍스트 추출엔 사용 안 함)
CONTENT_SELECTORS = PRECISE_SELECTORS + (
    ".subContent_body",
    "#usm-content-body-id",
    "table.usm-brd-vew",
    "table.bbsView",
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
    ".bbsV_data",
    ".snsBox",
    "#skipArea",
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
    "인쇄",
    "목록",
    "이전글",
    "다음글",
    "글작성 정보인 작성자, 작성일, 조회수 등을 제공합니다.",
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
    "/images/template/",
    "/common/",
    "/subimg/",
    # 레이아웃/스킨/장식 이미지 (공지 내용 아님). 예: dge/apple CMS의
    # /images/schl/web/<code>/sub/S_visual.png (서브 비주얼 배너),
    # /resource/images/schl/layout/alarm_ico.png (레이아웃 아이콘).
    "visual",
    "/images/schl/",
    "/resource/images/",
    "/layout/",
    "/skin/",
    "/template/",
    "_ico",
)


def extract_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 1. 노이즈 태그 제거
    for selector in NOISE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    # 2. 정밀 selector 우선 시도 (본문만 잡는 것들)
    for selector in PRECISE_SELECTORS:
        for tag in soup.select(selector):
            text = _clean_text(tag.get_text("\n", strip=True))
            if text:
                return text

    # 3. trafilatura 폴백 (노이즈 제거된 HTML 기준)
    extracted = _trafilatura_extract(str(soup))
    if extracted:
        cleaned = _clean_text(extracted)
        if cleaned:
            return cleaned

    # 4. 게시판 '본문 박스' 폴백 — body 전체(메뉴/네비 포함)로 가기 전에 본문 컨테이너부터.
    #    (정밀 selector 가 이미지뿐이라 비었던 공지에서 메뉴가 본문으로 새는 것을 막는다.)
    for selector in FALLBACK_CONTENT_SELECTORS:
        for tag in soup.select(selector):
            text = _clean_text(tag.get_text("\n", strip=True))
            if text:
                return text

    # 5. body 전체 폴백 (최후)
    body = soup.body or soup
    return _clean_text(body.get_text("\n", strip=True))


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
