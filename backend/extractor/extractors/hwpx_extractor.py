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
            # 각 <t> 를 '가장 가까운 <p> 조상'으로 묶되, 문서 순서대로 끊어 한 줄씩 만든다.
            # - 표 셀처럼 <p> 안에 <p> 가 중첩돼도 각 <t> 는 가장 안쪽 <p> 한 곳에만 귀속되어,
            #   바깥 문단이 안쪽 셀 텍스트까지 끌어와 2~3중 중복되던 버그가 생기지 않는다.
            # - 같은 바깥 문단이 표를 사이에 두고 앞/뒤로 나뉘어도 문서 순서대로 별도 줄로 끊어,
            #   '앞+뒤'가 한 줄로 붙고 표가 뒤로 밀리는 순서 꼬임을 막는다.
            # - <p> 조상이 없는 <t>(비표준/제어 텍스트)는 예전처럼 버린다.
            parents = {child: parent for parent in root.iter() for child in parent}
            lines: list[list[str]] = []
            current_p: ElementTree.Element | None = None
            for node in root.iter():
                if _local_name(node.tag) != "t" or not node.text:
                    continue
                nearest_p = None
                ancestor = parents.get(node)
                while ancestor is not None:
                    if _local_name(ancestor.tag) == "p":
                        nearest_p = ancestor
                        break
                    ancestor = parents.get(ancestor)
                if nearest_p is None:
                    continue
                if nearest_p is not current_p:
                    lines.append([])
                    current_p = nearest_p
                lines[-1].append(node.text)
            for texts in lines:
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


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_inline(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
