from __future__ import annotations

from pathlib import Path

import fitz

from extractor.budget import ExtractionBudget
from extractor.models import ExtractedText
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor, ocr_prompt


async def extract_pdf_text(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor | None,
    budget: ExtractionBudget | None = None,
    source_id: str = "",
    min_text_chars: int = 80,
) -> ExtractedText:
    try:
        text = _extract_selectable_text(path)
    except Exception as exc:
        text = ""
        selectable_error = f"{type(exc).__name__}: {exc}"
    else:
        selectable_error = ""

    if len(text.strip()) >= min_text_chars:
        return ExtractedText(
            source=source_name,
            method="pdf_pymupdf",
            text=text,
            status="success",
            metadata={"selectable_text_chars": len(text)},
        )

    if gemini is None:
        return ExtractedText(
            source=source_name,
            method="pdf_pymupdf",
            text=text,
            status="empty_or_unreadable",
            warnings=["PDF selectable text is too short and Gemini is not configured."],
            metadata={"selectable_error": selectable_error, "selectable_text_chars": len(text)},
        )

    page_count = _page_count(path)
    if budget is not None:
        page_decision = budget.allow_pdf_pages(source_id or source_name, page_count)
        if not page_decision.ok:
            return ExtractedText(
                source=source_name,
                method="pdf_gemini_document",
                text=text,
                status="budget_exhausted",
                warnings=[page_decision.reason],
                metadata={
                    "selectable_error": selectable_error,
                    "selectable_text_chars": len(text),
                    "page_count": page_count,
                },
            )
        call_decision = budget.reserve_gemini_call(source_id or source_name, path.stat().st_size)
        if not call_decision.ok:
            return ExtractedText(
                source=source_name,
                method="pdf_gemini_document",
                text=text,
                status="budget_exhausted",
                warnings=[call_decision.reason],
                metadata={
                    "selectable_error": selectable_error,
                    "selectable_text_chars": len(text),
                    "page_count": page_count,
                },
            )

    result = await gemini.extract_path(path, mime_type="application/pdf", prompt=ocr_prompt(source_name))
    warnings = list(result.warnings)
    if selectable_error:
        warnings.append(selectable_error)
    if text.strip():
        warnings.append("PyMuPDF selectable text was short; Gemini OCR result was used.")
    return ExtractedText(
        source=source_name,
        method="pdf_gemini_document",
        text=result.text,
        status="success" if result.text.strip() else "empty_or_unreadable",
        confidence=result.confidence,
        warnings=warnings,
        metadata={
            "detected_layout": result.detected_layout,
            "source_pages": result.source_pages,
            "selectable_text_chars": len(text),
            "page_count": page_count,
        },
    )


def _extract_selectable_text(path: Path) -> str:
    lines: list[str] = []
    with fitz.open(path) as document:
        for page in document:
            text = page.get_text("text").strip()
            if text:
                lines.append(text)
    return "\n\n".join(lines)


def _page_count(path: Path) -> int:
    with fitz.open(path) as document:
        return document.page_count
