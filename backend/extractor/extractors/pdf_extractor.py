from __future__ import annotations

import re
from pathlib import Path

import fitz

from extractor.budget import ExtractionBudget
from extractor.models import ExtractedText
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor, ocr_prompt


_PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")
_SYMBOL_ONLY_RE = re.compile(r"^[\*\.\-\=\#\_]+$")
_DECORATIVE_TOKEN_RE = re.compile(r"^[A-Za-z]$")


def _is_decorative_line(line: str) -> bool:
    """디자인 장식용 단일 글자들로만 구성된 줄을 감지.

    예: 'Y D O T N I G C B N U A' (포스터 배경 워드아트 OCR 결과).
    - 토큰 4개 미만이면 판별 보류 (정상 짧은 문장 보호).
    - 단일 알파벳 토큰이 전체의 80% 이상이면 장식으로 판단.
    """
    tokens = line.split()
    if len(tokens) < 4:
        return False
    single_letter = sum(1 for t in tokens if _DECORATIVE_TOKEN_RE.match(t))
    return single_letter / len(tokens) >= 0.8


def _filter_decorative_lines(text: str) -> str:
    """줄 단위로 _is_decorative_line 적용 (Gemini OCR 결과 후처리용)."""
    if not text:
        return text
    return "\n".join(line for line in text.splitlines() if not _is_decorative_line(line))


_FRAG_BULLETS = ("#", "-", "|", "*", "※", "○", "•", "□", ">", "❍", "∙", "·", "❑", "◦")
_FRAG_SENTEND = (".", "!", "?", ":", ")", "）", "」", "』", "]", "다", "요", "함", "음", "임", "됨")


def _looks_flattened(text: str) -> bool:
    """PyMuPDF 가 다단/표 레이아웃을 세로로 깨뜨렸는지 감지(짧은 파편 줄 비율로).

    다단·표가 있는 PDF 는 블록 정렬만으로 셀이 세로로 흩어져(구분/1명/2명/… 각 줄), 짧은 파편
    줄이 많아진다. 이때는 PyMuPDF 텍스트보다 레이아웃을 읽는 Gemini OCR 이 정확하므로 폴백한다.
    (quality_gate 의 평탄화 신호와 같은 기준 — 파편 줄 45% 초과. 정상 산문은 긴 줄이라 안 걸린다.)
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < 8:
        return False
    frags = sum(
        1
        for line in lines
        if len(line) < 12 and not line.startswith(_FRAG_BULLETS) and not line.endswith(_FRAG_SENTEND)
    )
    return frags / len(lines) > 0.45


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
        page_count = _page_count(path)
    except Exception:  # noqa: BLE001
        page_count = 0

    try:
        text = _extract_selectable_text(path)
    except Exception as exc:
        text = ""
        selectable_error = f"{type(exc).__name__}: {exc}"
    else:
        selectable_error = ""

    # PyMuPDF 텍스트가 충분하면 쓰되, 표/다단이 세로로 깨졌으면(파편 다수) Gemini OCR 로 폴백.
    flattened = gemini is not None and len(text.strip()) >= min_text_chars and _looks_flattened(text)
    if len(text.strip()) >= min_text_chars and not flattened:
        return ExtractedText(
            source=source_name,
            method="pdf_pymupdf",
            text=text,
            status="success",
            metadata={"selectable_text_chars": len(text), "page_count": page_count},
        )

    if gemini is None:
        return ExtractedText(
            source=source_name,
            method="pdf_pymupdf",
            text=text,
            status="empty_or_unreadable",
            warnings=["PDF selectable text is too short and Gemini is not configured."],
            metadata={
                "selectable_error": selectable_error,
                "selectable_text_chars": len(text),
                "page_count": page_count,
            },
        )

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
    cleaned_text = _filter_decorative_lines(result.text)
    warnings = list(result.warnings)
    if selectable_error:
        warnings.append(selectable_error)
    if text.strip():
        warnings.append("PyMuPDF text was short or layout-flattened; Gemini OCR result was used.")
    return ExtractedText(
        source=source_name,
        method="pdf_gemini_document",
        text=cleaned_text,
        status="success" if cleaned_text.strip() else "empty_or_unreadable",
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
    """PDF에서 텍스트 추출 (블록 단위 + 노이즈 필터).

    - blocks 모드: 페이지 위→아래, 왼쪽→오른쪽 위치 순으로 정렬해 표/캘릿아웃의
      셀이 짝지어 나오도록 한다.
    - 노이즈 필터: 진짜 페이지 번호(위/아래 여백에 단독으로 놓인 짧은 숫자 블록)와
      기호만 있는 줄을 제거한다. 표의 숫자 셀(24·120·116 등)은 라벨과 한 블록에
      묶이거나 본문 영역에 있으므로 페이지번호로 오인·삭제하지 않고 보존한다.
    """
    pages: list[str] = []
    with fitz.open(path) as document:
        for page in document:
            page_height = page.rect.height
            margin = page_height * 0.06
            blocks = page.get_text("blocks")
            text_blocks = sorted(
                [b for b in blocks if b[6] == 0],
                key=lambda b: (round(b[1], 1), round(b[0], 1)),
            )
            clean_lines: list[str] = []
            for block in text_blocks:
                block_lines = [ln.strip() for ln in block[4].splitlines() if ln.strip()]
                if not block_lines:
                    continue
                # 페이지 번호: 블록 전체가 짧은 단독 숫자 하나이고 위/아래 여백에
                # 있을 때만 제거. (표 셀 숫자는 라벨과 같은 블록이거나 본문 영역이라
                # 여기서 걸리지 않아 보존됨)
                in_margin = block[3] <= margin or block[1] >= page_height - margin
                if len(block_lines) == 1 and in_margin and _PAGE_NUMBER_RE.match(block_lines[0]):
                    continue
                for line in block_lines:
                    if _SYMBOL_ONLY_RE.match(line):
                        continue
                    if _is_decorative_line(line):
                        continue
                    clean_lines.append(line)
            if clean_lines:
                pages.append("\n".join(clean_lines))
    return "\n\n".join(pages)


def _page_count(path: Path) -> int:
    with fitz.open(path) as document:
        return document.page_count
