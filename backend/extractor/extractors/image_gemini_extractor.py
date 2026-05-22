from __future__ import annotations

import os
from pathlib import Path
import warnings

from PIL import Image, ImageOps

from extractor.budget import ExtractionBudget
from extractor.models import ExtractedText
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor, ocr_prompt


IMAGE_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}
Image.MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "50000000"))


async def extract_image_text(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor,
    budget: ExtractionBudget | None = None,
    source_id: str = "",
) -> ExtractedText:
    normalized_path = _normalize_image(path)
    mime_type = IMAGE_MIME_BY_SUFFIX.get(normalized_path.suffix.lower(), "image/png")
    if budget is not None:
        decision = budget.reserve_gemini_call(source_id or source_name, normalized_path.stat().st_size)
        if not decision.ok:
            return ExtractedText(
                source=source_name,
                method="gemini_vision",
                text="",
                status="budget_exhausted",
                warnings=[decision.reason],
            )
    result = await gemini.extract_path(
        normalized_path,
        mime_type=mime_type,
        prompt=ocr_prompt(source_name),
    )
    return ExtractedText(
        source=source_name,
        method="gemini_vision",
        text=result.text,
        status="success" if result.text.strip() else "empty_or_unreadable",
        confidence=result.confidence,
        warnings=result.warnings,
        metadata={"detected_layout": result.detected_layout, "source_pages": result.source_pages},
    )


def _normalize_image(path: Path) -> Path:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as probe:
                probe.verify()
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image)
                image.load()
                image.thumbnail((2400, 2400))
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                output = path.with_suffix(".normalized.png")
                image.save(output, format="PNG", optimize=True)
                return output
    except Image.DecompressionBombError as exc:
        raise RuntimeError(f"image_decompression_bomb: {exc}") from exc
    except Image.DecompressionBombWarning as exc:
        raise RuntimeError(f"image_decompression_bomb_warning: {exc}") from exc
