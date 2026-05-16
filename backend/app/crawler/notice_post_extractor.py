from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
import httpx

from app.crawler.cms_patterns import CmsDetection
from app.crawler.homepage_client import extract_js_redirect_url
from app.crawler.http_client import DEFAULT_HEADERS, make_async_client_for_url, with_retries
from app.crawler.link_extractor import page_snippet, page_title
from app.crawler.unknown_post_resolver import UnknownPostGeminiResolver


DATE_RE = re.compile(r"\b20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}\b")
NUMBER_RE = re.compile(r"\d+")
SLASH_VIEW_RE = re.compile(r"/view/(\d+)")
NEGATIVE_ROW_TERMS = ("급식", "식단", "갤러리", "사진", "일정", "달력", "로그인", "회원가입")
DETAIL_ID_KEYS = ("nttSn", "boardSeq", "nttId", "articleId", "number", "seq", "num", "id")


@dataclass(frozen=True)
class NoticePostRef:
    cms_key: str
    parser_family: str
    board_url: str
    board_key: str
    post_id: str
    post_uid: str
    title: str
    detail_url: str
    detail_method: str
    detail_access_ok: bool
    status: str
    post_id_source: str
    reason: str = ""
    gemini_used: bool = False


@dataclass(frozen=True)
class NoticePostRefResult:
    board_url: str
    board_final_url: str
    page_title: str
    cms: CmsDetection
    parser_family: str
    status: str
    posts: list[NoticePostRef]
    total_candidates: int
    success_count: int
    gemini_used: bool
    error: str | None = None


@dataclass
class _RawPostCandidate:
    row_id: str
    title: str
    row_text: str
    board_key: str
    post_id: str
    post_id_source: str
    detail_method: str
    url_candidates: list[str]
    explicit_id: bool = True
    gemini_used: bool = False


async def extract_notice_post_refs(
    *,
    board_url: str,
    cms: CmsDetection,
    warmup_url: str | None,
    gemini_api_key: str | None = None,
    max_posts: int = 30,
) -> NoticePostRefResult:
    if cms.key == "schoolbell" or "schoolbell-e.com" in urlparse(board_url).netloc:
        return NoticePostRefResult(
            board_url=board_url,
            board_final_url=board_url,
            page_title="",
            cms=cms,
            parser_family="schoolbell",
            status="unsupported_external_dynamic",
            posts=[],
            total_candidates=0,
            success_count=0,
            gemini_used=False,
            error="학교종이 외부 SPA는 정적 HTML에서 상세글 구분값을 안정적으로 추출하기 어렵습니다.",
        )

    try:
        async with make_async_client_for_url(url=board_url, timeout=20.0) as client:
            referer = warmup_url
            if warmup_url:
                warmup_response = await _get_following_js_redirect(client, warmup_url)
                referer = str(warmup_response.url)

            headers = dict(DEFAULT_HEADERS)
            if referer and _same_origin(referer, board_url):
                headers["Referer"] = referer

            board_response = await _get_following_js_redirect(client, board_url, headers=headers)
            board_html = board_response.text
            board_final_url = str(board_response.url)
            title = page_title(board_html)

            access_status = _classify_access_failure(
                url=board_final_url,
                status_code=board_response.status_code,
                html=board_html,
            )
            if access_status:
                return NoticePostRefResult(
                    board_url=board_url,
                    board_final_url=board_final_url,
                    page_title=title,
                    cms=cms,
                    parser_family=_detect_parser_family(board_final_url, board_html, cms),
                    status=access_status,
                    posts=[],
                    total_candidates=0,
                    success_count=0,
                    gemini_used=False,
                    error=access_status,
                )

            parser_family = _detect_parser_family(board_final_url, board_html, cms)
            soup = BeautifulSoup(board_html, "html.parser")
            if parser_family == "sen_like":
                ajax_html = await _fetch_sen_list_ajax(
                    client=client,
                    board_url=board_final_url,
                    soup=soup,
                    referer=referer or board_final_url,
                )
                if ajax_html:
                    board_html = f"{board_html}\n{ajax_html}"
                    soup = BeautifulSoup(board_html, "html.parser")

            raw_candidates = _extract_raw_candidates(
                board_url=board_final_url,
                html=board_html,
                soup=soup,
                parser_family=parser_family,
                max_posts=max_posts,
            )

            gemini_used = False
            if parser_family == "generic" and not raw_candidates:
                resolver = UnknownPostGeminiResolver(gemini_api_key)
                gemini_rows = await resolver.choose_post_rows(
                    board_url=board_final_url,
                    page_title=title,
                    forms=_summarize_forms(soup),
                    script_snippets=_extract_detail_script_snippets(board_html),
                    row_candidates=_summarize_row_candidates(soup),
                )
                raw_candidates = _raw_candidates_from_gemini(
                    board_final_url,
                    soup,
                    gemini_rows,
                    max_posts=max_posts,
                )
                gemini_used = bool(gemini_rows)

            if parser_family == "generic" and gemini_api_key:
                raw_candidates = await _order_unknown_candidates_with_gemini(
                    raw_candidates=raw_candidates,
                    board_url=board_final_url,
                    html=board_html,
                    gemini_api_key=gemini_api_key,
                )
                gemini_used = gemini_used or any(item.gemini_used for item in raw_candidates)

            posts: list[NoticePostRef] = []
            for candidate in raw_candidates[:max_posts]:
                post = await _validate_candidate(
                    client=client,
                    candidate=candidate,
                    board_url=board_final_url,
                    cms=cms,
                    parser_family=parser_family,
                    referer=referer or board_final_url,
                    gemini_api_key=gemini_api_key,
                )
                posts.append(post)

    except Exception as exc:  # noqa: BLE001 - POC returns status for UI/report.
        return NoticePostRefResult(
            board_url=board_url,
            board_final_url=board_url,
            page_title="",
            cms=cms,
            parser_family="unknown",
            status="parse_failed",
            posts=[],
            total_candidates=0,
            success_count=0,
            gemini_used=False,
            error=f"{type(exc).__name__}: {exc}",
        )

    success_count = sum(1 for item in posts if item.status in {"success", "success_with_derived_id", "success_file_only"})
    if success_count:
        status = "detail_entry_success"
    elif not raw_candidates:
        status = "no_posts"
    elif posts and all(item.reason == "unsupported_login_required" for item in posts):
        status = "unsupported_login_required"
    else:
        status = "detail_url_failed"

    return NoticePostRefResult(
        board_url=board_url,
        board_final_url=board_final_url,
        page_title=title,
        cms=cms,
        parser_family=parser_family,
        status=status,
        posts=posts,
        total_candidates=len(raw_candidates),
        success_count=success_count,
        gemini_used=gemini_used or any(item.gemini_used for item in posts),
        error=None,
    )


def _detect_parser_family(board_url: str, html: str, cms: CmsDetection) -> str:
    host = urlparse(board_url).netloc.lower()
    haystack = f"{board_url} {html[:80000]}"

    if "/c2zHome" in board_url or "homn_filedown.php" in haystack:
        return "gen_c2z_home_like"
    if cms.key in {"jbedu", "use", "cbe"}:
        return "slash_view_like"
    if SLASH_VIEW_RE.search(haystack) or re.search(r"/M\d+/?", urlparse(board_url).path):
        return "slash_view_like"
    if cms.key in {"select_ntt", "busanedu", "dge", "jje"}:
        return "select_ntt_like"
    if cms.key in {"boardcnts", "cnems_boardcnts"}:
        return "boardcnts_like"
    if cms.key == "gen_xboard":
        return "xboard_like"
    if cms.key == "sen":
        return "sen_like"

    if "school.use.go.kr" in host or "school.cbe.go.kr" in host or SLASH_VIEW_RE.search(haystack):
        return "slash_view_like"
    if "selectNttInfo.do" in haystack or "nttInfoBtn" in haystack:
        return "select_ntt_like"
    if "boardCnts" in haystack and "goView" in haystack:
        return "boardcnts_like"
    if "board.php" in haystack and "mode=view" in haystack:
        return "xboard_like"
    if "subMenu.do" in haystack and ("nttId" in haystack or "bbsId" in haystack):
        return "sen_like"
    return "generic"


def _extract_raw_candidates(
    *,
    board_url: str,
    html: str,
    soup: BeautifulSoup,
    parser_family: str,
    max_posts: int,
) -> list[_RawPostCandidate]:
    if parser_family == "select_ntt_like":
        candidates = _extract_select_ntt_candidates(board_url, soup)
    elif parser_family == "boardcnts_like":
        candidates = _extract_boardcnts_candidates(board_url, soup)
    elif parser_family == "slash_view_like":
        candidates = _extract_slash_view_candidates(board_url, soup)
    elif parser_family == "xboard_like":
        candidates = _extract_xboard_candidates(board_url, soup)
    elif parser_family == "gen_c2z_home_like":
        candidates = _extract_c2z_home_candidates(board_url, soup)
    elif parser_family == "sen_like":
        candidates = _extract_sen_candidates(board_url, html, soup)
    else:
        candidates = _extract_generic_candidates(board_url, soup)

    return _dedupe_raw_candidates(candidates)[:max_posts]


def _extract_select_ntt_candidates(board_url: str, soup: BeautifulSoup) -> list[_RawPostCandidate]:
    params = _board_params(board_url, soup)
    mi = _first(params, "mi")
    bbs_id = _first(params, "bbsId")
    board_key = f"mi={mi}|bbsId={bbs_id}" if mi or bbs_id else _board_key_from_url(board_url)
    info_path = _replace_path_suffix(board_url, "selectNttList.do", "selectNttInfo.do")
    candidates: list[_RawPostCandidate] = []

    for index, anchor in enumerate(soup.find_all("a")):
        href = (anchor.get("href") or "").strip()
        text = _clean_text(anchor.get_text(" ", strip=True))

        if "selectNttInfo.do" in href:
            detail_url = urljoin(board_url, href)
            query = parse_qs(urlparse(detail_url).query)
            post_id = _first(query, "nttSn") or _first(query, "nttId") or _first(query, "articleId")
            if post_id:
                candidates.append(
                    _RawPostCandidate(
                        row_id=f"S{index}",
                        title=text or _row_text(anchor),
                        row_text=_row_text(anchor),
                        board_key=board_key,
                        post_id=post_id,
                        post_id_source="href query",
                        detail_method="href",
                        url_candidates=[detail_url],
                    )
                )
            continue

        data_id = _data_id(anchor)
        classes = anchor.get("class") or []
        if data_id and ("nttInfoBtn" in classes or href.lower().startswith("javascript")):
            detail_url = _build_select_ntt_detail_url(info_path, mi, bbs_id, data_id)
            candidates.append(
                _RawPostCandidate(
                    row_id=f"S{index}",
                    title=text or _row_text(anchor),
                    row_text=_row_text(anchor),
                    board_key=board_key,
                    post_id=data_id,
                    post_id_source="data-id",
                    detail_method="data_id",
                    url_candidates=[detail_url],
                )
            )

    return candidates


def _extract_boardcnts_candidates(board_url: str, soup: BeautifulSoup) -> list[_RawPostCandidate]:
    board_query = parse_qs(urlparse(board_url).query)
    board_id = _first(board_query, "boardID")
    menu = _first(board_query, "m")
    site = _first(board_query, "s")
    board_key = f"boardID={board_id}|m={menu}|s={site}"
    candidates: list[_RawPostCandidate] = []

    for index, anchor in enumerate(soup.find_all("a")):
        href = (anchor.get("href") or "").strip()
        onclick = anchor.get("onclick") or ""
        text = _clean_text(anchor.get_text(" ", strip=True))

        if "boardCnts/view.do" in href:
            detail_url = urljoin(board_url, href)
            query = parse_qs(urlparse(detail_url).query)
            post_id = _first(query, "boardSeq")
            if post_id:
                candidates.append(
                    _RawPostCandidate(
                        row_id=f"B{index}",
                        title=text or _row_text(anchor),
                        row_text=_row_text(anchor),
                        board_key=board_key,
                        post_id=post_id,
                        post_id_source="href query boardSeq",
                        detail_method="href",
                        url_candidates=[detail_url],
                    )
                )

        if "goView" in onclick:
            args = _parse_js_args(onclick)
            if len(args) >= 2:
                signature = _go_view_signature(soup)
                row_board_id, view_board_id, post_id, lev, status, page, page_size = _interpret_go_view_args(
                    args=args,
                    signature=signature,
                    fallback_board_id=board_id,
                    fallback_page=_first(board_query, "page") or "1",
                )
                candidates.append(
                    _RawPostCandidate(
                        row_id=f"B{index}",
                        title=text or _row_text(anchor),
                        row_text=_row_text(anchor),
                        board_key=f"boardID={row_board_id}|m={menu}|s={site}",
                        post_id=post_id,
                        post_id_source="onclick goView arg 3",
                        detail_method="onclick",
                        url_candidates=_build_boardcnts_urls(
                            board_url,
                            row_board_id,
                            view_board_id,
                            post_id,
                            lev,
                            status,
                            page,
                            menu,
                            site,
                            page_size,
                            signature,
                        ),
                    )
                )

    return candidates


def _extract_slash_view_candidates(board_url: str, soup: BeautifulSoup) -> list[_RawPostCandidate]:
    candidates: list[_RawPostCandidate] = []
    for index, anchor in enumerate(soup.find_all("a")):
        href = (anchor.get("href") or "").strip()
        if "fileDownload" in href or "_cmm/file" in href:
            continue
        match = SLASH_VIEW_RE.search(href)
        if not match:
            continue
        detail_url = urljoin(board_url, href)
        board_path = urlparse(detail_url).path.split("/view/", 1)[0].rstrip("/") + "/"
        title = _clean_text(anchor.get_text(" ", strip=True)) or _row_text(anchor)
        candidates.append(
            _RawPostCandidate(
                row_id=f"V{index}",
                title=title,
                row_text=_row_text(anchor),
                board_key=board_path,
                post_id=match.group(1),
                post_id_source="path /view/",
                detail_method="href",
                url_candidates=[detail_url],
            )
        )
    return candidates


def _extract_xboard_candidates(board_url: str, soup: BeautifulSoup) -> list[_RawPostCandidate]:
    candidates: list[_RawPostCandidate] = []
    for index, anchor in enumerate(soup.find_all("a")):
        href = (anchor.get("href") or "").strip()
        if "cms.php" in href and "dk_id=" in href:
            detail_url = urljoin(board_url, href)
            query = parse_qs(urlparse(detail_url).query)
            post_id = _first(query, "dk_id")
            board_id = _first(query, "dk_cms") or _first(parse_qs(urlparse(board_url).query), "dk_cms")
            if not post_id:
                continue
            candidates.append(
                _RawPostCandidate(
                    row_id=f"G{index}",
                    title=_clean_text(anchor.get_text(" ", strip=True)) or _row_text(anchor),
                    row_text=_row_text(anchor),
                    board_key=f"dk_cms={board_id}",
                    post_id=post_id,
                    post_id_source="href query dk_id",
                    detail_method="href",
                    url_candidates=[detail_url],
                )
            )
            continue

        if "board.php" not in href or "mode=view" not in href:
            continue

        detail_url = urljoin(board_url, href)
        query = parse_qs(urlparse(detail_url).query)
        post_id = _first(query, "number") or _first(query, "num")
        tbnum = _first(query, "tbnum")
        if not post_id:
            continue
        candidates.append(
            _RawPostCandidate(
                row_id=f"X{index}",
                title=_clean_text(anchor.get_text(" ", strip=True)) or _row_text(anchor),
                row_text=_row_text(anchor),
                board_key=f"tbnum={tbnum}",
                post_id=post_id,
                post_id_source="href query number",
                detail_method="href",
                url_candidates=[detail_url],
            )
        )
    return candidates


def _extract_c2z_home_candidates(board_url: str, soup: BeautifulSoup) -> list[_RawPostCandidate]:
    candidates: list[_RawPostCandidate] = []
    rows = soup.select("#listTable tbody tr") or soup.select("table tbody tr")
    for index, row in enumerate(rows):
        row_text = _clean_text(row.get_text(" ", strip=True))
        if not row_text or not DATE_RE.search(row_text):
            continue

        onclick = ""
        for tag in row.find_all(True):
            value = tag.get("onclick") or ""
            if "homn_filedown.php" in value:
                onclick = value
                break
        if not onclick:
            continue

        url_match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+homn_filedown\.php\?[^'\"]+)['\"]", onclick)
        if not url_match:
            continue

        detail_url = urljoin(board_url, url_match.group(1))
        query = parse_qs(urlparse(detail_url).query)
        post_id = _first(query, "hno")
        if not post_id:
            continue

        title_cell = row.select_one(".a_left")
        title = _clean_text(title_cell.get_text(" ", strip=True)) if title_cell else row_text
        candidates.append(
            _RawPostCandidate(
                row_id=f"C{index}",
                title=title,
                row_text=row_text,
                board_key=_board_key_from_url(board_url),
                post_id=post_id,
                post_id_source="onclick hno",
                detail_method="file_download",
                url_candidates=[detail_url],
            )
        )
    return candidates


def _extract_sen_candidates(board_url: str, html: str, soup: BeautifulSoup) -> list[_RawPostCandidate]:
    candidates: list[_RawPostCandidate] = []
    menu_no = next((item for item in urlparse(board_url).path.split("/") if item.isdigit()), "")

    for index, anchor in enumerate(soup.find_all("a")):
        onclick = anchor.get("onclick") or ""
        if "fnView" not in onclick:
            continue
        args = _parse_js_args(onclick)
        if len(args) < 2:
            continue
        bbs_id, ntt_id = args[0], args[1]
        if {bbs_id, ntt_id} & {"bbsId", "nttId"}:
            continue
        detail_query = urlencode({"nttId": ntt_id})
        candidates.append(
            _RawPostCandidate(
                row_id=f"N{index}",
                title=_clean_text(anchor.get_text(" ", strip=True)) or f"nttId {ntt_id}",
                row_text=_row_text(anchor),
                board_key=f"menuNo={menu_no}|bbsId={bbs_id}",
                post_id=ntt_id,
                post_id_source="onclick fnView arg 2",
                detail_method="ajax_get",
                url_candidates=[urljoin(board_url, f"/dggb/module/board/selectBoardDetailAjax.do?{detail_query}")],
            )
        )

    for index, match in enumerate(re.finditer(r"fnBoardPage(?:_\d+)?\(([^)]*)\)", html)):
        args = _parse_js_args(match.group(0))
        if len(args) < 3:
            continue
        bbs_id, ntt_id, menu_no = args[0], args[1], args[2]
        if {bbs_id, ntt_id, menu_no} & {"bbsId", "nttId", "menuNo"}:
            continue
        detail_url = urljoin(board_url, f"/{menu_no}/subMenu.do")
        candidates.append(
            _RawPostCandidate(
                row_id=f"N{index}",
                title=f"nttId {ntt_id}",
                row_text=match.group(0),
                board_key=f"menuNo={menu_no}|bbsId={bbs_id}",
                post_id=ntt_id,
                post_id_source="fnBoardPage arg 2",
                detail_method="form",
                url_candidates=[detail_url],
            )
        )

    for index, anchor in enumerate(soup.find_all("a")):
        onclick = anchor.get("onclick") or ""
        if "fnBoardPage" not in onclick:
            continue
        args = _parse_js_args(onclick)
        if len(args) < 3:
            continue
        bbs_id, ntt_id, menu_no = args[0], args[1], args[2]
        if {bbs_id, ntt_id, menu_no} & {"bbsId", "nttId", "menuNo"}:
            continue
        candidates.append(
            _RawPostCandidate(
                row_id=f"N{index}",
                title=_clean_text(anchor.get_text(" ", strip=True)) or f"nttId {ntt_id}",
                row_text=_row_text(anchor),
                board_key=f"menuNo={menu_no}|bbsId={bbs_id}",
                post_id=ntt_id,
                post_id_source="onclick fnBoardPage",
                detail_method="onclick",
                url_candidates=[urljoin(board_url, f"/{menu_no}/subMenu.do")],
            )
        )
    return candidates


def _extract_generic_candidates(board_url: str, soup: BeautifulSoup) -> list[_RawPostCandidate]:
    candidates: list[_RawPostCandidate] = []
    candidates.extend(_extract_select_ntt_candidates(board_url, soup))
    candidates.extend(_extract_boardcnts_candidates(board_url, soup))
    candidates.extend(_extract_slash_view_candidates(board_url, soup))
    candidates.extend(_extract_xboard_candidates(board_url, soup))
    candidates.extend(_extract_generic_href_candidates(board_url, soup))
    return candidates


def _extract_generic_href_candidates(board_url: str, soup: BeautifulSoup) -> list[_RawPostCandidate]:
    candidates: list[_RawPostCandidate] = []
    for index, row in enumerate(_row_elements(soup)):
        row_score = _score_row(row)
        if row_score <= 0:
            continue
        row_text = _clean_text(row.get_text(" ", strip=True))
        for anchor in row.find_all("a"):
            href = (anchor.get("href") or "").strip()
            if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
                continue
            if "fileDownload" in href or "download" in href.lower():
                continue
            detail_url = urljoin(board_url, href)
            post_id, source, explicit = _post_id_from_url(detail_url)
            if not post_id:
                post_id = hashlib.sha1(_normalize_url(detail_url).encode("utf-8")).hexdigest()[:12]
                source = "derived detail_url hash"
                explicit = False
            title = _clean_text(anchor.get_text(" ", strip=True)) or row_text[:80]
            candidates.append(
                _RawPostCandidate(
                    row_id=f"G{index}",
                    title=title,
                    row_text=row_text,
                    board_key=_board_key_from_url(board_url),
                    post_id=post_id,
                    post_id_source=source,
                    detail_method="href" if explicit else "generated",
                    url_candidates=[detail_url],
                    explicit_id=explicit,
                )
            )
    return candidates


async def _validate_candidate(
    *,
    client: httpx.AsyncClient,
    candidate: _RawPostCandidate,
    board_url: str,
    cms: CmsDetection,
    parser_family: str,
    referer: str,
    gemini_api_key: str | None,
) -> NoticePostRef:
    headers = dict(DEFAULT_HEADERS)
    if _same_origin(referer, board_url):
        headers["Referer"] = referer

    last_reason = ""
    attempted: list[tuple[str, int | None, str, str, str]] = []
    for detail_url in candidate.url_candidates:
        try:
            response = await _get_following_js_redirect(client, detail_url, headers=headers)
            html = response.text
            final_url = str(response.url)
            title = page_title(html)
            snippet = page_snippet(html, 800)
            attempted.append((detail_url, response.status_code, final_url, title, snippet))
            failure = _classify_access_failure(
                url=final_url,
                status_code=response.status_code,
                html=html,
            )
            if failure:
                last_reason = failure
                continue
            if _looks_like_file_detail_success(response):
                return _post_ref(
                    candidate=candidate,
                    cms=cms,
                    parser_family=parser_family,
                    detail_url=final_url,
                    status="success_file_only",
                    access_ok=True,
                    reason="상세 페이지 없이 파일 다운로드 URL로 가정통신문 문서 접속 검증 성공",
                )
            if _looks_like_detail_success(
                board_url=board_url,
                detail_url=detail_url,
                final_url=final_url,
                html=html,
                row_title=candidate.title,
                post_id=candidate.post_id,
            ):
                status = "success" if candidate.explicit_id else "success_with_derived_id"
                return _post_ref(
                    candidate=candidate,
                    cms=cms,
                    parser_family=parser_family,
                    detail_url=final_url,
                    status=status,
                    access_ok=True,
                    reason="상세 페이지 접속 검증 성공",
                )
            last_reason = "상세 페이지로 검증되지 않았습니다."
        except Exception as exc:  # noqa: BLE001 - try next candidate URL.
            last_reason = f"{type(exc).__name__}: {exc}"

    if parser_family == "generic" and gemini_api_key and attempted:
        resolver = UnknownPostGeminiResolver(gemini_api_key)
        last = attempted[-1]
        classification = await resolver.classify_failure(
            attempted_url=last[0],
            status_code=last[1],
            final_url=last[2],
            title=last[3],
            snippet=last[4],
            row_title=candidate.title,
        )
        if classification:
            last_reason = classification.reason or classification.classification
            return _post_ref(
                candidate=candidate,
                cms=cms,
                parser_family=parser_family,
                detail_url=attempted[-1][2],
                status=classification.classification,
                access_ok=False,
                reason=last_reason,
                gemini_used=True,
            )

    status = "no_post_id" if not candidate.post_id else "detail_url_failed"
    return _post_ref(
        candidate=candidate,
        cms=cms,
        parser_family=parser_family,
        detail_url=candidate.url_candidates[0] if candidate.url_candidates else "",
        status=status,
        access_ok=False,
        reason=last_reason,
    )


async def _order_unknown_candidates_with_gemini(
    *,
    raw_candidates: list[_RawPostCandidate],
    board_url: str,
    html: str,
    gemini_api_key: str,
) -> list[_RawPostCandidate]:
    if not raw_candidates:
        return raw_candidates

    resolver = UnknownPostGeminiResolver(gemini_api_key)
    script_snippets = _extract_detail_script_snippets(html)
    ordered: list[_RawPostCandidate] = []
    for candidate in raw_candidates:
        if len(candidate.url_candidates) <= 1:
            ordered.append(candidate)
            continue
        url_items = [
            {"candidate_id": f"U{index}", "url": url}
            for index, url in enumerate(candidate.url_candidates)
        ]
        order = await resolver.order_url_candidates(
            row_id=candidate.row_id,
            post_id=candidate.post_id,
            board_url=board_url,
            url_candidates=url_items,
            script_snippets=script_snippets,
        )
        if not order or not order.ordered_candidate_ids:
            ordered.append(candidate)
            continue
        by_id = {f"U{index}": url for index, url in enumerate(candidate.url_candidates)}
        new_urls = [by_id[item] for item in order.ordered_candidate_ids if item in by_id]
        new_urls.extend(url for url in candidate.url_candidates if url not in new_urls)
        candidate.url_candidates = new_urls
        candidate.gemini_used = True
        ordered.append(candidate)
    return ordered


def _raw_candidates_from_gemini(
    board_url: str,
    soup: BeautifulSoup,
    choices: list[Any],
    *,
    max_posts: int,
) -> list[_RawPostCandidate]:
    row_map = {item["row_id"]: item for item in _summarize_row_candidates(soup)}
    candidates: list[_RawPostCandidate] = []
    for choice in choices:
        if not choice.is_post or not choice.post_id_candidate:
            continue
        row = row_map.get(choice.row_id, {})
        urls = _generic_urls_from_post_id(board_url, choice.post_id_candidate)
        candidates.append(
            _RawPostCandidate(
                row_id=choice.row_id,
                title=choice.title or str(row.get("text") or "")[:80],
                row_text=str(row.get("text") or ""),
                board_key=_board_key_from_url(board_url),
                post_id=choice.post_id_candidate,
                post_id_source=choice.post_id_source,
                detail_method="generated",
                url_candidates=urls,
                explicit_id=True,
                gemini_used=True,
            )
        )
    return candidates[:max_posts]


def _post_ref(
    *,
    candidate: _RawPostCandidate,
    cms: CmsDetection,
    parser_family: str,
    detail_url: str,
    status: str,
    access_ok: bool,
    reason: str,
    gemini_used: bool | None = None,
) -> NoticePostRef:
    uid = f"{cms.key}:{candidate.board_key}:{candidate.post_id}"
    return NoticePostRef(
        cms_key=cms.key,
        parser_family=parser_family,
        board_url=candidate.url_candidates[0] if candidate.url_candidates else "",
        board_key=candidate.board_key,
        post_id=candidate.post_id,
        post_uid=uid,
        title=candidate.title,
        detail_url=detail_url,
        detail_method=candidate.detail_method,
        detail_access_ok=access_ok,
        status=status,
        post_id_source=candidate.post_id_source,
        reason=reason,
        gemini_used=candidate.gemini_used if gemini_used is None else gemini_used,
    )


def _build_select_ntt_detail_url(info_path: str, mi: str | None, bbs_id: str | None, post_id: str) -> str:
    query = []
    if mi:
        query.append(("mi", mi))
    if bbs_id:
        query.append(("bbsId", bbs_id))
    query.append(("nttSn", post_id))
    parsed = urlparse(info_path)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(query), ""))


def _build_boardcnts_urls(
    board_url: str,
    board_id: str,
    view_board_id: str,
    post_id: str,
    lev: str,
    status: str,
    page: str,
    menu: str | None,
    site: str | None,
    page_size: str | None = None,
    signature: str | None = None,
) -> list[str]:
    base = f"{urlparse(board_url).scheme}://{urlparse(board_url).netloc}"
    common = [
        ("boardID", board_id),
        ("boardSeq", post_id),
        ("lev", lev or "0"),
        ("searchType", "null"),
        ("statusYN", status or "W"),
        ("page", page or "1"),
    ]
    if view_board_id and signature != "daejeon":
        common.insert(1, ("viewBoardID", view_board_id))
        common.insert(4, ("action", "view"))
    if page_size:
        common.append(("pSize", page_size))
    if site:
        common.append(("s", site))
    if menu:
        common.append(("m", menu))
    if signature == "daejeon":
        common.append(("opType", "N"))

    update_query = common[:]
    if signature != "daejeon":
        update_query.insert(6, ("srch2", "null"))
    return [
        f"{base}/boardCnts/view.do?{urlencode(common)}",
        f"{base}/boardCnts/updateCnt.do?{urlencode(update_query)}",
    ]


def _generic_urls_from_post_id(board_url: str, post_id: str) -> list[str]:
    parsed = urlparse(board_url)
    urls: list[str] = []
    if parsed.path.endswith("selectNttList.do"):
        params = parse_qs(parsed.query)
        urls.append(
            _build_select_ntt_detail_url(
                urlunparse((parsed.scheme, parsed.netloc, parsed.path.replace("selectNttList.do", "selectNttInfo.do"), "", "", "")),
                _first(params, "mi"),
                _first(params, "bbsId"),
                post_id,
            )
        )
    if parsed.path.endswith("list.do") and "boardCnts" in parsed.path:
        params = parse_qs(parsed.query)
        urls.extend(
            _build_boardcnts_urls(
                board_url,
                _first(params, "boardID") or "",
                _first(params, "boardID") or "",
                post_id,
                "0",
                "W",
                _first(params, "page") or "1",
                _first(params, "m"),
                _first(params, "s"),
                None,
                None,
            )
        )
    urls.append(urljoin(board_url.rstrip("/") + "/", f"view/{post_id}"))
    parsed_query = parse_qs(parsed.query)
    parsed_query["id"] = [post_id]
    urls.append(urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(parsed_query, doseq=True), "")))
    return _dedupe_strings(urls)


def _go_view_signature(soup: BeautifulSoup) -> str:
    html = str(soup)
    match = re.search(r"function\s+goView\s*\(([^)]*)\)", html)
    if not match:
        return "unknown"
    params = [item.strip() for item in match.group(1).split(",")]
    if len(params) >= 2 and "reqBoardSeq" in params[1]:
        return "daejeon"
    if len(params) >= 3 and "reqBoardSeq" in params[2]:
        return "cnems"
    return "unknown"


def _interpret_go_view_args(
    *,
    args: list[str],
    signature: str,
    fallback_board_id: str | None,
    fallback_page: str,
) -> tuple[str, str, str, str, str, str, str | None]:
    if signature == "daejeon":
        row_board_id = args[0] if len(args) > 0 else fallback_board_id or ""
        view_board_id = row_board_id
        post_id = args[1] if len(args) > 1 else ""
        lev = args[2] if len(args) > 2 else "0"
        status = args[4] if len(args) > 4 else "W"
        page = args[5] if len(args) > 5 else fallback_page
        page_size = args[6] if len(args) > 6 else None
        return row_board_id, view_board_id, post_id, lev, status, page, page_size

    row_board_id = args[0] if len(args) > 0 else fallback_board_id or ""
    view_board_id = args[1] if len(args) > 1 else row_board_id
    post_id = args[2] if len(args) > 2 else ""
    lev = args[3] if len(args) > 3 else "0"
    status = args[5] if len(args) > 5 else "W"
    page = args[6] if len(args) > 6 else fallback_page
    return row_board_id, view_board_id, post_id, lev, status, page, None


def _post_id_from_url(url: str) -> tuple[str | None, str, bool]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in DETAIL_ID_KEYS:
        value = _first(query, key)
        if value and NUMBER_RE.search(value):
            return value, f"href query {key}", True

    match = SLASH_VIEW_RE.search(parsed.path)
    if match:
        return match.group(1), "path /view/", True

    number_segments = [item for item in parsed.path.split("/") if item.isdigit()]
    if number_segments:
        return number_segments[-1], "path numeric segment", True
    return None, "", False


def _looks_like_detail_success(
    *,
    board_url: str,
    detail_url: str,
    final_url: str,
    html: str,
    row_title: str,
    post_id: str,
) -> bool:
    title = page_title(html)
    snippet = page_snippet(html, 1000)
    haystack = _compact(f"{final_url} {title} {snippet}")
    row_compact = _compact(row_title)

    if _normalize_url(final_url) == _normalize_url(board_url):
        return False
    if row_compact and len(row_compact) >= 8 and row_compact[:30] in haystack:
        return True
    if post_id and post_id in final_url:
        return True
    if post_id and post_id in html and any(term in f"{title} {snippet}" for term in ("작성자", "등록일", "첨부", "조회")):
        return True
    if any(term in f"{title} {snippet}" for term in ("작성자", "등록일", "첨부파일", "조회수")) and len(snippet) > 120:
        return True
    return False


def _looks_like_file_detail_success(response: httpx.Response) -> bool:
    content_type = (response.headers.get("content-type") or "").lower()
    content_disposition = (response.headers.get("content-disposition") or "").lower()
    url = str(response.url).lower()
    if response.status_code != 200:
        return False
    if "attachment" in content_disposition:
        return True
    if any(token in url for token in ("filedown", "download", "fileDownload".lower())) and "text/html" not in content_type:
        return True
    return False


def _classify_access_failure(*, url: str, status_code: int | None, html: str) -> str | None:
    text = f"{url} {page_title(html)} {page_snippet(html, 500)}"
    lowered = text.lower()
    html_lowered = html.lower()
    url_lowered = url.lower()
    if status_code in {401, 403}:
        return "unsupported_forbidden"
    if "schoolbell-e.com" in urlparse(url).netloc:
        return "unsupported_external_dynamic"
    if "mode=login" in url_lowered:
        return "unsupported_login_required"
    if "loginpost.php" in html_lowered and "fm_xb_login" in html_lowered:
        return "unsupported_login_required"
    if "authreaderror" in lowered or "게시판 접근 권한" in text or "권한이 없습니다" in text:
        return "unsupported_login_required"
    if "로그인이 필요" in text or _looks_like_login_only_page(html) or "비공개 설정된 글" in text or "authorization required" in lowered:
        return "unsupported_login_required"
    return None


def _looks_like_login_only_page(html: str) -> bool:
    text = page_snippet(html, 2000)
    compact = _compact(text)
    if "로그인후이용" not in compact:
        return False
    public_board_markers = (
        "게시판목록",
        "총",
        "작성일",
        "조회수",
        "등록일",
        "첨부파일",
        "selectboardlistajax",
        "fnview",
        "selectnttinfo",
        "boardcnts/view",
    )
    if DATE_RE.search(text):
        return False
    if any(marker in compact for marker in public_board_markers):
        return False
    return True


async def _fetch_sen_list_ajax(
    *,
    client: httpx.AsyncClient,
    board_url: str,
    soup: BeautifulSoup,
    referer: str,
) -> str | None:
    form = soup.find("form", id="boardFrm")
    if not form:
        return None
    data = {
        input_tag.get("name"): input_tag.get("value") or ""
        for input_tag in form.find_all("input")
        if input_tag.get("name")
    }
    if not data.get("bbsId"):
        return None

    headers = dict(DEFAULT_HEADERS)
    headers["Referer"] = referer
    headers["X-Requested-With"] = "XMLHttpRequest"
    ajax_url = urljoin(board_url, "/dggb/module/board/selectBoardListAjax.do")
    try:
        response = await with_retries(
            lambda: _checked_post(client, ajax_url, data=data, headers=headers),
            retries=2,
            base_delay=0.75,
        )
    except Exception:  # noqa: BLE001 - fallback to normal page parse.
        return None
    return response.text


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
        response = await with_retries(
            lambda: _checked_get(client, current_url, headers=headers),
            retries=2,
            base_delay=0.75,
        )
        if _looks_like_file_detail_success(response):
            break
        if _contains_access_denied(response.text):
            break
        redirect = extract_js_redirect_url(str(response.url), response.text)
        if not redirect or redirect in seen_urls:
            break
        seen_urls.add(redirect)
        current_url = redirect
    if response is None:
        raise RuntimeError(f"fetch failed: {url}")
    return response


async def _checked_get(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response


async def _checked_post(
    client: httpx.AsyncClient,
    url: str,
    *,
    data: dict[str, str],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response = await client.post(url, data=data, headers=headers)
    response.raise_for_status()
    return response


def _contains_access_denied(html: str) -> bool:
    text = html.lower()
    return (
        "authreaderror" in text
        or "게시판 접근 권한" in html
        or "권한이 없습니다" in html
        or "로그인이 필요" in html
        or _looks_like_login_only_page(html)
        or "비공개 설정된 글" in html
    )


def _board_params(board_url: str, soup: BeautifulSoup) -> dict[str, list[str]]:
    params = parse_qs(urlparse(board_url).query)
    for input_tag in soup.find_all("input"):
        name = input_tag.get("name")
        value = input_tag.get("value")
        if name and value and not params.get(name):
            params[name] = [value]
    return params


def _row_elements(soup: BeautifulSoup) -> list[Any]:
    rows: list[Any] = []
    rows.extend(soup.select("table tbody tr"))
    rows.extend(row for row in soup.select("table tr") if row not in rows)
    rows.extend(soup.select("ul li"))
    rows.extend(soup.select("ol li"))
    rows.extend(soup.select(".board div, .bbs div, .notice div, .list div, .card div, .gallery div"))
    return rows


def _score_row(row: Any) -> int:
    text = _clean_text(row.get_text(" ", strip=True))
    if not text:
        return -10
    score = 0
    if row.find("a"):
        score += 20
    if DATE_RE.search(text):
        score += 20
    if any(term in text for term in ("작성자", "등록일", "조회", "첨부")):
        score += 15
    if any(attr for tag in row.find_all(True) for attr in tag.attrs if attr.startswith("data-")):
        score += 10
    if any((tag.get("onclick") or "") for tag in row.find_all(True)):
        score += 10
    if NUMBER_RE.search(text[:20]):
        score += 5
    if row.find_parent(["nav", "header", "footer"]):
        score -= 30
    if any(term in text for term in NEGATIVE_ROW_TERMS):
        score -= 10
    return score


def _summarize_row_candidates(soup: BeautifulSoup, limit: int = 50) -> list[dict[str, Any]]:
    scored = sorted(
        ((_score_row(row), index, row) for index, row in enumerate(_row_elements(soup))),
        key=lambda item: item[0],
        reverse=True,
    )
    summaries: list[dict[str, Any]] = []
    for score, index, row in scored[:limit]:
        if score <= 0:
            continue
        hrefs = []
        onclicks = []
        data_attrs: dict[str, str] = {}
        for tag in row.find_all(True):
            if tag.name == "a" and tag.get("href"):
                hrefs.append(tag.get("href"))
            if tag.get("onclick"):
                onclicks.append(tag.get("onclick"))
            for key, value in tag.attrs.items():
                if key.startswith("data-"):
                    data_attrs[key] = str(value)
        summaries.append(
            {
                "row_id": f"R{index}",
                "score": score,
                "text": _clean_text(row.get_text(" ", strip=True))[:500],
                "hrefs": hrefs[:6],
                "data_attrs": data_attrs,
                "onclicks": onclicks[:4],
                "nearby_headers": _nearby_headers(row),
            }
        )
    return summaries


def _summarize_forms(soup: BeautifulSoup) -> list[dict[str, Any]]:
    forms = []
    for form in soup.find_all("form")[:8]:
        hidden = {}
        for input_tag in form.find_all("input"):
            if input_tag.get("type") == "hidden" and input_tag.get("name"):
                hidden[input_tag.get("name")] = input_tag.get("value")
        forms.append(
            {
                "id": form.get("id"),
                "name": form.get("name"),
                "action": form.get("action"),
                "method": form.get("method"),
                "hidden": hidden,
            }
        )
    return forms


def _extract_detail_script_snippets(html: str) -> list[str]:
    snippets: list[str] = []
    for pattern in ("selectNttInfo", "goView", "fnBoardPage", "boardCnts", "mode=view"):
        for match in re.finditer(re.escape(pattern), html):
            start = max(0, match.start() - 500)
            end = min(len(html), match.end() + 800)
            snippet = _clean_text(html[start:end])
            if snippet and snippet not in snippets:
                snippets.append(snippet[:1200])
            if len(snippets) >= 8:
                return snippets
    return snippets


def _nearby_headers(row: Any) -> list[str]:
    table = row.find_parent("table")
    if not table:
        return []
    headers = [_clean_text(item.get_text(" ", strip=True)) for item in table.find_all("th")]
    return [item for item in headers if item][:12]


def _parse_js_args(value: str) -> list[str]:
    match = re.search(r"\((.*)\)", value, re.DOTALL)
    if not match:
        return []
    raw = match.group(1)
    args = []
    current = ""
    quote = ""
    for char in raw:
        if quote:
            if char == quote:
                args.append(current)
                current = ""
                quote = ""
            else:
                current += char
            continue
        if char in {"'", '"'}:
            quote = char
            current = ""
        elif char == ",":
            token = current.strip()
            if token and token not in {"null", "undefined"}:
                args.append(token)
            current = ""
        else:
            current += char
    token = current.strip()
    if token and token not in {"null", "undefined"}:
        args.append(token)
    return args


def _data_id(tag: Any) -> str | None:
    for key in ("data-id", "data-ntt-sn", "data-seq", "data-board-seq", "data-ntt-id"):
        value = tag.get(key)
        if value:
            return str(value)
    return None


def _replace_path_suffix(url: str, old: str, new: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.replace(old, new) if old in parsed.path else parsed.path.rstrip("/") + f"/{new}"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _board_key_from_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}?{parsed.query}"


def _row_text(tag: Any) -> str:
    parent = tag.find_parent(["tr", "li", "div"]) or tag
    return _clean_text(parent.get_text(" ", strip=True))[:300]


def _first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0]


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\xa0", " ")).lower()


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", parsed.query, ""))


def _same_origin(left: str, right: str) -> bool:
    left_parsed = urlparse(left)
    right_parsed = urlparse(right)
    return left_parsed.scheme == right_parsed.scheme and left_parsed.netloc == right_parsed.netloc


def _dedupe_raw_candidates(candidates: list[_RawPostCandidate]) -> list[_RawPostCandidate]:
    by_key: dict[str, _RawPostCandidate] = {}
    for item in candidates:
        key = f"{item.board_key}:{item.post_id}" if item.post_id else "|".join(item.url_candidates)
        if key not in by_key:
            by_key[key] = item
    return list(by_key.values())


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

