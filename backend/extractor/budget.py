from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class BudgetDecision:
    ok: bool
    reason: str = ""


@dataclass
class ExtractionBudget:
    max_gemini_calls: int
    max_inline_images: int
    max_ocr_bytes: int
    max_pdf_pages_for_ocr: int
    gemini_calls_used: int = 0
    inline_images_used: int = 0
    ocr_bytes_used: int = 0
    exhausted_reasons: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "ExtractionBudget":
        return cls(
            max_gemini_calls=_int_env("MAX_GEMINI_CALLS_PER_NOTICE", 8),
            max_inline_images=_int_env("MAX_INLINE_IMAGES_PER_NOTICE", 6),
            max_ocr_bytes=_int_env("MAX_TOTAL_OCR_BYTES_PER_NOTICE", 26_214_400),
            max_pdf_pages_for_ocr=_int_env("MAX_PDF_PAGES_FOR_OCR", 20),
        )

    def reserve_inline_image(self, source_id: str) -> BudgetDecision:
        if self.inline_images_used >= self.max_inline_images:
            return self._reject(f"{source_id}: max inline images exceeded")
        self.inline_images_used += 1
        return BudgetDecision(ok=True)

    def reserve_gemini_call(self, source_id: str, byte_count: int) -> BudgetDecision:
        if self.gemini_calls_used >= self.max_gemini_calls:
            return self._reject(f"{source_id}: max Gemini calls exceeded")
        if self.ocr_bytes_used + byte_count > self.max_ocr_bytes:
            return self._reject(f"{source_id}: max OCR bytes exceeded")
        self.gemini_calls_used += 1
        self.ocr_bytes_used += byte_count
        return BudgetDecision(ok=True)

    def allow_pdf_pages(self, source_id: str, page_count: int) -> BudgetDecision:
        if page_count > self.max_pdf_pages_for_ocr:
            return self._reject(f"{source_id}: max PDF pages for OCR exceeded ({page_count})")
        return BudgetDecision(ok=True)

    @property
    def budget_exhausted(self) -> bool:
        return bool(self.exhausted_reasons)

    def metadata(self) -> dict[str, object]:
        return {
            "gemini_calls_used": self.gemini_calls_used,
            "inline_images_used": self.inline_images_used,
            "ocr_bytes_used": self.ocr_bytes_used,
            "budget_exhausted": self.budget_exhausted,
            "budget_exhausted_reasons": list(self.exhausted_reasons),
            "max_gemini_calls": self.max_gemini_calls,
            "max_inline_images": self.max_inline_images,
            "max_ocr_bytes": self.max_ocr_bytes,
            "max_pdf_pages_for_ocr": self.max_pdf_pages_for_ocr,
        }

    def _reject(self, reason: str) -> BudgetDecision:
        if reason not in self.exhausted_reasons:
            self.exhausted_reasons.append(reason)
        return BudgetDecision(ok=False, reason=reason)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
