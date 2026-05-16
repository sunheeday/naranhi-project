from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.crawler.board_detector import NoticeBoardSearchResult, find_notice_board_url
from app.crawler.neis_client import NeisClient, normalize_homepage_url
from app.crawler.notice_post_extractor import NoticePostRefResult, extract_notice_post_refs

POST_SUCCESS_STATUSES = {"success", "success_with_derived_id", "success_file_only"}


@dataclass(frozen=True)
class DiscoveredPostPreview:
    title: str
    post_id: str
    post_uid: str
    board_key: str
    detail_url: str
    status: str
    method: str
    source: str
    cms_key: str
    parser_family: str
    reason: str


@dataclass(frozen=True)
class SchoolBoardDiscoveryResult:
    school_id: str
    school_name: str
    office_code: str | None
    school_code: str | None
    homepage_url: str | None
    status: str
    board_url: str | None
    board_kind: str
    fallback_used: bool
    cms_key: str | None
    cms_name: str | None
    cms_confidence: float | None
    cms_signals: list[str]
    verified: bool
    verification_score: int | None
    verification_title: str | None
    verification_error: str | None
    parser_family: str | None
    total_candidates: int
    success_count: int
    sample_posts: list[DiscoveredPostPreview]
    error_code: str | None
    error_message: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _SchoolContext:
    school_id: str
    school_name: str
    office_code: str | None
    school_code: str | None
    homepage_url: str | None


class SchoolCrawlerService:
    async def discover_and_save_school_board(
        self,
        school_id: str,
    ) -> SchoolBoardDiscoveryResult:
        settings = get_settings()
        result = await self.discover_school_board(
            school_id,
            use_gemini=settings.crawler_enable_gemini,
            max_posts=settings.crawler_initial_notice_count,
        )
        if result.status == "school_not_found":
            return result
        _save_school_discovery_result(result)
        _save_discovered_notice_candidates(result)
        return result

    async def discover_school_board(
        self,
        school_id: str,
        *,
        use_gemini: bool = True,
        max_posts: int | None = None,
    ) -> SchoolBoardDiscoveryResult:
        settings = get_settings()
        try:
            return await asyncio.wait_for(
                self._discover_school_board_inner(
                    school_id,
                    use_gemini=use_gemini,
                    max_posts=max_posts,
                ),
                timeout=settings.crawler_school_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return _failure_result(
                _SchoolContext(
                    school_id=school_id,
                    school_name="",
                    office_code=None,
                    school_code=None,
                    homepage_url=None,
                ),
                status="fetch_timeout",
                error_message=(
                    f"School crawler exceeded "
                    f"{settings.crawler_school_timeout_seconds:.0f}s timeout."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - service returns status payloads.
            return _failure_result(
                _SchoolContext(
                    school_id=school_id,
                    school_name="",
                    office_code=None,
                    school_code=None,
                    homepage_url=None,
                ),
                status="internal_error",
                error_message=f"{type(exc).__name__}: {exc}",
            )

    async def _discover_school_board_inner(
        self,
        school_id: str,
        *,
        use_gemini: bool,
        max_posts: int | None,
    ) -> SchoolBoardDiscoveryResult:
        settings = get_settings()
        if not settings.supabase_configured:
            return _failure_result(
                _SchoolContext(
                    school_id=school_id,
                    school_name="",
                    office_code=None,
                    school_code=None,
                    homepage_url=None,
                ),
                status="internal_error",
                error_message="Supabase is not configured.",
            )

        school_row = _fetch_school_row(school_id)
        if not school_row:
            return _failure_result(
                _SchoolContext(
                    school_id=school_id,
                    school_name="",
                    office_code=None,
                    school_code=None,
                    homepage_url=None,
                ),
                status="school_not_found",
                error_message="School row was not found.",
            )

        context = _context_from_school_row(school_id, school_row)
        context = await _with_neis_homepage(context)
        if not context.homepage_url:
            return _failure_result(
                context,
                status="homepage_missing",
                error_message="School homepage URL is missing from DB and NEIS.",
            )

        gemini_api_key = (
            settings.gemini_api_key
            if use_gemini and settings.crawler_enable_gemini
            else None
        )
        post_limit = max_posts if max_posts is not None else settings.crawler_max_posts

        try:
            board_result = await find_notice_board_url(
                school_name=context.school_name,
                homepage_url=context.homepage_url,
                gemini_api_key=gemini_api_key,
            )
        except Exception as exc:  # noqa: BLE001 - classify homepage/board failures.
            status = _classify_fetch_exception(exc)
            return _failure_result(
                context,
                status=status,
                error_message=f"{type(exc).__name__}: {exc}",
            )

        if (
            not board_result.decision.best_url
            or not board_result.verification
            or not board_result.verification.ok
        ):
            status = _classify_board_failure(board_result)
            return _failure_result(
                context,
                status=status,
                error_message=_board_failure_message(board_result),
                board_result=board_result,
            )

        detail_result = await extract_notice_post_refs(
            board_url=board_result.decision.best_url,
            cms=board_result.cms,
            warmup_url=board_result.homepage_final_url,
            gemini_api_key=gemini_api_key,
            max_posts=post_limit,
        )
        return _result_from_detail_result(
            context=context,
            board_result=board_result,
            detail_result=detail_result,
            max_posts=post_limit,
        )


def get_school_crawler_service() -> SchoolCrawlerService:
    return SchoolCrawlerService()


def _fetch_school_row(school_id: str) -> dict[str, Any] | None:
    supabase = get_supabase_client()
    result = (
        supabase.table("schools")
        .select("*")
        .eq("id", school_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return dict(result.data[0])


def _context_from_school_row(school_id: str, row: dict[str, Any]) -> _SchoolContext:
    return _SchoolContext(
        school_id=school_id,
        school_name=str(row.get("name") or ""),
        office_code=_optional_str(row.get("neis_office_code")),
        school_code=_optional_str(row.get("neis_school_code")),
        homepage_url=normalize_homepage_url(_optional_str(row.get("homepage_url"))),
    )


async def _with_neis_homepage(context: _SchoolContext) -> _SchoolContext:
    if context.homepage_url or not context.office_code or not context.school_code:
        return context

    settings = get_settings()
    if not settings.neis_api_key:
        return context

    school = await NeisClient(
        settings.neis_api_key,
        timeout=settings.crawler_timeout_seconds,
    ).get_school_by_codes(context.office_code, context.school_code)
    if not school:
        return context

    return _SchoolContext(
        school_id=context.school_id,
        school_name=context.school_name or school.name,
        office_code=context.office_code or school.office_code,
        school_code=context.school_code or school.school_code,
        homepage_url=school.homepage_url or context.homepage_url,
    )


def _result_from_detail_result(
    *,
    context: _SchoolContext,
    board_result: NoticeBoardSearchResult,
    detail_result: NoticePostRefResult,
    max_posts: int,
) -> SchoolBoardDiscoveryResult:
    status = "success" if detail_result.success_count > 0 else _normalize_detail_status(detail_result.status)
    return SchoolBoardDiscoveryResult(
        school_id=context.school_id,
        school_name=context.school_name,
        office_code=context.office_code,
        school_code=context.school_code,
        homepage_url=context.homepage_url,
        status=status,
        board_url=board_result.decision.best_url,
        board_kind=board_result.board_kind,
        fallback_used=board_result.fallback_used,
        cms_key=board_result.cms.key,
        cms_name=board_result.cms.name,
        cms_confidence=board_result.cms.confidence,
        cms_signals=board_result.cms.signals,
        verified=bool(board_result.verification and board_result.verification.ok),
        verification_score=(
            board_result.verification.score if board_result.verification else None
        ),
        verification_title=(
            board_result.verification.title if board_result.verification else None
        ),
        verification_error=(
            board_result.verification.error if board_result.verification else None
        ),
        parser_family=detail_result.parser_family,
        total_candidates=detail_result.total_candidates,
        success_count=detail_result.success_count,
        sample_posts=[
            DiscoveredPostPreview(
                title=post.title,
                post_id=post.post_id,
                post_uid=post.post_uid,
                board_key=post.board_key,
                detail_url=post.detail_url,
                status=post.status,
                method=post.detail_method,
                source=post.post_id_source,
                cms_key=post.cms_key,
                parser_family=post.parser_family,
                reason=post.reason,
            )
            for post in detail_result.posts[:max_posts]
        ],
        error_code=None if status == "success" else status,
        error_message=None if status == "success" else detail_result.error,
    )


def _failure_result(
    context: _SchoolContext,
    *,
    status: str,
    error_message: str | None,
    board_result: NoticeBoardSearchResult | None = None,
) -> SchoolBoardDiscoveryResult:
    cms = board_result.cms if board_result else None
    verification = board_result.verification if board_result else None
    return SchoolBoardDiscoveryResult(
        school_id=context.school_id,
        school_name=context.school_name,
        office_code=context.office_code,
        school_code=context.school_code,
        homepage_url=context.homepage_url,
        status=status,
        board_url=board_result.decision.best_url if board_result else None,
        board_kind=board_result.board_kind if board_result else "unknown",
        fallback_used=board_result.fallback_used if board_result else False,
        cms_key=cms.key if cms else None,
        cms_name=cms.name if cms else None,
        cms_confidence=cms.confidence if cms else None,
        cms_signals=cms.signals if cms else [],
        verified=bool(verification and verification.ok),
        verification_score=verification.score if verification else None,
        verification_title=verification.title if verification else None,
        verification_error=verification.error if verification else None,
        parser_family=None,
        total_candidates=0,
        success_count=0,
        sample_posts=[],
        error_code=status,
        error_message=error_message,
    )


def _save_school_discovery_result(result: SchoolBoardDiscoveryResult) -> None:
    payload: dict[str, Any] = {
        "crawl_status": result.status,
        "crawl_error_message": result.error_message,
        "crawl_result": result.to_dict(),
        "crawl_last_checked_at": _utc_now_iso(),
    }
    if result.homepage_url:
        payload["homepage_url"] = result.homepage_url
    if result.verified and result.board_url:
        payload["crawl_board_url"] = result.board_url
        payload["crawl_board_kind"] = (
            result.board_kind
            if result.board_kind in {"family_notice", "announcement_fallback", "unknown"}
            else "unknown"
        )

    try:
        get_supabase_client().table("schools").update(payload).eq(
            "id",
            result.school_id,
        ).execute()
    except Exception as exc:  # noqa: BLE001 - normalize DB errors for API layer.
        raise RuntimeError(f"Failed to save school crawler result: {exc}") from exc


def _save_discovered_notice_candidates(result: SchoolBoardDiscoveryResult) -> int:
    saved = 0
    for post in result.sample_posts:
        if post.status not in POST_SUCCESS_STATUSES or not post.detail_url:
            continue

        payload = {
            "child_id": None,
            "school_id": result.school_id,
            "source": "crawl",
            "title": post.title or None,
            "status": "pending",
            "detail_url": post.detail_url,
            "source_post_id": post.post_id or None,
            "source_post_uid": post.post_uid or None,
            "crawl_result": {
                "status": post.status,
                "board_url": result.board_url,
                "board_kind": result.board_kind,
                "cms_key": post.cms_key or result.cms_key,
                "parser_family": post.parser_family or result.parser_family,
                "post": asdict(post),
            },
        }
        try:
            get_supabase_client().table("notices").insert(payload).execute()
            saved += 1
        except Exception as exc:  # noqa: BLE001 - Supabase client error shape varies.
            if _is_unique_violation(exc):
                continue
            raise RuntimeError(f"Failed to save crawled notice candidate: {exc}") from exc
    return saved


def _is_unique_violation(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    text = str(exc).lower()
    return (
        code == "23505"
        or "23505" in text
        or "duplicate key value violates unique constraint" in text
    )


def _classify_fetch_exception(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "fetch_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            return "unsupported_forbidden"
        if status_code in {429, 500, 502, 503, 504}:
            return "fetch_unavailable"
        return "homepage_fetch_failed"
    if isinstance(exc, httpx.TransportError):
        return "homepage_fetch_failed"
    return "homepage_fetch_failed"


def _classify_board_failure(board_result: NoticeBoardSearchResult) -> str:
    haystack = " ".join(
        item
        for item in (
            board_result.decision.best_url,
            board_result.verification.title if board_result.verification else None,
            board_result.verification.snippet if board_result.verification else None,
            board_result.verification.error if board_result.verification else None,
        )
        if item
    ).lower()
    if "schoolbell-e.com" in haystack:
        return "unsupported_external_dynamic"
    if "403" in haystack or "forbidden" in haystack or "권한" in haystack:
        return "unsupported_forbidden"
    if "login" in haystack or "로그인" in haystack:
        return "unsupported_login_required"
    return "notice_board_not_found"


def _board_failure_message(board_result: NoticeBoardSearchResult) -> str:
    if board_result.verification and board_result.verification.error:
        return board_result.verification.error
    if board_result.decision.best_url:
        return "Board URL candidate did not pass HTTP verification."
    return "No notice or announcement board candidate was found."


def _normalize_detail_status(status: str) -> str:
    if status in {
        "unsupported_login_required",
        "unsupported_forbidden",
        "unsupported_external_dynamic",
    }:
        return status
    return "detail_entry_failed"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
