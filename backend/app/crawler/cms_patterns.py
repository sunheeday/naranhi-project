from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.crawler.link_extractor import LinkCandidate


DETAIL_QUERY_KEYS = {"nttSn", "nttId", "articleId", "boardSeq", "seq", "number", "num"}


@dataclass(frozen=True)
class CmsDetection:
    key: str
    name: str
    confidence: float
    signals: list[str]


CMS_NAMES = {
    "jbedu": "전북 school.jbedu.kr CMS",
    "jje": "제주 school.jje.go.kr CMS",
    "busanedu": "부산 school.busanedu.net CMS",
    "dge": "대구 dge.ms.kr CMS",
    "gen_xboard": "광주 gen.ms.kr 구형 xboard CMS",
    "use": "울산 school.use.go.kr CMS",
    "cbe": "충북 school.cbe.go.kr CMS",
    "cnems_boardcnts": "충남 boardCnts CMS",
    "sen": "서울 sen 학교 CMS",
    "select_ntt": "교육청 통합 selectNtt CMS",
    "boardcnts": "boardCnts 게시판 CMS",
    "schoolbell": "학교종이 외부 서비스",
    "unknown": "알 수 없는 CMS",
}


def detect_cms(final_url: str, html: str, candidates: list[LinkCandidate]) -> CmsDetection:
    parsed = urlparse(final_url)
    host = parsed.netloc.lower()
    candidate_urls = " ".join(item.url for item in candidates[:80])
    haystack = f"{final_url} {html[:120000]} {candidate_urls}"

    scores: Counter[str] = Counter()
    signals: dict[str, list[str]] = {}

    def add(key: str, score: int, signal: str) -> None:
        scores[key] += score
        signals.setdefault(key, []).append(signal)

    if "school.jbedu.kr" in host:
        add("jbedu", 100, "도메인 school.jbedu.kr")
    if "school.jje.go.kr" in host:
        add("jje", 100, "도메인 school.jje.go.kr")
    if "school.busanedu.net" in host:
        add("busanedu", 100, "도메인 school.busanedu.net")
    if "dge.ms.kr" in host:
        add("dge", 100, "도메인 dge.ms.kr")
    if "gen.ms.kr" in host or ":452" in parsed.netloc:
        add("gen_xboard", 100, "도메인 gen.ms.kr 또는 452 포트")
    if "school.use.go.kr" in host:
        add("use", 100, "도메인 school.use.go.kr")
    if "school.cbe.go.kr" in host:
        add("cbe", 100, "도메인 school.cbe.go.kr")
    if "cnems.kr" in host:
        add("cnems_boardcnts", 100, "도메인 cnems.kr")
    if "sen." in host or host.endswith("sen.ms.kr"):
        add("sen", 90, "도메인 sen 학교 CMS")

    if "/xhomenews/board.php" in haystack or "/xboard/board.php" in haystack:
        add("gen_xboard", 80, "xhomenews/xboard 게시판 패턴")
    if "boardCnts/list.do" in haystack or "boardCnts/view.do" in haystack:
        add("boardcnts", 70, "boardCnts 게시판 패턴")
        if "cnems.kr" in host:
            add("cnems_boardcnts", 40, "cnems + boardCnts 조합")
    if "selectNttList.do" in haystack or "selectNttInfo.do" in haystack:
        add("select_ntt", 65, "selectNtt 게시판 패턴")
    if "/M01" in haystack and ("passni5" in haystack or "school.jbedu.kr" in host):
        add("jbedu", 50, "전북 M코드/passni5 패턴")
    if "/M01" in haystack and "school.use.go.kr" in host:
        add("use", 50, "울산 M코드 패턴")
    if "/M01" in haystack and "school.cbe.go.kr" in host:
        add("cbe", 50, "충북 M코드 패턴")
    if "schoolbell-e.com" in haystack:
        add("schoolbell", 35, "학교종이 외부 링크 포함")

    if not scores:
        return CmsDetection(
            key="unknown",
            name=CMS_NAMES["unknown"],
            confidence=0,
            signals=[],
        )

    key, score = scores.most_common(1)[0]
    confidence = min(score / 120, 0.99)
    return CmsDetection(
        key=key,
        name=CMS_NAMES.get(key, key),
        confidence=confidence,
        signals=signals.get(key, [])[:4],
    )


def board_url_variants(url: str, cms: CmsDetection) -> list[str]:
    variants: list[str] = []

    for candidate in (
        _normalize_jbedu_path(url),
        _normalize_select_ntt(url),
        _normalize_boardcnts(url),
        _normalize_xboard(url),
        _normalize_gen_cms(url),
        url,
    ):
        if candidate and candidate not in variants:
            variants.append(candidate)

    return variants


def _normalize_jbedu_path(url: str) -> str | None:
    parsed = urlparse(url)
    if "/view/" not in parsed.path:
        return None

    board_path = parsed.path.split("/view/", 1)[0].rstrip("/") + "/"
    return urlunparse((parsed.scheme, parsed.netloc, board_path, "", "", ""))


def _normalize_select_ntt(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.path.endswith("selectNttInfo.do"):
        return None

    query = _drop_detail_query_keys(parsed.query)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.replace("selectNttInfo.do", "selectNttList.do"),
            parsed.params,
            query,
            "",
        )
    )


def _normalize_boardcnts(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.path.endswith("boardCnts/view.do"):
        return None

    query = _drop_detail_query_keys(parsed.query)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.replace("boardCnts/view.do", "boardCnts/list.do"),
            parsed.params,
            query,
            "",
        )
    )


def _normalize_xboard(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.path.endswith("board.php"):
        return None

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in DETAIL_QUERY_KEYS and key.lower() not in {"mode", "queryencode"}
    ]
    if len(query_pairs) == len(parse_qsl(parsed.query, keep_blank_values=True)):
        return None

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query_pairs),
            "",
        )
    )


def _normalize_gen_cms(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.path.endswith("cms.php"):
        return None

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "dk_id"
    ]
    if len(query_pairs) == len(parse_qsl(parsed.query, keep_blank_values=True)):
        return None

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query_pairs),
            "",
        )
    )


def _drop_detail_query_keys(query: str) -> str:
    return urlencode(
        [
            (key, value)
            for key, value in parse_qsl(query, keep_blank_values=True)
            if key not in DETAIL_QUERY_KEYS
        ]
    )

