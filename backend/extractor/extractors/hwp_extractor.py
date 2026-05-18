from __future__ import annotations

import shutil
import subprocess
import re
import zlib
from pathlib import Path

from extractor.models import ExtractedText
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor


async def extract_hwp_text(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor | None,
    work_dir: Path,
    min_text_chars: int = 40,
) -> ExtractedText:
    warnings: list[str] = []

    body_text = _try_hwp_ole_bodytext(path, warnings)
    filtered_body_text = _clean_hwp_text(body_text, aggressive=True)
    if _quality_ok(filtered_body_text, min_text_chars=min_text_chars):
        return ExtractedText(
            source=source_name,
            method="hwp_ole_bodytext_filtered",
            text=filtered_body_text,
            status="success",
            warnings=warnings,
            metadata={
                "quality": _text_quality(filtered_body_text),
                "cleanup": _cleanup_stats(body_text, filtered_body_text),
            },
        )

    prv_text = _try_hwp_prv_text(path, warnings)
    if _quality_ok(prv_text, min_text_chars=min_text_chars):
        return ExtractedText(
            source=source_name,
            method="hwp_prv_text",
            text=prv_text,
            status="success",
            warnings=warnings + ["hwp_preview_text_may_be_truncated"],
            metadata={"quality": _text_quality(prv_text), "is_preview_text_only": True},
        )

    warnings.append("hwplib_py_disabled_broken_dependency")

    text = _try_hwp5txt(path, warnings)
    if _quality_ok(text, min_text_chars=min_text_chars):
        return ExtractedText(
            source=source_name,
            method="hwp5txt",
            text=text,
            status="success",
            warnings=warnings,
            metadata={"quality": _text_quality(text)},
        )
    if text.strip():
        warnings.append("hwp5txt_low_quality")

    warnings.append("libreoffice_fallback_disabled_after_validation")

    status = "unsupported_hwp_parse_failed"
    if any("encrypted" in item.lower() or "distribution" in item.lower() for item in warnings):
        status = "unsupported_hwp_protected"
    return ExtractedText(source=source_name, method="hwp_fallbacks", text="", status=status, warnings=warnings)


def _try_hwp_ole_bodytext(path: Path, warnings: list[str]) -> str:
    try:
        import olefile

        with olefile.OleFileIO(str(path)) as ole:
            if not ole.exists("FileHeader"):
                warnings.append("hwp_ole_bodytext_failed: FileHeader stream not found")
                return ""
            header = ole.openstream("FileHeader").read()
            flags = _hwp_header_flags(header)
            if flags["password"] or flags["drm"]:
                warnings.append(
                    "hwp_ole_bodytext_failed: protected document "
                    f"password={flags['password']} drm={flags['drm']}"
                )
                return ""
            if flags["distribution"]:
                warnings.append("hwp_distribution_document")

            texts: list[str] = []
            for storage_name in _hwp_text_storages(flags):
                section_names = _section_names(ole, storage_name)
                if not section_names:
                    continue
                storage_texts: list[str] = []
                for section_name in section_names:
                    try:
                        data = ole.openstream(section_name).read()
                        if flags["compressed"]:
                            data = zlib.decompress(data, -15)
                        storage_texts.extend(_extract_para_text_records(data))
                    except Exception as exc:  # noqa: BLE001 - continue with other sections/storages.
                        warnings.append(f"hwp_ole_section_failed: {section_name}: {type(exc).__name__}: {exc}")
                if storage_texts:
                    warnings.append(f"hwp_ole_storage_used: {storage_name}")
                    texts.extend(storage_texts)
        return _clean_hwp_text("\n".join(texts), aggressive=False)
    except Exception as exc:
        warnings.append(f"hwp_ole_bodytext_failed: {type(exc).__name__}: {exc}")
        return ""


def _try_hwp_prv_text(path: Path, warnings: list[str]) -> str:
    try:
        import olefile

        with olefile.OleFileIO(str(path)) as ole:
            for stream_name in ("PrvText", "Preview/PrvText"):
                if not ole.exists(stream_name):
                    continue
                raw = ole.openstream(stream_name).read()
                return _clean_hwp_text(_decode_best(raw), aggressive=True)
    except Exception as exc:
        warnings.append(f"hwp_prv_text_failed: {type(exc).__name__}: {exc}")
    return ""


def _extract_para_text_records(data: bytes) -> list[str]:
    paragraphs: list[str] = []
    offset = 0
    while offset + 4 <= len(data):
        header = int.from_bytes(data[offset:offset + 4], "little")
        offset += 4
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if offset + 4 > len(data):
                break
            size = int.from_bytes(data[offset:offset + 4], "little")
            offset += 4
        body = data[offset:offset + size]
        offset += size
        if tag_id == 67:
            text = _decode_para_text_body(body)
            if text.strip():
                paragraphs.append(text)
    return paragraphs


def _hwp_header_flags(header: bytes) -> dict[str, bool]:
    properties = int.from_bytes(header[36:40], "little") if len(header) >= 40 else 0
    return {
        "compressed": bool(properties & 0b1),
        "password": bool(properties & 0b10),
        "distribution": bool(properties & 0b100),
        "script": bool(properties & 0b1000),
        "drm": bool(properties & 0b10000),
    }


def _hwp_text_storages(flags: dict[str, bool]) -> tuple[str, ...]:
    if flags["distribution"]:
        return ("ViewText", "BodyText")
    return ("BodyText", "ViewText")


def _section_names(ole: object, storage_name: str) -> list[str]:
    return sorted(
        "/".join(item)
        for item in ole.listdir(streams=True, storages=False)
        if len(item) == 2 and item[0] == storage_name and item[1].startswith("Section")
    )


def _decode_para_text_body(body: bytes) -> str:
    chars: list[str] = []
    offset = 0
    while offset + 2 <= len(body):
        code = int.from_bytes(body[offset:offset + 2], "little")
        offset += 2
        if code == 0:
            continue
        if code in {0x0A, 0x0D}:
            chars.append("\n")
            continue
        if code == 0x09:
            chars.append("\t")
            offset = min(len(body), offset + 6)
            continue
        if _is_hwp_extended_control_code(code):
            chars.append(" ")
            offset = min(len(body), offset + 6)
            continue
        chars.append(chr(code))
    return "".join(chars)


def _is_hwp_extended_control_code(code: int) -> bool:
    return 0x01 <= code <= 0x08 or 0x0B <= code <= 0x12 or 0x14 <= code <= 0x1F


def _decode_best(data: bytes) -> str:
    best = ""
    for encoding in ("utf-16le", "utf-8", "cp949", "euc-kr"):
        text = data.decode(encoding, errors="ignore")
        if _text_quality(text)["score"] > _text_quality(best)["score"]:
            best = text
    return best


def _clean_hwp_text(value: str, *, aggressive: bool) -> str:
    # PrvText fallback can still leak CJK-looking decoder noise even after PARA_TEXT cleanup.
    value = re.sub(r"[\u4e00-\u9fff╣ॣ]", " ", value)
    value = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", value)
    lines: list[str] = []
    for raw_line in value.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if aggressive and _looks_like_control_noise(line):
            continue
        lines.append(line)
    return "\n".join(line for line in lines if line)


def _looks_like_control_noise(line: str) -> bool:
    hangul = len(re.findall(r"[가-힣]", line))
    cjk = sum(1 for char in line if "\u4e00" <= char <= "\u9fff" and not ("가" <= char <= "힣"))
    if hangul == 0 and len(line) <= 8:
        return True
    return hangul == 0 and cjk >= max(2, len(line) // 2)


def _quality_ok(text: str, *, min_text_chars: int) -> bool:
    quality = _text_quality(text)
    return (
        quality["chars"] >= min_text_chars
        and quality["hangul"] >= 20
        and quality["score"] > 50
    )


def _text_quality(text: str) -> dict[str, float]:
    stripped = text.strip()
    chars = len(stripped)
    hangul = len(re.findall(r"[가-힣]", stripped))
    lines = len([line for line in stripped.splitlines() if line.strip()])
    cjk_garbage = sum(
        1
        for char in stripped
        if "\u4e00" <= char <= "\u9fff" and not ("가" <= char <= "힣")
    )
    keywords = sum(
        stripped.count(keyword)
        for keyword in ("가정통신문", "학부모", "안내", "학교", "신청", "일시", "대상", "기간", "검사", "교육")
    )
    score = hangul * 2 + chars * 0.08 + keywords * 20 + min(lines, 30) * 3 - cjk_garbage * 3
    return {
        "chars": chars,
        "hangul": hangul,
        "lines": lines,
        "cjk_garbage": cjk_garbage,
        "keywords": keywords,
        "score": round(score, 2),
    }


def _cleanup_stats(before: str, after: str) -> dict[str, float]:
    before_quality = _text_quality(before)
    after_quality = _text_quality(after)
    return {
        "chars_before": before_quality["chars"],
        "chars_after": after_quality["chars"],
        "cjk_garbage_before": before_quality["cjk_garbage"],
        "cjk_garbage_after": after_quality["cjk_garbage"],
        "chars_dropped": max(0, before_quality["chars"] - after_quality["chars"]),
    }


def _try_hwp5txt(path: Path, warnings: list[str]) -> str:
    command = shutil.which("hwp5txt")
    candidates: list[list[str]] = []
    if command:
        candidates.append([command, str(path)])
    candidates.append(["python", "-m", "hwp5.hwp5txt", str(path)])

    for candidate in candidates:
        try:
            completed = subprocess.run(
                candidate,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                return completed.stdout
            warnings.append(
                f"hwp5txt_failed: command={' '.join(candidate)} "
                f"returncode={completed.returncode} stderr={completed.stderr.strip()[:300]}"
            )
        except Exception as exc:
            warnings.append(f"hwp5txt_failed: command={' '.join(candidate)} {type(exc).__name__}: {exc}")
    return ""
