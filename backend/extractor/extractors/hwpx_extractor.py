from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from extractor.archive_security import validate_zip_limits
from extractor.budget import ExtractionBudget
from extractor.models import ExtractedText
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor
from extractor.extractors.image_gemini_extractor import extract_image_text


async def extract_hwpx_text(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor | None,
    budget: ExtractionBudget | None = None,
    source_id: str = "",
) -> ExtractedText:
    warnings: list[str] = []
    try:
        text = _extract_hwpx_structured_text(path)
    except Exception as exc:
        text = ""
        warnings.append(f"hwpx_xml_failed: {type(exc).__name__}: {exc}")

    if text.strip():
        return ExtractedText(
            source=source_name,
            method="hwpx_xml",
            text=text,
            status="success",
            warnings=warnings,
        )

    if gemini is not None:
        image_texts = await _ocr_hwpx_images(path, gemini=gemini, source_name=source_name, budget=budget, source_id=source_id)
        combined = "\n\n".join(item.text for item in image_texts if item.text.strip())
        if combined.strip():
            return ExtractedText(
                source=source_name,
                method="hwpx_bindata_gemini_ocr",
                text=combined,
                status="success",
                warnings=warnings + ["HWPX XML text was empty; BinData OCR was used."],
            )

    return ExtractedText(
        source=source_name,
        method="hwpx_xml",
        text=text,
        status="empty_or_unreadable",
        warnings=warnings + ["No enough text found in HWPX XML or BinData OCR."],
    )


def _extract_hwpx_structured_text(path: Path) -> str:
    validate_zip_limits(path)
    with zipfile.ZipFile(path) as archive:
        section_names = sorted(
            name for name in archive.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        paragraphs: list[str] = []
        for name in section_names:
            root = ElementTree.fromstring(archive.read(name))
            for paragraph in _iter_by_local_name(root, "p"):
                texts = [
                    node.text or ""
                    for node in paragraph.iter()
                    if _local_name(node.tag) == "t" and node.text
                ]
                line = _clean_inline("".join(texts))
                if line:
                    paragraphs.append(line)
        return "\n".join(paragraphs)


async def _ocr_hwpx_images(
    path: Path,
    *,
    gemini: GeminiDocumentExtractor,
    source_name: str,
    budget: ExtractionBudget | None,
    source_id: str,
    limit: int = 3,
) -> list[ExtractedText]:
    results: list[ExtractedText] = []
    validate_zip_limits(path)
    with zipfile.ZipFile(path) as archive:
        image_names = [
            name for name in archive.namelist()
            if name.startswith("BinData/") and Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
        ][:limit]
        temp_dir = path.parent / f"{path.stem}-hwpx-images"
        temp_dir.mkdir(exist_ok=True)
        for name in image_names:
            image_path = temp_dir / Path(name).name
            image_path.write_bytes(archive.read(name))
            results.append(
                await extract_image_text(
                    image_path,
                    source_name=f"{source_name}:{name}",
                    gemini=gemini,
                    budget=budget,
                    source_id=f"{source_id}:{name}",
                )
            )
    return results


def _read_optional_text(archive: zipfile.ZipFile, name: str) -> str:
    if name not in archive.namelist():
        return ""
    raw = archive.read(name)
    for encoding in ("utf-8", "utf-16", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _iter_by_local_name(root: ElementTree.Element, local_name: str):
    for item in root.iter():
        if _local_name(item.tag) == local_name:
            yield item


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_inline(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_text(value: str) -> str:
    return "\n".join(_clean_inline(line) for line in value.splitlines() if _clean_inline(line))
