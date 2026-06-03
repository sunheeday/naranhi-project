from __future__ import annotations

import html
import shutil
import subprocess
import re
import sys
import tempfile
import zlib
from pathlib import Path

from extractor.markdown_tables import collapse_layout_tables, fix_table_structure
from extractor.models import ExtractedText
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor
from extractor.extractors.image_gemini_extractor import extract_image_text


_URL_RE = re.compile(r"(?:https?://|www\.)[A-Za-z0-9./:_?=&%#@~+\-]+")


async def extract_hwp_text(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor | None,
    work_dir: Path,
) -> ExtractedText:
    warnings: list[str] = []

    markdown = _hwp_to_markdown(path, warnings)
    if len(markdown.strip()) >= 40:  # hwp5html 로 표 구조·앞글자 보존 성공
        return ExtractedText(
            source=source_name,
            method="hwp5html_markdown",
            text=_append_hwp_hyperlinks(markdown, path),
            status="success",
            warnings=warnings,
            metadata={"quality": _text_quality(markdown)},
        )

    body_text = _try_hwp_ole_bodytext(path, warnings)
    filtered_body_text = _clean_hwp_text(body_text, aggressive=True)
    if filtered_body_text.strip():
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

    warnings.append("hwplib_py_disabled_broken_dependency")

    text = _try_hwp5txt(path, warnings)
    if text.strip():
        return ExtractedText(
            source=source_name,
            method="hwp5txt",
            text=text,
            status="success",
            warnings=warnings,
            metadata={"quality": _text_quality(text)},
        )

    warnings.append("libreoffice_fallback_disabled_after_validation")

    if gemini is not None:
        image_texts = await _ocr_hwp_bindata_images(
            path, gemini=gemini, source_name=source_name, work_dir=work_dir
        )
        combined = "\n\n".join(t.text for t in image_texts if t.text.strip())
        if combined.strip():
            return ExtractedText(
                source=source_name,
                method="hwp_bindata_gemini_ocr",
                text=combined,
                status="success",
                warnings=warnings + ["HWP text extraction failed; BinData OCR was used."],
            )

    status = "unsupported_hwp_parse_failed"
    if any("encrypted" in item.lower() or "distribution" in item.lower() for item in warnings):
        status = "unsupported_hwp_protected"
    return ExtractedText(source=source_name, method="hwp_fallbacks", text="", status=status, warnings=warnings)


def _hwp_to_markdown(path: Path, warnings: list[str]) -> str:
    """hwp5html -> markdownify 로 표 구조·앞글자를 보존해 markdown 추출.

    기존 OLE 바이너리 추출은 표를 평문으로 뭉개고 앞글자를 흘리므로(2026->026), 표(| |)와
    글자를 보존하는 hwp5html 경로를 우선 시도한다. hwp5html/markdownify 미설치 환경에선 빈
    문자열을 돌려 호출부가 기존 체인(OLE/hwp5txt/BinData OCR)으로 폴백하게 한다.
    """
    command = _hwp5html_command()
    if command is None:
        return ""
    try:
        import markdownify  # lazy import: 미설치 환경에선 이 경로만 건너뛰고 폴백
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"hwp5html_skip_no_markdownify: {type(exc).__name__}")
        return ""
    temp_dir = Path(tempfile.mkdtemp(prefix="hwp5html-"))
    try:
        completed = subprocess.run(
            [*command, "--output", str(temp_dir), str(path)],
            capture_output=True,
            timeout=90,
        )
        xhtml = temp_dir / "index.xhtml"
        if not xhtml.exists():
            warnings.append(
                f"hwp5html_failed: returncode={completed.returncode} "
                f"stderr={completed.stderr.decode('utf-8', 'replace').strip()[:200]}"
            )
            return ""
        xhtml_text = _unwrap_nested_tables(xhtml.read_text(encoding="utf-8", errors="replace"))
        xhtml_text = _expand_table_spans(xhtml_text)  # 병합셀(rowspan/colspan)을 격자로 펼쳐 표 보존
        md = markdownify.markdownify(xhtml_text, heading_style="ATX")
        md = re.sub(r"(?m)^\s*xml version=.*$", "", md)   # xhtml 선언 leak 제거
        md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)       # 이미지 markdown junk 제거
        md = re.sub(r"[ \t]+\n", "\n", md)
        md = re.sub(r"\n{3,}", "\n\n", md)
        return fix_table_structure(collapse_layout_tables(md.strip())).strip()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"hwp5html_failed: {type(exc).__name__}: {exc}")
        return ""


def _unwrap_nested_tables(xhtml: str) -> str:
    """레이아웃용 래퍼 표(셀 안에 또 다른 표가 든 바깥 표)를 펼쳐 안쪽 진짜 표를 최상위로 끌어올린다.

    HWP 가정통신문은 문서 전체를 표 한 칸에 담는 '표 레이아웃'이 흔하다. 이때 markdown 은 표
    중첩을 표현하지 못해 안쪽 데이터표가 한 셀 안에서 `| --- |` 로 직선화돼 깨진다(파이프 떡칠).
    markdownify 전에 바깥 래퍼 표를 풀면 안쪽 표가 최상위 markdown 표로 깔끔히 변환된다.
    bs4 미설치/파싱 실패 시 원본을 그대로 돌려 기존 동작을 유지한다(폴백 안전).
    """
    try:
        from bs4 import BeautifulSoup  # markdownify 의 의존성이라 동일 환경에 존재
    except Exception:  # noqa: BLE001 - bs4 없으면 펼치기만 건너뛴다.
        return xhtml
    try:
        soup = BeautifulSoup(xhtml, "html.parser")
    except Exception:  # noqa: BLE001
        return xhtml

    for _ in range(20):  # 다중 중첩 대비 안전 상한(무한루프 방지)
        outer = next(
            (table for table in soup.find_all("table") if table.find("table") is not None),
            None,
        )
        if outer is None:
            break
        # 바깥 표의 '자기' 행·셀만 고른다(안쪽 표의 행·셀은 가장 가까운 table 조상이 달라 제외).
        own_rows = [tr for tr in outer.find_all("tr") if tr.find_parent("table") is outer]
        blocks = []
        for row in own_rows:
            for cell in [c for c in row.find_all(["td", "th"]) if c.find_parent("table") is outer]:
                div = soup.new_tag("div")
                for child in list(cell.children):
                    div.append(child.extract())  # 안쪽 표째로 div 안으로 이동(한 단계 위로)
                blocks.append(div)
        if blocks:
            outer.replace_with(*blocks)
        else:
            outer.decompose()
    return str(soup)


def _cell_span(cell: object, name: str) -> int:
    try:
        return max(1, int(cell.get(name, 1) or 1))  # type: ignore[attr-defined]
    except (TypeError, ValueError):
        return 1


def _pending_at_or_after(pending: dict[int, int], col: int) -> bool:
    return any(c >= col and rem > 0 for c, rem in pending.items())


def _expand_one_table(soup: object, table: object) -> None:
    """한 표의 rowspan/colspan 을 펼쳐 직사각형 격자 <table> 로 교체한다(병합 없으면 그대로)."""
    rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]  # type: ignore[attr-defined]
    if not rows:
        return
    grid: list[list[str]] = []
    pending: dict[int, int] = {}  # col -> 아래로 남은 rowspan 행수(빈칸으로 채움)
    has_span = False
    for tr in rows:
        cells = [c for c in tr.find_all(["td", "th"]) if c.find_parent("table") is table]
        row: list[str] = []
        col = ci = 0
        while ci < len(cells) or _pending_at_or_after(pending, col):
            if len(row) > 80:  # 병적 구조 무한루프 안전 상한
                break
            if pending.get(col, 0) > 0:  # 위 행 rowspan 이 이 칸을 차지 → 빈칸
                row.append("")
                pending[col] -= 1
                col += 1
                continue
            if ci < len(cells):
                cell = cells[ci]
                ci += 1
                text = " ".join(cell.get_text(" ", strip=True).split())
                cs = _cell_span(cell, "colspan")
                rs = _cell_span(cell, "rowspan")
                if cs > 1 or rs > 1:
                    has_span = True
                for k in range(cs):  # colspan: 첫 칸에만 값, 나머지는 빈칸(값 중복·창작 없음)
                    row.append(text if k == 0 else "")
                    if rs > 1:
                        pending[col] = rs - 1
                    col += 1
                continue
            row.append("")  # 셀은 끝났지만 오른쪽에 rowspan 잔여 → 빈칸 전진
            col += 1
        grid.append(row)
    if not has_span:
        return  # 병합 없는 표는 건드리지 않는다(markdownify 가 알아서 처리)
    width = max((len(r) for r in grid), default=0)
    if width < 2:
        return
    new_table = soup.new_tag("table")  # type: ignore[attr-defined]
    for ri, row in enumerate(grid):
        tr_tag = soup.new_tag("tr")  # type: ignore[attr-defined]
        for k in range(width):
            text = row[k] if k < len(row) else ""
            cell_tag = soup.new_tag("th" if ri == 0 else "td")  # type: ignore[attr-defined]
            if text:
                cell_tag.string = text
            tr_tag.append(cell_tag)
        new_table.append(tr_tag)
    table.replace_with(new_table)  # type: ignore[attr-defined]


def _expand_table_spans(xhtml: str) -> str:
    """표의 병합셀(rowspan/colspan)을 펼쳐 직사각형 격자로 만든다(markdownify 전 단계).

    HWP 표는 셀 병합이 흔한데 markdownify 는 이를 못 그려 표가 평문으로 뭉개진다(평촌중
    '출석인정결석'). 병합을 미리 빈 셀로 펼쳐 완전한 격자를 만들면 깔끔한 markdown 표가 된다.
    값은 첫 칸에만 두고 펼친 칸은 빈칸 → 내용 중복·창작 없이 충실 보존.
    bs4 미설치/파싱 실패 시 원본 그대로(폴백 안전).
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:  # noqa: BLE001 - bs4 없으면 펼치기만 건너뛴다.
        return xhtml
    try:
        soup = BeautifulSoup(xhtml, "html.parser")
    except Exception:  # noqa: BLE001
        return xhtml
    for table in soup.find_all("table"):
        try:
            _expand_one_table(soup, table)
        except Exception:  # noqa: BLE001 - 한 표 실패가 전체 변환을 막지 않게.
            continue
    return str(soup)


def _hwp5html_command() -> list[str] | None:
    """hwp5html 콘솔 스크립트 경로. (python -m hwp5.hwp5html 은 파일을 생성하지 않아 사용 불가.)"""
    found = shutil.which("hwp5html")
    if found:
        return [found]
    # pip 는 python 실행파일 옆 Scripts/bin 에 콘솔 스크립트를 설치한다.
    bin_dir = Path(sys.executable).parent
    for name in ("hwp5html.exe", "hwp5html"):
        candidate = bin_dir / name
        if candidate.exists():
            return [str(candidate)]
    return None


def _hwp_link_urls(path: Path) -> list[str]:
    """hwp5proc xml 에서 하이퍼링크 URL 추출 (PARA_TEXT 가 놓치는 링크 보강)."""
    found = shutil.which("hwp5proc")
    if found:
        command = [found]
    else:
        bin_dir = Path(sys.executable).parent
        candidate = next(
            (bin_dir / n for n in ("hwp5proc.exe", "hwp5proc") if (bin_dir / n).exists()), None
        )
        if candidate is None:
            return []
        command = [str(candidate)]
    try:
        completed = subprocess.run([*command, "xml", str(path)], capture_output=True, timeout=60)
        xml = html.unescape(completed.stdout.decode("utf-8", "replace"))
        urls: list[str] = []
        for match in _URL_RE.finditer(xml):
            url = re.split(r"HWP[A-Z_]{4,}", match.group(0))[0].rstrip(".,)】] ")
            if len(url) > 8 and url not in urls:
                urls.append(url)
        return urls
    except Exception:  # noqa: BLE001
        return []


def _append_hwp_hyperlinks(markdown: str, path: Path) -> str:
    missing = [url for url in _hwp_link_urls(path) if url not in markdown]
    if missing:
        markdown += "\n\n" + "\n".join(f"[관련링크] {url}" for url in missing)
    return markdown


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


def _clean_hwp_text(value: str, *, aggressive: bool) -> str:
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


async def _ocr_hwp_bindata_images(
    path: Path,
    *,
    gemini: GeminiDocumentExtractor,
    source_name: str,
    work_dir: Path,
    limit: int = 3,
) -> list[ExtractedText]:
    results: list[ExtractedText] = []
    try:
        import olefile

        _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}
        with olefile.OleFileIO(str(path)) as ole:
            bin_streams = [
                item for item in ole.listdir(streams=True, storages=False)
                if len(item) == 2 and item[0] == "BinData"
                and Path(item[1]).suffix.lower() in _IMAGE_EXTENSIONS
            ][:limit]

            if not bin_streams:
                return results

            temp_dir = work_dir / f"{path.stem}-hwp-images"
            temp_dir.mkdir(exist_ok=True)
            for item in bin_streams:
                name = item[1]
                image_path = temp_dir / name
                image_path.write_bytes(ole.openstream(item).read())
                results.append(
                    await extract_image_text(
                        image_path,
                        source_name=f"{source_name}:{name}",
                        gemini=gemini,
                        budget=None,
                        source_id=f":{name}",
                    )
                )
    except Exception:
        pass
    return results


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
