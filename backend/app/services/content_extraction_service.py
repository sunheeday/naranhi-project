from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.services.notice_card_service import replace_notice_cards
from app.utils.korean_date_parser import parse_korean_deadline, to_iso_or_none
from extractor.http_security import sanitize_error


EXTRACTED_CONTENT_SCHEMA_VERSION = "1"
SUMMARY_CARD_SCHEMA_VERSION = "1"
SUCCESS_STATUSES = {"success", "partial_success"}
IMMEDIATE_GIVEUP_CODES = {"budget_exhausted", "permanent_not_found", "unsupported_file"}
LOGGER = logging.getLogger(__name__)
_HAYSTACK_ERROR_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("empty_or_unreadable", ("empty_or_unreadable",)),
    ("budget_exhausted", ("budget_exhausted",)),
    ("gemini_quota_exhausted", ("quota", "429", "resource_exhausted", "rate limit", "rate_limit")),
    ("permanent_not_found", ("404", "not found", "not_found")),
    ("unsupported_file", ("unsupported_or_spoofed_file", "unsupported_file_type", "unsupported_file", "file_type_check")),
    ("transient_network", ("timeout", "timed out", "connecterror", "readerror", "network", "content_fetch_failed", "download_failed")),
)


@dataclass(frozen=True)
class ContentExtractionItem:
    notice_id: str
    status: str
    extraction_error_code: str | None
    gemini_calls_used: int
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContentExtractionSummary:
    started_at: str
    finished_at: str
    dry_run: bool
    force: bool
    max_notices: int
    processed_count: int
    success_count: int
    error_count: int
    gemini_calls_used: int
    gemini_call_cap_reached: bool
    targets: list[dict[str, Any]]
    results: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def exit_code(self) -> int:
        return 0


class ContentExtractionService:
    async def run(
        self,
        *,
        notice_id: str | None = None,
        max_notices: int | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> ContentExtractionSummary:
        if force and not notice_id:
            raise ValueError("--force requires --notice-id for content extraction.")

        settings = get_settings()
        _ensure_supabase_configured(settings)
        started_at = _utc_now()
        max_count = max_notices or settings.extractor_max_notices_per_run

        if dry_run:
            targets = _dry_run_targets(notice_id=notice_id, limit=max_count)
            return _build_summary(
                started_at=started_at,
                dry_run=True,
                force=force,
                max_notices=max_count,
                targets=targets,
                results=[],
                gemini_call_cap_reached=False,
            )

        from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor

        results: list[ContentExtractionItem] = []
        total_gemini_calls = 0
        gemini_call_cap_reached = False
        async with GeminiDocumentExtractor() as gemini_client:
            for _ in range(max_count):
                if _cap_reached(total_gemini_calls, settings.extractor_max_gemini_calls_per_run):
                    gemini_call_cap_reached = True
                    break

                notice = _claim_notice(
                    notice_id=notice_id,
                    force=force,
                    stale_minutes=settings.extractor_stale_minutes,
                )
                if notice is None:
                    break

                item = await self._process_notice(
                    notice,
                    gemini_client=gemini_client,
                    notice_timeout_seconds=settings.extractor_notice_timeout_seconds,
                )
                total_gemini_calls += item.gemini_calls_used
                results.append(item)
                LOGGER.info(
                    "content extractor result: notice_id=%s status=%s error_code=%s gemini_calls=%s",
                    item.notice_id,
                    item.status,
                    item.extraction_error_code,
                    item.gemini_calls_used,
                )
                if notice_id:
                    break

        return _build_summary(
            started_at=started_at,
            dry_run=False,
            force=force,
            max_notices=max_count,
            targets=[],
            results=results,
            gemini_call_cap_reached=gemini_call_cap_reached,
        )

    async def run_for_school(
        self,
        school_id: str,
        *,
        max_notices: int,
    ) -> ContentExtractionSummary:
        settings = get_settings()
        _ensure_supabase_configured(settings)
        started_at = _utc_now()
        notice_ids = _pending_notice_ids_for_school(school_id, limit=max_notices)

        from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor

        results: list[ContentExtractionItem] = []
        total_gemini_calls = 0
        gemini_call_cap_reached = False
        async with GeminiDocumentExtractor() as gemini_client:
            for notice_id in notice_ids:
                if _cap_reached(total_gemini_calls, settings.extractor_max_gemini_calls_per_run):
                    gemini_call_cap_reached = True
                    break

                notice = _claim_notice(
                    notice_id=notice_id,
                    force=True,
                    stale_minutes=settings.extractor_stale_minutes,
                )
                if notice is None:
                    continue

                item = await self._process_notice(
                    notice,
                    gemini_client=gemini_client,
                    notice_timeout_seconds=settings.extractor_notice_timeout_seconds,
                )
                total_gemini_calls += item.gemini_calls_used
                results.append(item)
                LOGGER.info(
                    "school content extractor result: school_id=%s notice_id=%s status=%s error_code=%s gemini_calls=%s",
                    school_id,
                    item.notice_id,
                    item.status,
                    item.extraction_error_code,
                    item.gemini_calls_used,
                )

        return _build_summary(
            started_at=started_at,
            dry_run=False,
            force=True,
            max_notices=max_notices,
            targets=[],
            results=results,
            gemini_call_cap_reached=gemini_call_cap_reached,
        )

    async def _process_notice(
        self,
        notice: dict[str, Any],
        *,
        gemini_client: Any,
        notice_timeout_seconds: float,
    ) -> ContentExtractionItem:
        notice_id = str(notice.get("id") or "")
        detail_url = str(notice.get("detail_url") or "")
        if not notice_id or not detail_url:
            return _save_failure(
                notice,
                error_code="permanent_not_found",
                error_message="Missing notice id or detail_url.",
                gemini_calls_used=0,
            )

        from extractor.extract_pipeline import extract_case
        from extractor.models import CaseConfig

        try:
            result = await asyncio.wait_for(
                extract_case(
                    CaseConfig(id=notice_id, detail_url=detail_url, fetch_context=_fetch_context_from_notice(notice)),
                    gemini_client=gemini_client,
                ),
                timeout=notice_timeout_seconds,
            )
        except TimeoutError as exc:
            return _save_failure(
                notice,
                error_code="transient_network",
                error_message=f"Extraction timed out after {notice_timeout_seconds:g}s.",
                gemini_calls_used=0,
                exception=exc,
            )
        except Exception as exc:  # noqa: BLE001 - normalize one notice failure.
            return _save_failure(
                notice,
                error_code="internal_error",
                error_message=f"{type(exc).__name__}: {sanitize_error(exc)}",
                gemini_calls_used=0,
                exception=exc,
            )

        gemini_calls_used = _gemini_calls_used(result)
        if _is_successful_extraction(result):
            summary_card, summary_calls_used = await _generate_summary_card(
                notice,
                result,
                gemini_client=gemini_client,
            )
            gemini_calls_used += summary_calls_used
            _save_success(notice, result, summary_card=summary_card)
            return ContentExtractionItem(
                notice_id=notice_id,
                status="done",
                extraction_error_code=None,
                gemini_calls_used=gemini_calls_used,
            )

        error_code = classify_extraction_error(result)
        return _save_failure(
            notice,
            error_code=error_code,
            error_message=_result_error_message(result),
            gemini_calls_used=gemini_calls_used,
        )


def classify_extraction_error(result: Any) -> str:
    if getattr(result, "content_kind", "") == "empty_or_unreadable":
        return "empty_or_unreadable"
    if _metadata_bool(getattr(result, "metadata", {}), "budget_exhausted"):
        return "budget_exhausted"

    haystack = _result_haystack(result)
    for code, terms in _HAYSTACK_ERROR_RULES:
        if any(term in haystack for term in terms):
            return code
    return "internal_error"


def _ensure_supabase_configured(settings: Any) -> None:
    missing = _missing_supabase_config_names(settings)
    if missing:
        raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")


def _missing_supabase_config_names(settings: Any) -> list[str]:
    missing: list[str] = []
    if not getattr(settings, "supabase_url", None):
        missing.append("SUPABASE_URL")
    if not getattr(settings, "supabase_service_role_key", None):
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    return missing


def build_extracted_content(result: Any, *, summary_card: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": EXTRACTED_CONTENT_SCHEMA_VERSION,
        "final_url": getattr(result, "final_url", ""),
        "content_kind": getattr(result, "content_kind", ""),
        "canonical_summary": getattr(result, "canonical_summary", {}) or {},
        "canonical_source_ids": getattr(result, "canonical_source_ids", []) or [],
        "sources": [_source_summary(source) for source in getattr(result, "sources", []) or []],
        "metadata": getattr(result, "metadata", {}) or {},
        "errors": getattr(result, "errors", []) or [],
    }
    if summary_card:
        payload["summary_card"] = summary_card
    return _jsonable(payload)


def _save_success(notice: dict[str, Any], result: Any, *, summary_card: dict[str, Any] | None = None) -> None:
    notice_id = str(notice["id"])
    canonical_summary = getattr(result, "canonical_summary", {}) if isinstance(getattr(result, "canonical_summary", {}), dict) else {}
    summary_oneliner = _optional_str(canonical_summary.get("summary_oneliner"))
    deadline = _optional_str(canonical_summary.get("deadline"))
    deadline_at = to_iso_or_none(parse_korean_deadline(deadline, reference=notice.get("created_at")))
    extracted_content = build_extracted_content(result, summary_card=summary_card)

    payload = {
        "status": "done",
        "original_text": getattr(result, "raw_text", ""),
        "summary_oneliner": summary_oneliner,
        "summary_translations": _merge_ko_summary(notice.get("summary_translations"), summary_oneliner),
        "document_type": _optional_str(canonical_summary.get("document_type")),
        "urgency": _optional_str(canonical_summary.get("urgency")),
        "deadline_at": deadline_at,
        "extracted_content": extracted_content,
        "extraction_finished_at": _utc_now().isoformat(),
        "extraction_next_run_at": None,
        "extraction_error_code": None,
        "error_message": None,
    }
    get_supabase_client().table("notices").update(payload).eq("id", notice_id).execute()
    try:
        replace_notice_cards(
            notice_id,
            extracted_content,
            title=_optional_str(notice.get("title")),
            original_text=getattr(result, "raw_text", ""),
        )
    except Exception as exc:  # noqa: BLE001 - cards are a rebuildable cache.
        LOGGER.error(
            "notice card generation failed: notice_id=%s exception=%s",
            notice_id,
            sanitize_error(exc),
        )


async def _generate_summary_card(
    notice: dict[str, Any],
    result: Any,
    *,
    gemini_client: Any,
) -> tuple[dict[str, Any] | None, int]:
    settings = get_settings()
    if not settings.extractor_enable_gemini_summary:
        return None, 0
    if not getattr(gemini_client, "api_keys", []):
        LOGGER.info("Gemini summary skipped because GEMINI_API_KEY(S) is not configured.")
        return None, 0

    raw_text = str(getattr(result, "raw_text", "") or "")
    prompt_text = _summary_prompt_text(raw_text, max_chars=settings.extractor_summary_input_chars)
    if len(prompt_text) < 20:
        return None, 0

    title = _optional_str(notice.get("title")) or _optional_str(
        (getattr(result, "canonical_summary", {}) or {}).get("summary_oneliner")
        if isinstance(getattr(result, "canonical_summary", {}), dict)
        else None
    )
    model = settings.extractor_summary_model
    try:
        parsed = await gemini_client.generate_json(
            _summary_card_prompt(
                title=title,
                raw_text=prompt_text,
                content_kind=str(getattr(result, "content_kind", "") or ""),
            ),
            model=model,
        )
    except Exception as exc:  # noqa: BLE001 - deterministic card fallback remains available.
        LOGGER.warning(
            "Gemini summary generation failed: notice_id=%s exception=%s",
            notice.get("id"),
            sanitize_error(exc),
        )
        return None, 1

    items = _summary_card_items_from_gemini(parsed)
    if not items:
        LOGGER.warning("Gemini summary generation returned no usable items: notice_id=%s", notice.get("id"))
        return None, 1

    return (
        {
            "schema_version": SUMMARY_CARD_SCHEMA_VERSION,
            "source": "gemini_summary",
            "model": model,
            "items": items,
            "confidence": _summary_confidence(parsed),
        },
        1,
    )


def _summary_card_prompt(*, title: str | None, raw_text: str, content_kind: str) -> str:
    schema = {
        "items": [{"text": "학부모가 바로 이해해야 하는 핵심 내용"}],
        "confidence": 0.0,
    }
    return f"""
너는 한국 학교 공지를 학부모 앱의 "핵심 요약" 카드로 바꾸는 편집자다.

목표:
- 원문에 있는 실질적인 내용은 가능한 한 많이 보존한다.
- 너무 짧게 요약하지 말고, 학부모가 알아야 할 사실을 4~8개 항목으로 정리한다.
- 원문에 중요한 내용이 8개보다 적으면 적은 개수만 반환한다.
- 학교명, 교장명, 작성자, 등록일, 주소, 우편번호, 전화/FAX, 홈페이지, 게시판 UI, 파일첨부 표, 공익제보센터 안내처럼 사용자가 행동 판단에 필요 없는 잡음은 제외한다.

반드시 포함하려고 노력할 항목:
- 일정, 기간, 시간, 날짜
- 대상 학년/반/학생/학부모
- 장소
- 제출/신청/동의/납부/참여/확인 같은 해야 할 일
- 준비물, 비용, 문의처가 본문 맥락상 중요한 경우
- 변경 사항, 예외 사항, 주의할 점
- 본문 설명 문단의 핵심 내용

규칙:
- 원문에 없는 내용을 만들지 않는다.
- 날짜, 시간, 금액, 전화번호, 장소는 원문 표현을 최대한 유지한다.
- 각 item.text는 한 문장 또는 한 항목으로 쓴다.
- 제목만 반복하지 말고 본문 정보를 넣는다.
- 한국어 JSON만 반환한다.

반환 JSON schema:
{json.dumps(schema, ensure_ascii=False)}

공지 제목:
{title or ""}

content_kind:
{content_kind}

원문:
{raw_text}
""".strip()


def _summary_prompt_text(raw_text: str, *, max_chars: int) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in raw_text.splitlines():
        line = " ".join(str(raw_line).split()).strip()
        if not line or line == "---":
            continue
        if line.startswith("[") and "]" in line:
            continue
        lower = line.lower()
        if any(token in lower for token in ("cleanedu@sen.go.kr", "공익제보센터", "신고내용", "신고방법")):
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if sum(len(item) + 1 for item in lines) >= max_chars:
            break
    return "\n".join(lines)[:max_chars]


def _summary_card_items_from_gemini(parsed: Any) -> list[dict[str, str]]:
    if not isinstance(parsed, dict):
        return []
    raw_items = parsed.get("items")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        text = ""
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        elif isinstance(item, str):
            text = item.strip()
        text = " ".join(text.split())
        if not text or text in seen:
            continue
        seen.add(text)
        items.append({"text": text})
        if len(items) >= 8:
            break
    return items


def _summary_confidence(parsed: Any) -> float | None:
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("confidence")
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return None


def _save_failure(
    notice: dict[str, Any],
    *,
    error_code: str,
    error_message: str,
    gemini_calls_used: int,
    exception: Exception | None = None,
) -> ContentExtractionItem:
    notice_id = str(notice.get("id") or "")
    payload = _failure_payload(notice, error_code=error_code, error_message=error_message)
    get_supabase_client().table("notices").update(payload).eq("id", notice_id).execute()
    if exception:
        LOGGER.warning(
            "content extraction failed: notice_id=%s error_code=%s exception=%s",
            notice_id,
            error_code,
            sanitize_error(exception),
        )
    return ContentExtractionItem(
        notice_id=notice_id,
        status="error",
        extraction_error_code=error_code,
        gemini_calls_used=gemini_calls_used,
        error_message=payload["error_message"],
    )


def _failure_payload(notice: dict[str, Any], *, error_code: str, error_message: str) -> dict[str, Any]:
    now = _utc_now()
    attempts = _int_value(notice.get("extraction_attempts"))
    next_run_at: str | None = None
    next_attempts = attempts

    if error_code == "transient_network":
        next_run_at = (now + timedelta(minutes=30)).isoformat()
    elif error_code == "empty_or_unreadable":
        next_run_at = (now + timedelta(hours=6)).isoformat()
    elif error_code == "gemini_quota_exhausted":
        next_run_at = (now + timedelta(hours=24)).isoformat()
    elif error_code == "internal_error":
        if attempts < 3:
            next_run_at = (now + timedelta(hours=6)).isoformat()
        else:
            next_attempts = max(attempts, 3)
    elif error_code in IMMEDIATE_GIVEUP_CODES:
        next_attempts = max(attempts, 3)

    return {
        "status": "error",
        "extraction_attempts": next_attempts,
        "extraction_finished_at": now.isoformat(),
        "extraction_next_run_at": next_run_at,
        "extraction_error_code": error_code,
        "error_message": _truncate_error(error_message),
    }


def _claim_notice(*, notice_id: str | None, force: bool, stale_minutes: int) -> dict[str, Any] | None:
    result = (
        get_supabase_client()
        .rpc(
            "claim_notice_extractions",
            {
                "p_limit": 1,
                "p_stale_minutes": stale_minutes,
                "p_notice_id": notice_id,
                "p_force": force,
            },
        )
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _dry_run_targets(*, notice_id: str | None, limit: int) -> list[dict[str, Any]]:
    query = (
        get_supabase_client()
        .table("notices")
        .select("id,status,detail_url,created_at,extraction_error_code,extraction_next_run_at")
        .eq("source", "crawl")
        .in_("status", ["pending", "error", "processing"])
        .limit(limit)
    )
    if notice_id:
        query = query.eq("id", notice_id)
    rows = query.execute().data or []
    return [
        {
            "id": row.get("id"),
            "status": row.get("status"),
            "has_detail_url": bool(row.get("detail_url")),
            "created_at": row.get("created_at"),
            "extraction_error_code": row.get("extraction_error_code"),
            "extraction_next_run_at": row.get("extraction_next_run_at"),
        }
        for row in rows
        if row.get("detail_url")
    ]


def _pending_notice_ids_for_school(school_id: str, *, limit: int) -> list[str]:
    rows = (
        get_supabase_client()
        .table("notices")
        .select("id,detail_url")
        .eq("school_id", school_id)
        .eq("source", "crawl")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return [str(row["id"]) for row in rows if row.get("id") and row.get("detail_url")]


def _is_successful_extraction(result: Any) -> bool:
    return (
        getattr(result, "status", "") in SUCCESS_STATUSES
        and bool(str(getattr(result, "raw_text", "")).strip())
        and getattr(result, "content_kind", "") != "empty_or_unreadable"
    )


def _fetch_context_from_notice(notice: dict[str, Any]) -> dict[str, Any]:
    crawl_result = notice.get("crawl_result")
    context: dict[str, Any] = {}
    if isinstance(crawl_result, dict):
        context.update(crawl_result)
        context["crawl_result"] = crawl_result
    source_post_id = notice.get("source_post_id")
    if source_post_id:
        context["source_post_id"] = str(source_post_id)
    detail_url = notice.get("detail_url")
    if detail_url:
        context["detail_url"] = str(detail_url)
    return context


def _build_summary(
    *,
    started_at: datetime,
    dry_run: bool,
    force: bool,
    max_notices: int,
    targets: list[dict[str, Any]],
    results: list[ContentExtractionItem],
    gemini_call_cap_reached: bool,
) -> ContentExtractionSummary:
    success_count = sum(1 for item in results if item.status == "done")
    error_count = sum(1 for item in results if item.status == "error")
    return ContentExtractionSummary(
        started_at=started_at.isoformat(),
        finished_at=_utc_now().isoformat(),
        dry_run=dry_run,
        force=force,
        max_notices=max_notices,
        processed_count=len(results),
        success_count=success_count,
        error_count=error_count,
        gemini_calls_used=sum(item.gemini_calls_used for item in results),
        gemini_call_cap_reached=gemini_call_cap_reached,
        targets=targets,
        results=[item.to_dict() for item in results],
    )


def _source_summary(source: Any) -> dict[str, Any]:
    raw_text = getattr(source, "raw_text", "") or ""
    return {
        "source_id": getattr(source, "source_id", ""),
        "source_type": getattr(source, "source_type", ""),
        "source_role": getattr(source, "source_role", ""),
        "origin_url": getattr(source, "origin_url", ""),
        "filename": getattr(source, "filename", ""),
        "file_hash": getattr(source, "file_hash", ""),
        "text_fingerprint": getattr(source, "text_fingerprint", ""),
        "extraction_method": getattr(source, "extraction_method", ""),
        "status": getattr(source, "status", ""),
        "confidence": getattr(source, "confidence", 0.0),
        "quality_score": getattr(source, "quality_score", 0.0),
        "metadata": getattr(source, "metadata", {}) or {},
        "errors": getattr(source, "errors", []) or [],
        "raw_text_chars": len(raw_text),
    }


def _result_haystack(result: Any) -> str:
    parts: list[str] = [
        str(getattr(result, "status", "")),
        str(getattr(result, "content_kind", "")),
        " ".join(str(item) for item in getattr(result, "errors", []) or []),
    ]
    for source in getattr(result, "sources", []) or []:
        parts.extend(
            [
                str(getattr(source, "status", "")),
                str(getattr(source, "extraction_method", "")),
                " ".join(str(item) for item in getattr(source, "errors", []) or []),
            ]
        )
    return " ".join(parts).lower()


def _result_error_message(result: Any) -> str:
    errors = getattr(result, "errors", []) or []
    if errors:
        return _truncate_error("; ".join(str(error) for error in errors[:4]))
    return _truncate_error(f"Extraction returned status={getattr(result, 'status', 'unknown')}")


def _gemini_calls_used(result: Any) -> int:
    metadata = getattr(result, "metadata", {}) or {}
    return _int_value(metadata.get("gemini_calls_used"))


def _metadata_bool(metadata: Any, key: str) -> bool:
    return isinstance(metadata, dict) and bool(metadata.get(key))


def _merge_ko_summary(value: Any, summary_oneliner: str | None) -> dict[str, str]:
    result = {str(key): str(item) for key, item in value.items()} if isinstance(value, dict) else {}
    if summary_oneliner:
        result["ko"] = summary_oneliner
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _truncate_error(value: str) -> str:
    return sanitize_error(value).replace("\n", " ")[:800]


def _cap_reached(used: int, cap: int) -> bool:
    return cap > 0 and used >= cap


def _utc_now() -> datetime:
    return datetime.now(UTC)
