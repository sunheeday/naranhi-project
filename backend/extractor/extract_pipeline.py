from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
import yaml

from extractor.budget import ExtractionBudget
from extractor.detail_fetcher import fetch_detail
from extractor.file_downloader import download_attachment
from extractor.file_type_detector import detect_file_type
from extractor.html_text_extractor import extract_html_text
from extractor.http_security import sanitize_error
from extractor.models import (
    AttachmentExtraction,
    AttachmentRef,
    CaseConfig,
    DownloadedFile,
    ExtractedText,
    ExtractionResult,
    SourceCandidate,
    SourceExtraction,
)
from extractor.notice_structurer import combined_raw_text
from extractor.quality import file_sha256, text_fingerprint, text_quality_score
from extractor.source_inventory import attach_direct_file, build_source_inventory
from extractor.source_merger import assign_roles_and_dedupe
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor
from extractor.extractors.hwp_extractor import extract_hwp_text
from extractor.extractors.hwpx_extractor import extract_hwpx_text
from extractor.extractors.image_gemini_extractor import extract_image_text
from extractor.extractors.pdf_extractor import extract_pdf_text
from extractor.extractors.xlsx_extractor import extract_xlsx_text


OUTPUT_DIR = Path("outputs")
MIN_TEXT_CHARS = 20
MIN_HTML_BODY_CHARS = 120
SOURCE_ATTACHMENT_TYPES = {"attachment", "attachment_pdf", "attachment_hwp", "attachment_hwpx", "attachment_xlsx", "attachment_image", "direct_file"}
SOURCE_IMAGE_TYPES = {"inline_image", "attachment_image"}
CONTENT_IMAGE_TERMS = ("안내", "가정통신문", "첨부", "본문", "홍보", "포스터", "교육", "신청", "제출", "기간", "대상", "일시", "준비")
NOISE_IMAGE_TERMS = ("logo", "icon", "banner", "btn", "button", "spacer", "blank", "로고", "배너", "아이콘")


async def run_cases(cases: list[CaseConfig], *, output_dir: Path = OUTPUT_DIR) -> list[ExtractionResult]:
    load_dotenv(Path(".env"))
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[ExtractionResult] = []
    for index, case in enumerate(cases):
        print(f"[{index + 1:02d}/{len(cases):02d}] {case.id} {case.detail_url}")
        try:
            result = await extract_case(case)
        except Exception as exc:  # noqa: BLE001 - batch should continue across cases.
            result = _failed_result(case, "internal_error", f"{type(exc).__name__}: {sanitize_error(exc)}")
        results.append(result)
        result_path = output_dir / f"{_timestamp()}-{case.id}.json"
        result_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    summary_path = output_dir / f"{_timestamp()}-summary.json"
    summary_path.write_text(
        json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"summary={summary_path}")
    return results


async def extract_case(case: CaseConfig, *, gemini_client: GeminiDocumentExtractor | None = None) -> ExtractionResult:
    errors: list[str] = []
    budget = ExtractionBudget.from_env()
    owns_gemini_client = gemini_client is None
    gemini_client = gemini_client or GeminiDocumentExtractor()
    gemini = gemini_client if gemini_client.api_keys else None

    try:
        with tempfile.TemporaryDirectory(prefix="naranhi-extract-") as temp_name:
            temp_dir = Path(temp_name)
            try:
                fetched = await fetch_detail(case.detail_url, context=case.fetch_context)
            except Exception as exc:
                return _failed_result(
                    case,
                    "content_fetch_failed",
                    f"{type(exc).__name__}: {sanitize_error(exc)}",
                    metadata=budget.metadata(),
                )

            inventory = build_source_inventory(fetched)
            if not fetched.is_html and inventory:
                inventory[0] = _prepare_direct_file_source(fetched, inventory[0], temp_dir)

            html_text = extract_html_text(fetched.text) if fetched.is_html else ""
            sources: list[SourceExtraction] = []
            for candidate in inventory:
                source = await _extract_source(
                    candidate,
                    fetched_final_url=fetched.final_url,
                    html_text=html_text,
                    temp_dir=temp_dir,
                    gemini=gemini,
                    budget=budget,
                )
                sources.append(source)

        sources, included_source_ids = assign_roles_and_dedupe(sources)
        raw_text = combined_raw_text(sources, included_source_ids)
        content_kind = _classify_content_kind(sources)
        status = _status_from_sources(sources, raw_text)

        for source in sources:
            if source.status not in {"success", "partial_success", "skipped"}:
                for source_error in source.errors:
                    errors.append(f"{source.source_id}: {source_error}")

        if case.expected_kind and case.expected_kind != content_kind:
            errors.append(f"expected_kind_mismatch expected={case.expected_kind} actual={content_kind}")
            if status == "success":
                status = "partial_success"

        return ExtractionResult(
            case_id=case.id,
            detail_url=case.detail_url,
            final_url=fetched.final_url,
            content_kind=content_kind,
            status=status,
            raw_text=raw_text,
            sources=sources,
            included_source_ids=included_source_ids,
            errors=errors,
            metadata={**budget.metadata(), "fetch": fetched.metadata},
            expected_kind=case.expected_kind,
            html_text=_html_text_from_sources(sources),
            attachments=_legacy_attachment_refs(inventory),
            image_texts=_legacy_image_texts(sources),
            attachment_texts=_legacy_attachment_texts(sources),
            combined_text=raw_text,
            methods=_methods_from_sources(sources),
        )
    except Exception as exc:  # noqa: BLE001 - normalize unexpected per-case failures.
        return _failed_result(
            case,
            "internal_error",
            f"{type(exc).__name__}: {sanitize_error(exc)}",
            metadata=budget.metadata(),
        )
    finally:
        if owns_gemini_client:
            await gemini_client.aclose()


async def _extract_source(
    candidate: SourceCandidate,
    *,
    fetched_final_url: str,
    html_text: str,
    temp_dir: Path,
    gemini: GeminiDocumentExtractor | None,
    budget: ExtractionBudget,
) -> SourceExtraction:
    if candidate.source_type == "html_body":
        return _source_from_text(
            candidate,
            raw_text=candidate.source_text,
            method="html",
            status="success" if candidate.source_text.strip() else "empty_or_unreadable",
            confidence=0.9 if candidate.source_text.strip() else 0.0,
            metadata={"chars": len(candidate.source_text)},
        )

    if candidate.source_type == "inline_image":
        ocr_decision = _inline_image_ocr_decision(candidate, html_text=html_text, budget=budget)
        if not ocr_decision["ok"]:
            return _source_from_text(
                candidate,
                raw_text="",
                method="skipped",
                status=str(ocr_decision["status"]),
                errors=[str(ocr_decision["reason"])],
                metadata={"ocr_inline_images": os.getenv("OCR_INLINE_IMAGES", "auto")},
            )
        if candidate.inline_ref is None:
            return _source_from_text(candidate, raw_text="", method="inline_image", status="extract_failed", errors=["missing_inline_ref"])
        try:
            downloaded = await download_attachment(
                candidate.inline_ref,
                output_dir=temp_dir / "downloads",
                max_file_size_mb=_max_file_size_mb(),
                referer=fetched_final_url,
            )
            if gemini is None:
                raise RuntimeError("Gemini API key is required for image OCR.")
            extracted = await extract_image_text(
                downloaded.path,
                source_name=downloaded.filename,
                gemini=gemini,
                budget=budget,
                source_id=candidate.source_id,
            )
            return _source_from_extracted(candidate, downloaded, extracted, file_type="image")
        except Exception as exc:
            return _source_from_text(
                candidate,
                raw_text="",
                method="gemini_vision",
                status="ocr_failed",
                errors=[f"{type(exc).__name__}: {sanitize_error(exc)}"],
            )

    if candidate.direct_file is not None:
        downloaded = candidate.direct_file
    elif candidate.attachment_ref is not None:
        try:
            downloaded = await download_attachment(
                candidate.attachment_ref,
                output_dir=temp_dir / "downloads",
                max_file_size_mb=_max_file_size_mb(),
                referer=fetched_final_url,
            )
        except Exception as exc:
            return _source_from_text(
                candidate,
                raw_text="",
                method="download",
                status="download_failed",
                errors=[f"{type(exc).__name__}: {sanitize_error(exc)}"],
            )
    else:
        return _source_from_text(candidate, raw_text="", method="unknown", status="extract_failed", errors=["missing_attachment_ref"])

    file_type = detect_file_type(downloaded.path, downloaded.filename, downloaded.content_type)
    if not _expected_file_type_matches(candidate.source_type, file_type):
        return _source_from_text(
            candidate,
            raw_text="",
            method="file_type_check",
            status="unsupported_or_spoofed_file",
            errors=[f"expected={candidate.source_type} actual={file_type}"],
            file_hash=file_sha256(downloaded.path),
            filename=downloaded.filename,
            origin_url=downloaded.url,
            metadata={**downloaded.metadata, "file_type": file_type},
        )

    extracted, file_type = await _extract_downloaded_file(
        downloaded,
        gemini=gemini,
        work_dir=temp_dir,
        budget=budget,
        source_id=candidate.source_id,
        file_type=file_type,
    )
    return _source_from_extracted(candidate, downloaded, extracted, file_type=file_type)


async def _extract_downloaded_file(
    downloaded: DownloadedFile,
    *,
    gemini: GeminiDocumentExtractor | None,
    work_dir: Path,
    budget: ExtractionBudget,
    source_id: str,
    file_type: str | None = None,
) -> tuple[ExtractedText, str]:
    file_type = file_type or detect_file_type(downloaded.path, downloaded.filename, downloaded.content_type)
    try:
        if file_type == "pdf":
            extracted = await extract_pdf_text(
                downloaded.path,
                source_name=downloaded.filename,
                gemini=gemini,
                budget=budget,
                source_id=source_id,
            )
        elif file_type == "image":
            if gemini is None:
                raise RuntimeError("Gemini API key is required for image OCR.")
            extracted = await extract_image_text(
                downloaded.path,
                source_name=downloaded.filename,
                gemini=gemini,
                budget=budget,
                source_id=source_id,
            )
        elif file_type == "hwpx":
            extracted = await extract_hwpx_text(
                downloaded.path,
                source_name=downloaded.filename,
                gemini=gemini,
                budget=budget,
                source_id=source_id,
            )
        elif file_type == "hwp":
            extracted = await extract_hwp_text(downloaded.path, source_name=downloaded.filename, gemini=gemini, work_dir=work_dir)
        elif file_type == "xlsx":
            extracted = await extract_xlsx_text(
                downloaded.path,
                source_name=downloaded.filename,
            )
        elif file_type == "html":
            extracted = ExtractedText(
                source=downloaded.filename,
                method="html_file",
                text=extract_html_text(downloaded.path.read_text(encoding="utf-8", errors="replace")),
                status="success",
            )
        else:
            extracted = ExtractedText(
                source=downloaded.filename,
                method="unsupported",
                text="",
                status="unsupported_file_type",
                warnings=[f"file_type={file_type}"],
            )
    except Exception as exc:
        extracted = ExtractedText(
            source=downloaded.filename,
            method=f"{file_type}_extract_failed",
            text="",
            status="extract_failed",
            warnings=[f"{type(exc).__name__}: {sanitize_error(exc)}"],
        )
    return extracted, file_type


async def _extract_downloaded_attachment(
    downloaded: DownloadedFile,
    *,
    gemini: GeminiDocumentExtractor | None,
    work_dir: Path,
) -> AttachmentExtraction:
    extracted, file_type = await _extract_downloaded_file(
        downloaded,
        gemini=gemini,
        work_dir=work_dir,
        budget=ExtractionBudget.from_env(),
        source_id=downloaded.filename,
    )
    return AttachmentExtraction(
        url=downloaded.url,
        filename=downloaded.filename,
        file_type=file_type,
        status=extracted.status,
        text=extracted.text,
        methods=[extracted.method],
        errors=extracted.warnings,
        content_type=downloaded.content_type,
        size_bytes=downloaded.size_bytes,
    )


def _source_from_extracted(
    candidate: SourceCandidate,
    downloaded: DownloadedFile,
    extracted: ExtractedText,
    *,
    file_type: str,
) -> SourceExtraction:
    metadata = dict(extracted.metadata)
    metadata.update({**downloaded.metadata, "file_type": file_type, "size_bytes": downloaded.size_bytes, "content_type": downloaded.content_type})
    confidence = extracted.confidence if extracted.confidence is not None else _default_confidence(extracted.method, extracted.status)
    return _source_from_text(
        candidate,
        raw_text=extracted.text,
        method=extracted.method,
        status=extracted.status,
        confidence=confidence,
        errors=extracted.warnings,
        file_hash=file_sha256(downloaded.path),
        filename=downloaded.filename,
        origin_url=downloaded.url,
        metadata=metadata,
    )


def _source_from_text(
    candidate: SourceCandidate,
    *,
    raw_text: str,
    method: str,
    status: str,
    confidence: float = 0.0,
    errors: list[str] | None = None,
    file_hash: str = "",
    filename: str | None = None,
    origin_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceExtraction:
    final_status = status
    if final_status == "success" and len(raw_text.strip()) < MIN_TEXT_CHARS:
        final_status = "empty_or_unreadable"
    fingerprint = text_fingerprint(raw_text)
    quality_score = text_quality_score(raw_text, confidence)
    return SourceExtraction(
        source_id=candidate.source_id,
        source_type=candidate.source_type,
        source_role="unknown",
        origin_url=origin_url or candidate.origin_url,
        filename=filename if filename is not None else candidate.filename,
        file_hash=file_hash,
        text_fingerprint=fingerprint,
        duplicate_of=None,
        extraction_method=method,
        status=final_status,
        raw_text=raw_text,
        structured={},
        confidence=confidence,
        quality_score=quality_score,
        errors=errors or [],
        metadata={
            "kind_hint": candidate.kind_hint,
            "order_index": candidate.order_index,
            "source_text": candidate.source_text,
            **(metadata or {}),
        },
    )


def _prepare_direct_file_source(fetched: Any, candidate: SourceCandidate, temp_dir: Path) -> SourceCandidate:
    filename = _filename_from_headers_or_url(fetched.headers, fetched.final_url)
    direct_path = temp_dir / "direct" / filename
    direct_path.parent.mkdir(parents=True, exist_ok=True)
    direct_path.write_bytes(fetched.content)
    downloaded = DownloadedFile(
        url=fetched.final_url,
        path=direct_path,
        filename=filename,
        content_type=fetched.content_type,
        size_bytes=len(fetched.content),
        kind_hint="direct_file",
        metadata=fetched.metadata,
    )
    return attach_direct_file(candidate, downloaded)


def load_cases(path: Path) -> list[CaseConfig]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = payload.get("cases") or []
    return [
        CaseConfig(
            id=str(item["id"]),
            detail_url=str(item["detail_url"]),
            expected_kind=item.get("expected_kind"),
        )
        for item in cases
    ]


def _classify_content_kind(sources: list[SourceExtraction]) -> str:
    has_html = any(source.source_type == "html_body" and len(source.raw_text.strip()) >= MIN_HTML_BODY_CHARS for source in sources)
    has_image = any(source.source_type in SOURCE_IMAGE_TYPES for source in sources)
    has_attachment = any(source.source_type in SOURCE_ATTACHMENT_TYPES and source.source_type not in {"attachment_image"} for source in sources)

    category_count = sum(1 for value in (has_html, has_image, has_attachment) if value)
    if category_count >= 3:
        return "mixed"
    if has_html and has_image:
        return "html_text_with_images"
    if has_html and has_attachment:
        return "html_text_with_attachments"
    if has_image and has_attachment:
        return "image_with_attachments"
    if has_html:
        return "html_text_only"
    if has_image:
        return "image_only"
    if has_attachment:
        return "attachment_only"
    return "empty_or_unreadable"


def _status_from_sources(sources: list[SourceExtraction], raw_text: str) -> str:
    readable = [source for source in sources if source.status in {"success", "partial_success"} and len(source.raw_text.strip()) >= MIN_TEXT_CHARS]
    if not readable:
        return "empty_or_unreadable"
    failed = [
        source
        for source in sources
        if source.status not in {"success", "partial_success", "skipped"}
        and source.source_role not in {"metadata_only", "duplicate"}
    ]
    if failed:
        return "partial_success"
    return "success" if len(raw_text.strip()) >= MIN_TEXT_CHARS else "partial_success"


def _inline_image_ocr_decision(
    candidate: SourceCandidate,
    *,
    html_text: str,
    budget: ExtractionBudget,
) -> dict[str, object]:
    mode = os.getenv("OCR_INLINE_IMAGES", "auto").strip().lower()
    if mode in {"never", "false", "0", "no", "off"}:
        return {"ok": False, "status": "skipped", "reason": "inline_image_ocr_skipped_by_policy"}

    haystack = _inline_image_haystack(candidate)
    if _looks_like_noise_image(haystack):
        return {"ok": False, "status": "skipped", "reason": "inline_image_noise_filter"}

    should_ocr = mode in {"always", "true", "1", "yes"}
    if not should_ocr:
        should_ocr = len(html_text.strip()) < MIN_HTML_BODY_CHARS or any(term in haystack for term in CONTENT_IMAGE_TERMS)
    if not should_ocr:
        return {"ok": False, "status": "skipped", "reason": "inline_image_no_content_signal"}

    budget_decision = budget.reserve_inline_image(candidate.source_id)
    if not budget_decision.ok:
        return {"ok": False, "status": "budget_exhausted", "reason": budget_decision.reason}
    return {"ok": True, "status": "queued", "reason": ""}


def _inline_image_haystack(candidate: SourceCandidate) -> str:
    alt = candidate.inline_ref.alt if candidate.inline_ref else ""
    return f"{candidate.origin_url} {candidate.filename} {candidate.source_text} {alt}".lower()


def _looks_like_noise_image(haystack: str) -> bool:
    return any(term in haystack for term in NOISE_IMAGE_TERMS)


def _expected_file_type_matches(source_type: str, file_type: str) -> bool:
    expected = {
        "attachment_pdf": {"pdf"},
        "attachment_hwp": {"hwp"},
        "attachment_hwpx": {"hwpx"},
        "attachment_xlsx": {"xlsx"},
        "attachment_image": {"image"},
        "inline_image": {"image"},
    }.get(source_type)
    if expected is None:
        return True
    return file_type in expected


def _legacy_attachment_refs(inventory: list[SourceCandidate]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for candidate in inventory:
        if candidate.attachment_ref is not None:
            refs.append(asdict(candidate.attachment_ref))
        elif candidate.direct_file is not None:
            refs.append(
                {
                    "url": candidate.direct_file.url,
                    "filename": candidate.direct_file.filename,
                    "source_text": "direct file URL",
                    "kind_hint": "direct_file",
                }
            )
    return refs


def _legacy_image_texts(sources: list[SourceExtraction]) -> list[dict[str, Any]]:
    return [
        {
            "source": source.filename or source.origin_url,
            "method": source.extraction_method,
            "text": source.raw_text,
            "status": source.status,
            "confidence": source.confidence,
            "warnings": source.errors,
            "metadata": source.metadata,
        }
        for source in sources
        if source.source_type in SOURCE_IMAGE_TYPES
    ]


def _legacy_attachment_texts(sources: list[SourceExtraction]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        if source.source_type not in SOURCE_ATTACHMENT_TYPES:
            continue
        rows.append(
            AttachmentExtraction(
                url=source.origin_url,
                filename=source.filename,
                file_type=str(source.metadata.get("file_type") or source.metadata.get("kind_hint") or ""),
                status=source.status,
                text=source.raw_text,
                methods=[source.extraction_method] if source.extraction_method else [],
                errors=source.errors,
                content_type=str(source.metadata.get("content_type") or ""),
                size_bytes=int(source.metadata.get("size_bytes") or 0),
            ).to_dict()
        )
    return rows


def _html_text_from_sources(sources: list[SourceExtraction]) -> str:
    for source in sources:
        if source.source_type == "html_body":
            return source.raw_text
    return ""


def _methods_from_sources(sources: list[SourceExtraction]) -> list[str]:
    methods = [
        source.extraction_method
        for source in sources
        if source.extraction_method and source.extraction_method != "skipped"
    ]
    return _dedupe(methods)


def _failed_result(
    case: CaseConfig,
    status: str,
    error: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        case_id=case.id,
        detail_url=case.detail_url,
        final_url=case.detail_url,
        content_kind="content_fetch_failed",
        status=status,
        raw_text="",
        sources=[],
        included_source_ids=[],
        errors=[error],
        metadata=metadata or {},
        expected_kind=case.expected_kind,
        html_text="",
        attachments=[],
        image_texts=[],
        attachment_texts=[],
        combined_text="",
        methods=[],
    )


def _default_confidence(method: str, status: str) -> float:
    if status not in {"success", "partial_success"}:
        return 0.0
    if method.startswith("gemini"):
        return 0.72
    if method in {"html", "html_file", "hwp_ole_bodytext_filtered", "hwp_prv_text", "hwpx_xml", "pdf_pymupdf"}:
        return 0.86
    return 0.65


def _max_file_size_mb() -> int:
    try:
        return int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    except ValueError:
        return 50


def _filename_from_url(url: str) -> str:
    name = unquote(Path(urlparse(url).path).name)
    return name or "direct-file"


def _filename_from_headers_or_url(headers: dict[str, str], url: str) -> str:
    disposition = headers.get("content-disposition", "")
    filename = _parse_content_disposition_filename(disposition)
    return filename or _filename_from_url(url)


def _parse_content_disposition_filename(value: str) -> str:
    star = re.search(r"""filename\*\s*=\s*([^']*)''([^;]+)""", value, re.IGNORECASE)
    if star:
        encoding = star.group(1) or "utf-8"
        try:
            return unquote(star.group(2), encoding=encoding)
        except LookupError:
            return unquote(star.group(2))
    normal = re.search(r"""filename\s*=\s*"?([^";]+)"?""", value, re.IGNORECASE)
    if normal:
        return _decode_header_filename(normal.group(1).strip())
    return ""


def _decode_header_filename(value: str) -> str:
    decoded = unquote(value)
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            candidate = decoded.encode("latin-1").decode(encoding)
        except UnicodeError:
            continue
        if any("가" <= char <= "힣" for char in candidate):
            return candidate
    return decoded


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract original text from school notice detail pages and attachments.")
    parser.add_argument("--cases", type=Path, help="YAML file containing detail_url test cases.")
    parser.add_argument("--url", help="Single detail URL to extract.")
    parser.add_argument("--case-id", default="manual_url", help="Case id used with --url.")
    parser.add_argument("--expected-kind", default=None)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.url:
        cases = [CaseConfig(id=args.case_id, detail_url=args.url, expected_kind=args.expected_kind)]
    elif args.cases:
        cases = load_cases(args.cases)
    else:
        raise SystemExit("--cases 또는 --url 중 하나가 필요합니다.")
    await run_cases(cases, output_dir=args.output_dir)


if __name__ == "__main__":
    asyncio.run(main())
