from __future__ import annotations

from dataclasses import dataclass, replace
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.crawler.cms_patterns import CmsDetection, board_url_variants, detect_cms
from app.crawler.gemini_finder import GeminiDecision, GeminiFinder, heuristic_decision
from app.crawler.homepage_client import FetchedPage, HomepageClient
from app.crawler.link_extractor import (
    LinkCandidate,
    candidate_priority,
    extract_links,
    find_announcement_menu_link,
    find_exact_notice_menu_link,
    is_primary_notice_text,
    page_snippet,
    page_title,
    score_candidate,
)
from app.crawler.verifier import VerificationResult, verify_notice_url


SECONDARY_MENU_THRESHOLD = 15
HEURISTIC_GEMINI_SKIP_CONFIDENCE = 0.8


@dataclass(frozen=True)
class NoticeBoardSearchResult:
    homepage_url: str
    homepage_final_url: str
    homepage_title: str
    cms: CmsDetection
    candidates: list[LinkCandidate]
    decision: GeminiDecision
    verification: VerificationResult | None
    board_kind: str
    fallback_used: bool


async def find_notice_board_url(
    *,
    school_name: str,
    homepage_url: str,
    gemini_api_key: str | None,
) -> NoticeBoardSearchResult:
    client = HomepageClient()
    homepage = await client.fetch(homepage_url)
    homepage = await _resolve_school_landing_page(client, homepage)
    title = page_title(homepage.html)
    snippet = page_snippet(homepage.html)
    candidates = extract_links(homepage.final_url, homepage.html)
    direct_notice_link = find_exact_notice_menu_link(homepage.final_url, homepage.html)
    announcement_fallback_link = find_announcement_menu_link(homepage.final_url, homepage.html)

    expanded = [] if direct_notice_link else await _expand_from_menu_candidates(client, candidates)
    seeded_candidates = []
    if direct_notice_link:
        seeded_candidates.append(direct_notice_link)
    if announcement_fallback_link:
        seeded_candidates.append(announcement_fallback_link)
    merged_candidates = _merge_candidates(seeded_candidates + candidates + expanded)
    cms = detect_cms(homepage.final_url, homepage.html, merged_candidates)

    if direct_notice_link:
        decision = GeminiDecision(
            best_url=direct_notice_link.url,
            confidence=0.98,
            reason=(
                "홈페이지 메뉴 영역에서 가정통신문 계열 링크를 직접 찾았습니다. "
                "Gemini 판단 없이 규칙 기반으로 확정했습니다."
            ),
            alternatives=[
                {
                    "url": item.url,
                    "reason": f"{item.text} / {item.context}",
                }
                for item in merged_candidates
                if item.url != direct_notice_link.url
            ][:3],
            needs_human_check=False,
        )
    elif gemini_api_key:
        heuristic = heuristic_decision(merged_candidates)
        if heuristic.best_url and heuristic.confidence >= HEURISTIC_GEMINI_SKIP_CONFIDENCE:
            decision = replace(
                heuristic,
                reason=(
                    "규칙 기반 1위 후보의 confidence가 충분히 높아 "
                    "Gemini 판단 없이 선택했습니다."
                ),
                needs_human_check=False,
            )
        else:
            try:
                decision = await GeminiFinder(gemini_api_key).choose_notice_board(
                    school_name=school_name,
                    homepage_url=homepage.final_url,
                    page_title=title,
                    page_snippet=snippet,
                    candidates=merged_candidates,
                )
            except Exception as exc:  # noqa: BLE001 - POC should degrade, not fail batch.
                decision = GeminiDecision(
                    best_url=heuristic.best_url,
                    confidence=max(0.1, heuristic.confidence - 0.15),
                    reason=f"Gemini 판단 실패로 규칙 기반 후보를 사용했습니다. Gemini error: {exc}",
                    alternatives=heuristic.alternatives,
                    needs_human_check=True,
                )
    else:
        decision = heuristic_decision(merged_candidates)

    if not decision.best_url and announcement_fallback_link:
        decision = GeminiDecision(
            best_url=announcement_fallback_link.url,
            confidence=0.72,
            reason=(
                "학교 자체 가정통신문 메뉴를 찾지 못했습니다. "
                "사용자 정책에 따라 공지사항 게시판을 대체 위치로 사용합니다."
            ),
            alternatives=decision.alternatives,
            needs_human_check=True,
        )

    verification = None
    if decision.best_url:
        decision, verification = await _verify_with_board_url_normalization(
            decision,
            warmup_url=homepage.final_url,
            cms=cms,
        )
        if (
            verification
            and not verification.ok
            and announcement_fallback_link
            and announcement_fallback_link.url != decision.best_url
        ):
            fallback_decision = GeminiDecision(
                best_url=announcement_fallback_link.url,
                confidence=min(decision.confidence, 0.72),
                reason=(
                    f"{decision.reason} 선택한 가정통신문 후보 검증에 실패하여 "
                    "사용자 정책에 따라 공지사항 게시판을 대체 위치로 사용합니다."
                ),
                alternatives=decision.alternatives,
                needs_human_check=True,
            )
            fallback_decision, fallback_verification = await _verify_with_board_url_normalization(
                fallback_decision,
                warmup_url=homepage.final_url,
                cms=cms,
            )
            if fallback_verification.ok:
                decision, verification = fallback_decision, fallback_verification

    return NoticeBoardSearchResult(
        homepage_url=homepage_url,
        homepage_final_url=homepage.final_url,
        homepage_title=title,
        cms=cms,
        candidates=merged_candidates,
        decision=decision,
        verification=verification,
        board_kind=_board_kind_for_decision(
            decision=decision,
            verification=verification,
            direct_notice_link=direct_notice_link,
            announcement_fallback_link=announcement_fallback_link,
            candidates=merged_candidates,
        ),
        fallback_used=_fallback_used_for_decision(
            decision=decision,
            verification=verification,
            announcement_fallback_link=announcement_fallback_link,
        ),
    )


async def _expand_from_menu_candidates(
    client: HomepageClient,
    candidates: list[LinkCandidate],
    max_pages: int = 8,
) -> list[LinkCandidate]:
    expanded: list[LinkCandidate] = []
    likely_menu_pages = [
        item for item in candidates
        if item.score >= SECONDARY_MENU_THRESHOLD and "가정통신문" not in f"{item.text} {item.context}"
    ][:max_pages]

    for menu_candidate in likely_menu_pages:
        try:
            page = await client.fetch(menu_candidate.url)
        except Exception:
            continue
        nested = extract_links(page.final_url, page.html, limit=80)
        expanded.extend(
            LinkCandidate(
                text=item.text,
                url=item.url,
                context=f"{menu_candidate.text} > {item.context}",
                score=item.score + score_candidate(menu_candidate.text, menu_candidate.url, menu_candidate.context),
            )
            for item in nested
        )

    return expanded


def _merge_candidates(candidates: list[LinkCandidate], limit: int = 80) -> list[LinkCandidate]:
    by_url: dict[str, LinkCandidate] = {}
    for item in candidates:
        current = by_url.get(item.url)
        if current is None or candidate_priority(item) < candidate_priority(current):
            by_url[item.url] = item
    return sorted(by_url.values(), key=lambda item: (candidate_priority(item), -item.score))[:limit]


def _board_kind_for_decision(
    *,
    decision: GeminiDecision,
    verification: VerificationResult | None,
    direct_notice_link: LinkCandidate | None,
    announcement_fallback_link: LinkCandidate | None,
    candidates: list[LinkCandidate],
) -> str:
    if not decision.best_url or not verification or not verification.ok:
        return "unknown"

    if direct_notice_link and _same_url_for_kind(decision.best_url, direct_notice_link.url):
        return "family_notice"

    if announcement_fallback_link and _same_url_for_kind(decision.best_url, announcement_fallback_link.url):
        return "announcement_fallback"

    selected = _candidate_for_url(decision.best_url, candidates)
    if selected and is_primary_notice_text(f"{selected.text} {selected.context} {selected.url}"):
        return "family_notice"

    if is_primary_notice_text(decision.best_url):
        return "family_notice"

    return "unknown"


def _fallback_used_for_decision(
    *,
    decision: GeminiDecision,
    verification: VerificationResult | None,
    announcement_fallback_link: LinkCandidate | None,
) -> bool:
    return bool(
        decision.best_url
        and verification
        and verification.ok
        and announcement_fallback_link
        and _same_url_for_kind(decision.best_url, announcement_fallback_link.url)
    )


def _candidate_for_url(url: str, candidates: list[LinkCandidate]) -> LinkCandidate | None:
    return next((item for item in candidates if _same_url_for_kind(url, item.url)), None)


def _same_url_for_kind(left: str, right: str) -> bool:
    return _normalize_url_for_kind(left) == _normalize_url_for_kind(right)


def _normalize_url_for_kind(url: str) -> str:
    parsed = urlparse(url)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", query, ""))


async def _resolve_school_landing_page(client: HomepageClient, page: FetchedPage) -> FetchedPage:
    snippet = page_snippet(page.html, max_chars=300)
    candidates = extract_links(page.final_url, page.html, limit=10)

    if len(candidates) > 5 and "바로가기" not in snippet:
        return page

    for candidate in candidates:
        text = f"{candidate.text} {candidate.url}"
        if not ("바로가기" in text or "home=y" in candidate.url or "intro.do" in candidate.url):
            continue

        try:
            next_page = await client.fetch(candidate.url)
        except Exception:
            continue

        next_candidates = extract_links(next_page.final_url, next_page.html, limit=10)
        if len(next_candidates) > len(candidates) or find_exact_notice_menu_link(next_page.final_url, next_page.html):
            return next_page

    return page


async def _verify_with_board_url_normalization(
    decision: GeminiDecision,
    *,
    warmup_url: str,
    cms: CmsDetection,
) -> tuple[GeminiDecision, VerificationResult]:
    assert decision.best_url is not None

    urls = board_url_variants(decision.best_url, cms)

    first_verification: VerificationResult | None = None
    for url in urls:
        verification = await verify_notice_url(url, warmup_url=warmup_url)
        if first_verification is None:
            first_verification = verification
        if verification.ok:
            if url != decision.best_url:
                return (
                    replace(
                        decision,
                        best_url=url,
                        reason=(
                            f"{decision.reason} 상세글 URL 대신 검증 가능한 게시판 URL로 정규화했습니다."
                        ),
                    ),
                    verification,
                )
            return decision, verification

    return decision, first_verification or await verify_notice_url(decision.best_url, warmup_url=warmup_url)

