from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from extractor.archive_security import validate_zip_limits
from extractor.budget import ExtractionBudget
from extractor.markdown_tables import collapse_layout_tables, fix_table_structure
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
    blocks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        section_names = sorted(
            name for name in archive.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        for name in section_names:
            root = ElementTree.fromstring(archive.read(name))
            # 본문 <p> 는 텍스트로, <tbl> 은 markdown 표(| |)로 뽑는다.
            # - 표를 평문으로 뭉개지 않으므로 정제 단계의 '표 마스킹'이 표를 보호 → LLM 의 셀 값 변조 차단.
            # - 표 셀 안 <p> 중첩에 의한 본문 2~3중 중복도 'tbl 조상이 있으면 본문 <p> 로 안 잡는다'로 자동 방지.
            parents = {child: parent for parent in root.iter() for child in parent}
            for element in root.iter():
                local = _local_name(element.tag)
                if local == "p" and not _nearest_is_table(element, parents):
                    text = _paragraph_text(element)
                    if text:
                        blocks.append(text)
                elif local == "tbl" and not _nearest_is_table(element, parents):
                    table_md = _table_to_markdown(element)
                    if table_md:
                        blocks.append(table_md)
    md = "\n".join(blocks)
    return fix_table_structure(collapse_layout_tables(md))


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


def _nearest_is_table(element: ElementTree.Element, parents: dict) -> bool:
    """element 의 조상 중 <tbl> 이 있으면 True (표 셀 내부 요소 판별)."""
    ancestor = parents.get(element)
    while ancestor is not None:
        if _local_name(ancestor.tag) == "tbl":
            return True
        ancestor = parents.get(ancestor)
    return False


def _paragraph_text(element: ElementTree.Element, *, stop_at_table: bool = True) -> str:
    """element 하위 <t> 텍스트를 모아 한 줄로. stop_at_table 이면 중첩 표 안 텍스트는 제외."""
    parts: list[str] = []

    def walk(node: ElementTree.Element) -> None:
        for child in node:
            local = _local_name(child.tag)
            if local == "tbl" and stop_at_table:
                continue
            if local == "t" and child.text:
                parts.append(child.text)
            walk(child)

    walk(element)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _table_to_markdown(table: ElementTree.Element) -> str:
    """<tbl> 을 markdown 표로. 첫 행을 헤더로 두고 행마다 열 수를 맞춘다."""
    rows: list[list[str]] = []

    def find_rows(node: ElementTree.Element) -> None:
        for child in node:
            if _local_name(child.tag) == "tr":
                rows.append(
                    [_paragraph_text(cell, stop_at_table=False) for cell in child if _local_name(cell.tag) == "tc"]
                )
            else:
                find_rows(child)

    find_rows(table)
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""
    ncols = max(len(row) for row in rows)
    rows = [row + [""] * (ncols - len(row)) for row in rows]
    md = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * ncols]
    for row in rows[1:]:
        md.append("| " + " | ".join(row) + " |")
    return "\n".join(md)
