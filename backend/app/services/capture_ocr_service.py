from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor, ocr_prompt


SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpg",
    "image/heic",
    "image/heif",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
}

IMAGE_MIME_BY_SUFFIX = {
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class CaptureOcrResult:
    extracted_text: str
    mime_type: str
    confidence: float | None = None
    is_readable: bool = False
    warnings: list[str] = field(default_factory=list)
    detected_layout: str = "unknown"


class CaptureOcrProvider(Protocol):
    async def extract_bytes(self, data: bytes, *, mime_type: str, source_name: str) -> CaptureOcrResult:
        """Extract visible notice text from image bytes."""


class GeminiCaptureOcrProvider:
    """Thin adapter that keeps camera OCR isolated from route handling."""

    async def extract_bytes(self, data: bytes, *, mime_type: str, source_name: str) -> CaptureOcrResult:
        # TODO: Add image normalization/recompression here before OCR if mobile uploads
        # start hitting model inline payload limits or EXIF orientation issues.
        settings = get_settings()
        async with GeminiDocumentExtractor(
            api_keys=settings.gemini_key_material,
            model=settings.gemini_model,
            timeout=settings.gemini_timeout_seconds,
            vertex_project=settings.vertex_ai_project_id,
            vertex_location=settings.vertex_ai_location,
        ) as extractor:
            result = await extractor.extract_bytes(
                data,
                mime_type=mime_type,
                prompt=ocr_prompt(source_name),
            )
        return CaptureOcrResult(
            extracted_text=result.text,
            mime_type=mime_type,
            confidence=result.confidence,
            is_readable=result.is_readable,
            warnings=result.warnings,
            detected_layout=result.detected_layout,
        )


class CaptureOcrService:
    def __init__(self, provider: CaptureOcrProvider | None = None) -> None:
        self.provider = provider or GeminiCaptureOcrProvider()

    async def extract_text(
        self,
        *,
        data: bytes,
        mime_type: str | None,
        source_name: str | None = None,
    ) -> CaptureOcrResult:
        if not data:
            raise ValueError("Image payload is empty.")

        resolved_mime_type = _normalize_mime_type(mime_type, source_name=source_name)
        if resolved_mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            supported = ", ".join(sorted(SUPPORTED_IMAGE_MIME_TYPES))
            raise ValueError(f"Unsupported image content type. Supported: {supported}.")

        return await self.provider.extract_bytes(
            data,
            mime_type=_canonical_mime_type(resolved_mime_type),
            source_name=source_name or "camera_notice",
        )


def _normalize_mime_type(value: str | None, *, source_name: str | None = None) -> str:
    normalized = (value or "").split(";", 1)[0].strip().lower()
    if normalized and normalized != "application/octet-stream":
        return normalized

    suffix = Path(source_name or "").suffix.lower()
    return IMAGE_MIME_BY_SUFFIX.get(suffix, normalized or "application/octet-stream")


def _canonical_mime_type(value: str) -> str:
    if value == "image/jpg":
        return "image/jpeg"
    return value


def get_capture_ocr_service() -> CaptureOcrService:
    return CaptureOcrService()
