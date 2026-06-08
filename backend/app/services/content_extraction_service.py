from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
import re
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from extractor.http_security import sanitize_error
from postgrest.exceptions import APIError


EXTRACTED_CONTENT_SCHEMA_VERSION = "1"
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
_SOURCE_TRANSLATION_LOCKS: dict[str, asyncio.Lock] = {}


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
            remaining = max_count
            while remaining > 0:
                if _cap_reached(total_gemini_calls, settings.extractor_max_gemini_calls_per_run):
                    gemini_call_cap_reached = True
                    break

                batch_size = 1 if notice_id else min(settings.extractor_notice_concurrency, remaining)
                if settings.extractor_max_gemini_calls_per_run > 0:
                    batch_size = 1
                claimed_notices: list[dict[str, Any]] = []
                for _ in range(batch_size):
                    notice = _claim_notice(
                        notice_id=notice_id,
                        force=force,
                        stale_minutes=settings.extractor_stale_minutes,
                    )
                    if notice is None:
                        break
                    claimed_notices.append(notice)
                    if notice_id:
                        break

                if not claimed_notices:
                    break

                processed = await self._process_notice_batch(
                    claimed_notices,
                    gemini_client=gemini_client,
                    notice_timeout_seconds=settings.extractor_notice_timeout_seconds,
                    concurrency=settings.extractor_notice_concurrency,
                )
                remaining -= len(claimed_notices)
                for item in processed:
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
            queue = list(notice_ids)
            while queue:
                if _cap_reached(total_gemini_calls, settings.extractor_max_gemini_calls_per_run):
                    gemini_call_cap_reached = True
                    break

                batch_size = min(settings.extractor_notice_concurrency, len(queue))
                if settings.extractor_max_gemini_calls_per_run > 0:
                    batch_size = 1
                batch_ids = [queue.pop(0) for _ in range(batch_size)]

                claimed_notices: list[dict[str, Any]] = []
                for queued_notice_id in batch_ids:
                    notice = _claim_notice(
                        notice_id=queued_notice_id,
                        force=True,
                        stale_minutes=settings.extractor_stale_minutes,
                    )
                    if notice is None:
                        continue
                    claimed_notices.append(notice)

                if not claimed_notices:
                    continue

                processed = await self._process_notice_batch(
                    claimed_notices,
                    gemini_client=gemini_client,
                    notice_timeout_seconds=settings.extractor_notice_timeout_seconds,
                    concurrency=settings.extractor_notice_concurrency,
                )
                for item in processed:
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

    async def _process_notice_batch(
        self,
        notices: list[dict[str, Any]],
        *,
        gemini_client: Any,
        notice_timeout_seconds: float,
        concurrency: int,
    ) -> list[ContentExtractionItem]:
        if not notices:
            return []

        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def run_one(index: int, notice: dict[str, Any]) -> tuple[int, ContentExtractionItem]:
            async with semaphore:
                item = await self._process_notice(
                    notice,
                    gemini_client=gemini_client,
                    notice_timeout_seconds=notice_timeout_seconds,
                )
                return index, item

        completed = await asyncio.gather(
            *(run_one(index, notice) for index, notice in enumerate(notices))
        )
        completed.sort(key=lambda pair: pair[0])
        return [item for _, item in completed]

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

        # 추출 중 다운로드된 첨부 파일을 Supabase Storage 에 올린다(같은 바이트, 한 번만 다운로드).
        uploads: dict[str, dict[str, Any]] = {}
        inline_images: list[tuple[str, bytes]] = []  # 본문 사진들 — 1장(세로 PNG)으로 합쳐 저장

        async def _on_attachment(source_id: str, downloaded: Any) -> None:
            from app.services.attachment_storage import upload_attachment

            # 본문 사진(inline image)은 개별 저장하지 않고 바이트만 모은다(나중에 1장으로 합침).
            if source_id.startswith("inline_image"):
                try:
                    inline_images.append((source_id, Path(downloaded.path).read_bytes()))
                except Exception:  # noqa: BLE001
                    pass
                return

            info = await upload_attachment(
                notice_id=notice_id,
                source_id=source_id,
                path_on_disk=downloaded.path,
                filename=downloaded.filename,
                content_type=downloaded.content_type,
            )
            if info:
                uploads[source_id] = info

        try:
            result = await asyncio.wait_for(
                extract_case(
                    CaseConfig(id=notice_id, detail_url=detail_url, fetch_context=_fetch_context_from_notice(notice)),
                    gemini_client=gemini_client,
                    on_attachment=_on_attachment,
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
            refinements, refine_calls = await _refine_sources(
                result, gemini_client=gemini_client, notice_id=notice_id
            )
            gemini_calls_used += refine_calls

            # 요약 생성: 정제된 본문+첨부를 한 번 더 압축해 '이 공지가 무엇인지' 요약을 만들고
            # original_text 에 저장한다(기존 번역 파이프라인이 그대로 요약을 번역). best-effort.
            from app.services.summary_service import summarize

            body_text, summary_attachments = _summary_inputs(result, refinements)
            summary, summary_calls = await summarize(
                title=str(notice.get("title") or ""),
                body=body_text,
                attachments=summary_attachments,
                gemini=gemini_client,
            )
            gemini_calls_used += summary_calls

            # 본문 사진들을 세로로 이은 PNG 1장으로 합쳐 Storage 에 저장(첨부란에서 미리보기/다운로드).
            body_image = await _combine_and_upload_body_images(notice_id, inline_images)
            try:
                _save_success(notice, result, refinements, uploads, summary, body_image)
            except Exception as exc:  # noqa: BLE001 - one bad save must not abort the whole batch.
                return _save_failure(
                    notice,
                    error_code="internal_error",
                    error_message=f"save_success failed: {type(exc).__name__}: {sanitize_error(exc)}",
                    gemini_calls_used=gemini_calls_used,
                    exception=exc,
                )
            await _auto_translate_notice_locales(notice)
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


def build_extracted_content(
    result: Any,
    refinements: dict[str, dict[str, Any]] | None = None,
    uploads: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    refinements = refinements or {}
    uploads = uploads or {}
    payload = {
        "schema_version": EXTRACTED_CONTENT_SCHEMA_VERSION,
        "final_url": getattr(result, "final_url", ""),
        "content_kind": getattr(result, "content_kind", ""),
        "included_source_ids": getattr(result, "included_source_ids", []) or [],
        "sources": [
            _source_summary(
                source,
                refinements.get(str(getattr(source, "source_id", "")), {}),
                uploads.get(str(getattr(source, "source_id", "")), {}),
            )
            for source in getattr(result, "sources", []) or []
        ],
        "metadata": getattr(result, "metadata", {}) or {},
        "errors": getattr(result, "errors", []) or [],
    }
    return _jsonable(payload)


# 본문을 이루는 소스(게시판 본문 + 본문 속 사진). 다운로드 가능한 '첨부 파일'과 구분한다.
_BODY_SOURCE_TYPES = {"html_body", "inline_image"}

# 본문 '텍스트'에 인라인 사진 OCR 을 합칠 최소 품질. 이보다 낮으면(깨진 지도/스크린샷 OCR 등)
# 깨끗한 문서 첨부가 따로 있을 때 본문 텍스트에서 제외한다(사진 자체는 '본문 사진'으로 보여줌).
INLINE_OCR_BODY_MIN_QUALITY = 60.0
# 텍스트를 신뢰할 수 있는 문서 첨부(본문 사진 OCR 이 깨져도 같은 내용을 깨끗하게 싣는다).
_DOC_ATTACHMENT_TYPES = {"attachment_pdf", "attachment_hwp", "attachment_hwpx", "attachment_xlsx"}


def _has_clean_doc_attachment(result: Any) -> bool:
    """included 에 텍스트가 충분한 문서 첨부(PDF/HWP/HWPX/XLSX)가 있는지.

    있으면 본문 속 사진(inline_image)의 OCR 이 깨져도 그 첨부가 같은 내용을 깨끗하게 싣고 있으므로,
    품질 낮은 사진 OCR 을 본문 텍스트에서 빼도 정보가 사라지지 않는다(사진은 '본문 사진'으로 보여줌).
    """
    by_id = {str(getattr(s, "source_id", "")): s for s in getattr(result, "sources", []) or []}
    for sid in list(getattr(result, "included_source_ids", []) or []):
        source = by_id.get(str(sid))
        if source is None:
            continue
        if (
            getattr(source, "source_type", "") in _DOC_ATTACHMENT_TYPES
            and len(str(getattr(source, "raw_text", "") or "").strip()) >= 200
        ):
            return True
    return False


def _order_index(source: Any) -> int:
    meta = getattr(source, "metadata", {}) or {}
    value = meta.get("order_index")
    return value if isinstance(value, int) else 0


def _body_sources(result: Any) -> list[Any]:
    """본문 소스(게시판 본문 + 본문 속 사진)를 문서 순서대로. (사용자 모델: 본문=텍스트+사진)"""
    by_id = {str(getattr(s, "source_id", "")): s for s in getattr(result, "sources", []) or []}
    included = list(getattr(result, "included_source_ids", []) or [])
    sources = [
        by_id[sid]
        for sid in included
        if sid in by_id and getattr(by_id[sid], "source_type", "") in _BODY_SOURCE_TYPES
    ]
    return sorted(sources, key=_order_index)


def _primary_source_id(result: Any) -> str:
    """본문 carrier = original_text(기존 호환·번역 대상) 및 본문 카드의 대표 소스.

    html_body 가 있으면 그것, 없으면(사진만 있는 본문) 첫 본문 소스. 본문 소스가 전혀 없으면
    첫 included(첨부만 있는 비정상 케이스).
    """
    body = _body_sources(result)
    for source in body:
        if getattr(source, "source_type", "") == "html_body":
            return str(getattr(source, "source_id", ""))
    if body:
        return str(getattr(body[0], "source_id", ""))
    included = list(getattr(result, "included_source_ids", []) or [])
    return str(included[0]) if included else ""


# 첨부가 이보다 많은 페이지(또는 그에 준하는 분량)면 정제하지 않고 원본 파일로 안내(needs_file).
MAX_ATTACHMENT_PAGES = 20
_TOO_LONG_CHARS = 20000  # 페이지수 없는 형식(HWP/HWPX 등) 폴백: 20페이지 ≈ 2만자


def _source_page_count(source: Any) -> int | None:
    meta = getattr(source, "metadata", {}) or {}
    pages = meta.get("page_count")
    return pages if isinstance(pages, int) and pages > 0 else None


def _attachment_too_long(source: Any) -> bool:
    """첨부가 너무 길어(20페이지 초과) 정제 대신 원본 파일로 안내해야 하는지.

    PDF 는 정확한 페이지수로, 페이지수가 없는 형식(HWP/HWPX 등)은 글자수 대략값으로 판단한다.
    """
    pages = _source_page_count(source)
    if pages is not None and pages > MAX_ATTACHMENT_PAGES:
        return True
    return len(str(getattr(source, "raw_text", "") or "")) > _TOO_LONG_CHARS


def _refinement_entry(refined: str, gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "refined_text": refined,
        "needs_file": bool(gate.get("needs_file")),
        "needs_file_reason": gate.get("reasons", []),
        "quality_signals": gate.get("signals", {}),
    }


async def _refine_sources(
    result: Any, *, gemini_client: Any, notice_id: str
) -> tuple[dict[str, dict[str, Any]], int]:
    """본문(게시판 본문+사진을 합쳐 하나)과 첨부 파일(각각)을 정제·게이트 판정한다.

    사용자 모델 = '본문(텍스트+사진)' + '첨부 파일'. 그래서 html_body 와 본문 속 inline_image 는
    하나의 본문으로 합쳐 정제하고(사진 OCR이 본문에 자연히 포함), 다운로드 첨부만 따로 카드로 낸다.
    한 묶음의 정제가 실패해도 원문을 그대로 써서 공지를 잃지 않는다.
    반환: ({carrier_source_id: 정제결과}, 총 gemini 호출수).
    """
    from app.services.quality_gate import assess
    from app.services.refinement_service import refine

    async def _refine_one(raw_text: str) -> tuple[str, dict[str, Any], int]:
        try:
            refined, tag, calls = await refine(raw_text, gemini=gemini_client)
            return _scrub_text(refined), assess(refined, tag), calls
        except Exception as exc:  # noqa: BLE001 - 정제 실패가 공지를 잃게 하지 않는다(원문 폴백).
            LOGGER.warning(
                "refine failed, using raw: notice_id=%s exception=%s", notice_id, sanitize_error(exc)
            )
            return _scrub_text(raw_text), assess(raw_text, "refine_error"), 0

    by_id = {str(getattr(s, "source_id", "")): s for s in getattr(result, "sources", []) or []}
    included = list(getattr(result, "included_source_ids", []) or [])
    refinements: dict[str, dict[str, Any]] = {}
    total_calls = 0

    # 본문: 게시판 본문 + 본문 속 사진(OCR)을 순서대로 합쳐 '하나의 본문'으로 정제.
    body = _body_sources(result)
    body_ids = {str(getattr(s, "source_id", "")) for s in body}
    carrier_id = _primary_source_id(result)
    # 깨끗한 문서 첨부(PDF/HWP 등)가 있으면, 품질 낮은 인라인 사진 OCR(깨진 지도/스크린샷 등)은
    # 본문 '텍스트'에서 제외해 본문 오염을 막는다. 단 carrier(대표 본문)는 절대 빼지 않는다
    # (본문이 통째로 비는 사고 방지). 빠진 사진도 따로 '본문 사진'으로 합쳐 보여주므로 원본 확인 가능.
    has_clean_doc = _has_clean_doc_attachment(result)
    body_chunks: list[str] = []
    for source in body:
        raw = str(getattr(source, "raw_text", "") or "").strip()
        if not raw:
            continue
        sid = str(getattr(source, "source_id", ""))
        if (
            has_clean_doc
            and sid != carrier_id
            and getattr(source, "source_type", "") == "inline_image"
            and float(getattr(source, "quality_score", 0) or 0) < INLINE_OCR_BODY_MIN_QUALITY
        ):
            LOGGER.info(
                "drop low-quality inline OCR from body: notice_id=%s source_id=%s score=%s",
                notice_id, sid, getattr(source, "quality_score", 0),
            )
            continue
        body_chunks.append(raw)
    body_raw = "\n\n".join(body_chunks)
    if body_raw.strip() and carrier_id:
        refined, gate, calls = await _refine_one(body_raw)
        total_calls += calls
        refinements[carrier_id] = _refinement_entry(refined, gate)
        LOGGER.info(
            "body refine: notice_id=%s body_sources=%s needs_file=%s chars=%s->%s",
            notice_id, len(body), refinements[carrier_id]["needs_file"], len(body_raw), len(refined),
        )

    # 첨부 파일: 다운로드 소스는 각각 따로 정제(자기 카드).
    for source_id in included:
        if source_id in body_ids:
            continue
        source = by_id.get(source_id)
        if source is None:
            continue
        raw_text = str(getattr(source, "raw_text", "") or "")
        if not raw_text.strip():
            continue
        if _attachment_too_long(source):  # 20페이지 초과 → 정제 안 함, 원본 파일로 안내
            pages = _source_page_count(source)
            refinements[source_id] = {
                "refined_text": "",
                "needs_file": True,
                "needs_file_reason": [f"분량 많음({pages}쪽) — 원본 파일 확인" if pages else "분량 많음 — 원본 파일 확인"],
                "quality_signals": {"tag": "too_long", "page_count": pages},
            }
            LOGGER.info(
                "attachment too long, skip refine: notice_id=%s source_id=%s pages=%s chars=%s",
                notice_id, source_id, pages, len(raw_text),
            )
            continue
        refined, gate, calls = await _refine_one(raw_text)
        total_calls += calls
        refinements[source_id] = _refinement_entry(refined, gate)
        LOGGER.info(
            "attachment refine: notice_id=%s source_id=%s needs_file=%s chars=%s->%s",
            notice_id, source_id, refinements[source_id]["needs_file"], len(raw_text), len(refined),
        )

    return refinements, total_calls


def _summary_inputs(
    result: Any, refinements: dict[str, dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """요약 입력 구성: 본문 정제본(body) + 첨부별 {source_id, name, text, needs_file}.

    본문 carrier 의 refined_text 를 body 로, 나머지 included 첨부 소스를 문서 순서로 모은다.
    """
    carrier_id = _primary_source_id(result)
    body_text = str((refinements.get(carrier_id) or {}).get("refined_text") or "")
    body_ids = {str(getattr(s, "source_id", "")) for s in _body_sources(result)}
    by_id = {str(getattr(s, "source_id", "")): s for s in getattr(result, "sources", []) or []}

    attachments: list[dict[str, Any]] = []
    for source_id in list(getattr(result, "included_source_ids", []) or []):
        if source_id == carrier_id or source_id in body_ids:
            continue
        ref = refinements.get(source_id)
        if ref is None:
            continue
        source = by_id.get(source_id)
        attachments.append(
            {
                "source_id": source_id,
                "name": str(getattr(source, "filename", "") or "") if source else "",
                "text": str(ref.get("refined_text") or ""),
                "needs_file": bool(ref.get("needs_file")),
            }
        )
    return body_text, attachments


def _full_body_text(result: Any, refinements: dict[str, dict[str, Any]]) -> str:
    """본문 정제본 + 첨부 정제본들을 합쳐 '풀 본문'을 만든다.

    팀 번역·구조화 파이프라인(translate_notice → notice_cards/school_events)의 입력이 되며,
    요약이 아니라 전체 내용에서 카드·일정이 추출되도록 한다. 첨부는 '## 첨부: 파일명'
    헤더로 구분해 이어붙인다.
    """
    body, attachments = _summary_inputs(result, refinements)
    parts: list[str] = []
    if body.strip():
        parts.append(body.strip())
    for att in attachments:
        text = str(att.get("text") or "").strip()
        if not text:
            continue
        name = str(att.get("name") or "").strip() or "첨부"
        parts.append(f"## 첨부: {name}\n\n{text}")
    return "\n\n".join(parts).strip()


def _stitch_images_vertically(images: list[bytes]) -> bytes | None:
    """여러 이미지 바이트를 같은 폭으로 맞춰 세로로 이어 붙인 PNG 1장(바이트)로 반환."""
    import io

    from PIL import Image

    pil: list[Any] = []
    for data in images:
        try:
            pil.append(Image.open(io.BytesIO(data)).convert("RGB"))
        except Exception:  # noqa: BLE001 - 깨진 이미지는 건너뜀
            continue
    if not pil:
        return None
    width = min(max(im.width for im in pil), 1600)  # 폭 통일 + 과대 방지
    resized = []
    for im in pil:
        if im.width != width:
            new_h = max(1, round(im.height * width / im.width))
            im = im.resize((width, new_h))
        resized.append(im)
    total_h = sum(im.height for im in resized)
    combined = Image.new("RGB", (width, total_h), "white")
    y = 0
    for im in resized:
        combined.paste(im, (0, y))
        y += im.height
    out = io.BytesIO()
    combined.save(out, format="PNG")
    return out.getvalue()


# 본문 사진을 1장으로 합칠 때의 최대 장수(과대 PNG·메모리 폭주 방지).
_MAX_BODY_IMAGES = 12


async def _combine_and_upload_body_images(notice_id: str, inline_images: list[tuple[str, bytes]]) -> str:
    """본문 사진들(여러 장)을 세로 PNG 1장으로 합쳐 Storage 에 올리고 public_url 반환(없으면 '')."""
    if not inline_images:
        return ""

    def _order(item: tuple[str, bytes]) -> int:
        match = re.search(r"(\d+)\s*$", item[0])
        return int(match.group(1)) if match else 0

    ordered_items = sorted(inline_images, key=_order)
    if len(ordered_items) > _MAX_BODY_IMAGES:  # 상한 적용: 너무 많은 사진은 과대 PNG 방지를 위해 자른다
        LOGGER.info(
            "body images capped: notice_id=%s total=%s cap=%s",
            notice_id, len(ordered_items), _MAX_BODY_IMAGES,
        )
        ordered_items = ordered_items[:_MAX_BODY_IMAGES]
    ordered = [data for _, data in ordered_items]
    combined = await asyncio.to_thread(_stitch_images_vertically, ordered)
    if not combined:
        return ""
    from app.services.attachment_storage import upload_bytes

    info = await upload_bytes(
        notice_id=notice_id, name="body-images", data=combined, content_type="image/png", ext=".png"
    )
    return info["public_url"] if info else ""


def _save_success(
    notice: dict[str, Any],
    result: Any,
    refinements: dict[str, dict[str, Any]],
    uploads: dict[str, dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
    body_image_url: str = "",
) -> None:
    from app.services.summary_service import render_summary_markdown

    notice_id = str(notice["id"])
    extracted_content = build_extracted_content(result, refinements, uploads)

    # 본문 사진들을 합친 1장(PNG)을 합성 소스로 추가 → 프론트 '원본 파일' 카드에서 미리보기/다운로드.
    if body_image_url:
        extracted_content.setdefault("sources", []).append({
            "source_id": "body_images_combined",
            "source_type": "attachment_image",
            "source_role": "body_images",
            "filename": "본문 사진.png",
            "public_url": body_image_url,
            "metadata": {"file_type": "image"},
        })

    # 공지 레벨 needs_file(기존 프론트·번역 호환): 대표 소스(본문 우선) 기준.
    primary = refinements.get(_primary_source_id(result), {})
    extracted_content["needs_file"] = bool(primary.get("needs_file"))
    extracted_content["needs_file_reason"] = primary.get("needs_file_reason", [])
    extracted_content["quality_signals"] = primary.get("quality_signals", {})

    # original_text = 정제된 풀 본문(본문+첨부 합본) → 팀 번역·구조화 파이프라인이 여기서
    # 구조화 카드(해야할일/일정/준비물)·일정·해야할일/소식 분류를 풀 내용 기준으로 추출한다.
    # 요약은 별도로 extracted_content.summary 에 보관(렌더 텍스트 포함, 프론트 요약 카드용).
    if summary:
        extracted_content["summary"] = {**summary, "rendered": render_summary_markdown(summary)}
    original_text = (
        _full_body_text(result, refinements)
        or primary.get("refined_text")
        or _scrub_text(str(getattr(result, "raw_text", "") or ""))
    )

    payload = {
        "status": "done",
        "original_text": _scrub_text(original_text),
        "extracted_content": extracted_content,
        "extraction_next_run_at": None,
        "extraction_error_code": None,
        "error_message": None,
    }
    get_supabase_client().table("notices").update(payload).eq("id", notice_id).execute()


async def _auto_translate_notice_locales(notice: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.gemini_configured:
        return

    notice_id = str(notice.get("id") or "").strip()
    school_id = str(notice.get("school_id") or "").strip()
    if not notice_id or not school_id:
        return

    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    notice_text = _clean_text(notice.get("original_text"))
    if not notice_text:
        try:
            fresh_notice = (
                get_supabase_client()
                .table("notices")
                .select("original_text")
                .eq("id", notice_id)
                .single()
                .execute()
                .data
            )
        except AttributeError:
            fresh_notice = None
        if isinstance(fresh_notice, dict):
            notice_text = _clean_text(fresh_notice.get("original_text"))

    from app.services.notice_service import NoticeService

    service = NoticeService()
    try:
        await service.translate_notice(
            notice_id=notice_id,
            target_language="ko",
            source_text=notice_text,
        )
    except Exception as exc:  # noqa: BLE001 - canonical refresh must not fail extraction.
        LOGGER.warning(
            "canonical ko translation refresh failed: notice_id=%s school_id=%s error=%s",
            notice_id,
            school_id,
            sanitize_error(exc),
        )

    locales = _school_translation_locales(school_id)
    if not locales:
        return

    target_locales = _missing_translation_locales(notice_id, locales)
    if not target_locales:
        return

    semaphore = asyncio.Semaphore(max(1, int(getattr(settings, "auto_translation_locale_concurrency", 3) or 3)))

    async def _run_locale(locale: str) -> None:
        async with semaphore:
            try:
                await service.translate_notice(
                    notice_id=notice_id,
                    target_language=locale,
                )
                # 요약·본문·첨부도 같은 번역 함수(translate_text)로 채운다(표시용).
                await translate_sources_for_locale(service, notice_id, locale)
            except Exception as exc:  # noqa: BLE001 - translation backfill must not fail extraction.
                LOGGER.warning(
                    "auto translation failed: notice_id=%s school_id=%s locale=%s error=%s",
                    notice_id,
                    school_id,
                    locale,
                    sanitize_error(exc),
                )

    await asyncio.gather(*(_run_locale(locale) for locale in target_locales))


async def translate_sources_for_locale(service: Any, notice_id: str, target_language: str) -> None:
    """요약·본문·첨부 정제본을 팀 translate_text(기존 번역 함수)로 번역해 extracted_content 에 저장.

    번역 로직은 팀 것을 그대로 재사용한다 — 우리는 요약/소스 텍스트를 넣어 호출하고 결과를
    translations 슬롯에 담을 뿐(새 번역 코드 0). 이미 번역된 언어는 건너뛴다(캐시).
    프론트는 summary.translations / sources[].translations 를 읽어 부모 언어로 표시한다.
    """
    if not target_language or target_language == "ko":
        return

    sb = get_supabase_client()
    row = sb.table("notices").select("extracted_content").eq("id", notice_id).single().execute().data
    extracted = (row or {}).get("extracted_content") or {}
    summary = extracted.get("summary") if isinstance(extracted.get("summary"), dict) else None
    sources = extracted.get("sources") if isinstance(extracted.get("sources"), list) else []

    async def _translate(text: str, *, translation_kind: str) -> str:
        try:
            result = await service.translate_text(
                source_text=text,
                target_language=target_language,
                translation_kind=translation_kind,
            )
        except Exception as exc:  # noqa: BLE001 - 소스 번역 실패가 전체 번역을 깨지 않는다.
            LOGGER.warning(
                "source translate failed: notice_id=%s lang=%s error=%s",
                notice_id, target_language, sanitize_error(exc),
            )
            return ""
        translated = result.get("translation") if isinstance(result, dict) else None
        return translated.strip() if isinstance(translated, str) and translated.strip() else ""

    changed = False
    settings = get_settings()
    pending_jobs: list[tuple[str, str | int, str, str]] = []
    if summary and isinstance(summary.get("rendered"), str) and summary["rendered"].strip():
        existing = summary.get("translations") if isinstance(summary.get("translations"), dict) else {}
        if target_language not in existing:
            pending_jobs.append(("summary", "summary", summary["rendered"], "notice_summary"))

    for index, src in enumerate(sources):
        if not isinstance(src, dict):
            continue
        text = src.get("refined_text")
        if not (isinstance(text, str) and text.strip()):
            continue
        existing = src.get("translations") if isinstance(src.get("translations"), dict) else {}
        if target_language in existing:
            continue
        pending_jobs.append(("source", index, text, "notice_source"))

    if pending_jobs:
        semaphore = asyncio.Semaphore(max(1, int(getattr(settings, "source_translation_concurrency", 4) or 4)))

        async def run_job(job: tuple[str, str | int, str, str]) -> tuple[str, str | int, str]:
            job_type, key, text, translation_kind = job
            async with semaphore:
                translated = await _translate(text, translation_kind=translation_kind)
                return job_type, key, translated

        completed = await asyncio.gather(*(run_job(job) for job in pending_jobs))
        lock = _SOURCE_TRANSLATION_LOCKS.setdefault(notice_id, asyncio.Lock())
        async with lock:
            latest_row = sb.table("notices").select("extracted_content").eq("id", notice_id).single().execute().data
            latest_extracted = (latest_row or {}).get("extracted_content") or extracted
            latest_summary = latest_extracted.get("summary") if isinstance(latest_extracted.get("summary"), dict) else None
            latest_sources = latest_extracted.get("sources") if isinstance(latest_extracted.get("sources"), list) else []

            for job_type, key, translated in completed:
                if not translated:
                    continue
                if job_type == "summary" and latest_summary is not None:
                    translations = latest_summary.get("translations") if isinstance(latest_summary.get("translations"), dict) else {}
                    if target_language not in translations:
                        latest_summary.setdefault("translations", {})[target_language] = translated
                        changed = True
                    continue
                if job_type == "source" and isinstance(key, int) and 0 <= key < len(latest_sources):
                    src = latest_sources[key]
                    if isinstance(src, dict):
                        translations = src.get("translations") if isinstance(src.get("translations"), dict) else {}
                        if target_language not in translations:
                            src.setdefault("translations", {})[target_language] = translated
                            changed = True

            if changed:
                sb.table("notices").update({"extracted_content": latest_extracted}).eq("id", notice_id).execute()
            return

    if changed:
        sb.table("notices").update({"extracted_content": extracted}).eq("id", notice_id).execute()


def _school_translation_locales(school_id: str) -> list[str]:
    rows = (
        get_supabase_client()
        .table("children")
        .select("user_id")
        .eq("school_id", school_id)
        .execute()
        .data
        or []
    )
    user_ids = sorted(
        {
            str(row.get("user_id") or "").strip()
            for row in rows
            if row.get("user_id")
        },
    )
    if not user_ids:
        return []

    locales: list[str] = []
    for chunk in _chunks(user_ids, 100):
        profiles = (
            get_supabase_client()
            .table("profiles")
            .select("locale,native_language")
            .in_("id", chunk)
            .execute()
            .data
            or []
        )
        for row in profiles:
            for key in ("locale", "native_language"):
                locale = _normalized_locale(row.get(key))
                if locale and locale not in locales:
                    locales.append(locale)
    if locales:
        return locales
    return ["ko"]


def _missing_translation_locales(notice_id: str, locales: list[str]) -> list[str]:
    existing_rows = (
        get_supabase_client()
        .table("notice_ai_translations")
        .select("target_language,translated_text,validation_status")
        .eq("notice_id", notice_id)
        .execute()
        .data
        or []
    )
    completed = {
        _normalized_locale(row.get("target_language"))
        for row in existing_rows
        if _normalized_locale(row.get("target_language"))
        and str(row.get("translated_text") or "").strip()
    }
    return [locale for locale in locales if locale not in completed]


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
        "extraction_next_run_at": next_run_at,
        "extraction_error_code": error_code,
        "error_message": _truncate_error(error_message),
    }


def _claim_notice(*, notice_id: str | None, force: bool, stale_minutes: int) -> dict[str, Any] | None:
    try:
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
    except APIError as exc:
        if not _is_missing_claim_rpc_error(exc):
            raise
        LOGGER.warning(
            "claim_notice_extractions RPC not found; falling back to direct claim logic."
        )
        return _claim_notice_without_rpc(
            notice_id=notice_id,
            force=force,
            stale_minutes=stale_minutes,
        )


def _dry_run_targets(*, notice_id: str | None, limit: int) -> list[dict[str, Any]]:
    query = (
        get_supabase_client()
        .table("notices")
        .select("id,status,detail_url,created_at,extraction_error_code,extraction_next_run_at")
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
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return [str(row["id"]) for row in rows if row.get("id") and row.get("detail_url")]


def _is_missing_claim_rpc_error(exc: APIError) -> bool:
    message = str(exc)
    return (
        getattr(exc, "code", "") == "PGRST202"
        and "claim_notice_extractions" in message
    )


def _claim_notice_without_rpc(
    *,
    notice_id: str | None,
    force: bool,
    stale_minutes: int,
) -> dict[str, Any] | None:
    rows = _candidate_notice_rows(notice_id=notice_id)
    candidate = _pick_claimable_notice(
        rows,
        notice_id=notice_id,
        force=force,
        stale_minutes=stale_minutes,
    )
    if candidate is None:
        return None

    notice_id_value = str(candidate["id"])
    now_iso = _utc_now().isoformat()
    payload = {
        "status": "processing",
        "extraction_attempts": _int_value(candidate.get("extraction_attempts")) + 1,
        "extraction_started_at": now_iso,
        "extraction_next_run_at": None,
        "extraction_error_code": None,
        "error_message": None,
    }
    get_supabase_client().table("notices").update(payload).eq("id", notice_id_value).execute()
    return {**candidate, **payload}


def _candidate_notice_rows(*, notice_id: str | None) -> list[dict[str, Any]]:
    query = get_supabase_client().table("notices").select("*")
    if notice_id:
        query = query.eq("id", notice_id).limit(1)
    else:
        query = query.in_("status", ["pending", "error", "processing"]).order("created_at").limit(100)
    return query.execute().data or []


def _pick_claimable_notice(
    rows: list[dict[str, Any]],
    *,
    notice_id: str | None,
    force: bool,
    stale_minutes: int,
) -> dict[str, Any] | None:
    now = _utc_now()
    stale_cutoff = now - timedelta(minutes=stale_minutes)

    for row in rows:
        if row.get("school_id") is None or not row.get("detail_url"):
            continue
        if notice_id and str(row.get("id")) != notice_id:
            continue
        if force and notice_id:
            return row

        status = str(row.get("status") or "")
        if status == "pending":
            return row
        if status == "error":
            next_run_at = _parse_datetime_value(row.get("extraction_next_run_at"))
            attempts = _int_value(row.get("extraction_attempts"))
            error_code = str(row.get("extraction_error_code") or "")
            if (
                (error_code == "gemini_quota_exhausted" or attempts < 3)
                and (next_run_at is None or next_run_at <= now)
            ):
                return row
        if status == "processing":
            started_at = _parse_datetime_value(row.get("extraction_started_at"))
            if started_at is not None and started_at < stale_cutoff:
                return row

    return None


def _parse_datetime_value(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


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


def _source_summary(
    source: Any,
    refinement: dict[str, Any] | None = None,
    upload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_text = getattr(source, "raw_text", "") or ""
    summary: dict[str, Any] = {
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
    # 소스별 정제 결과(있으면) — 프론트가 본문/첨부를 각각 카드로 렌더한다.
    if refinement:
        summary["refined_text"] = refinement.get("refined_text", "")
        summary["needs_file"] = bool(refinement.get("needs_file"))
        summary["needs_file_reason"] = refinement.get("needs_file_reason", [])
    # Storage 업로드 결과(있으면) — 프론트 파일카드의 미리보기/다운로드 URL.
    if upload:
        summary["storage_path"] = upload.get("storage_path", "")
        summary["public_url"] = upload.get("public_url", "")
    return summary


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


def _scrub_text(value: str) -> str:
    """Drop characters that cannot be stored as UTF-8 (e.g. lone surrogates that
    OCR/model output occasionally emits, such as from a QR code or garbled glyph).

    Postgres/JSON storage is UTF-8; a lone surrogate raises UnicodeEncodeError on
    save and, because the save happens outside the per-notice guard, used to crash
    the entire extractor batch. Policy: if it can't be stored, drop it.
    """
    if not isinstance(value, str):
        return value
    return value.encode("utf-8", "ignore").decode("utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return _scrub_text(value)
    if value is None or isinstance(value, int | float | bool):
        return value
    return _scrub_text(str(value))


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalized_locale(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    locale = value.strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", locale):
        return None
    if locale == "ko":
        return None
    return locale


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _truncate_error(value: str) -> str:
    return _scrub_text(sanitize_error(value)).replace("\n", " ")[:800]


def _cap_reached(used: int, cap: int) -> bool:
    return cap > 0 and used >= cap


def _utc_now() -> datetime:
    return datetime.now(UTC)
