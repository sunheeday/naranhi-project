"""markdown 표 후처리 — HWP/HWPX 추출이 만든 표를 다듬는다(공용).

- collapse_layout_tables: 배너/레이아웃용 표(실열 ≤2 또는 빈칸 다수)는 평문으로 풀고 진짜 데이터 표는 유지.
- fix_table_structure: 빈 선두행 제거 + 첫 실내용행을 헤더로 승격 + 구분선 재배치.
(hwp5html/markdownify 나 HWPX XML 파서가 병합헤더를 빈 행으로 만들어 헤더가 데이터행으로 밀리는 문제 보정.)
"""
from __future__ import annotations

import re


_SEP_RE = re.compile(r"^\s*\|[-\s|:]+\|\s*$")


def is_separator(line: str) -> bool:
    return bool(_SEP_RE.match(line)) and "-" in line


def is_empty_row(line: str) -> bool:
    return not any(cell.strip() for cell in line.strip().strip("|").split("|"))


def collapse_layout_tables(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            block = lines[i:j]
            data_rows = [ln for ln in block if not is_separator(ln)]
            maxcols = total = empty = 0
            for ln in data_rows:
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                maxcols = max(maxcols, len([c for c in cells if c]))
                total += len(cells)
                empty += len([c for c in cells if not c])
            empty_ratio = empty / max(total, 1)
            if maxcols <= 2 and (empty_ratio >= 0.4 or maxcols <= 1):
                for ln in data_rows:
                    cells = [c.strip() for c in ln.strip().strip("|").split("|") if c.strip()]
                    if cells:
                        out.append(" ".join(cells))
                out.append("")
            else:
                out.extend(block)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def fix_table_structure(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            block = lines[i:j]
            sep_idx = next((k for k, ln in enumerate(block) if is_separator(ln)), None)
            if sep_idx is not None:
                rows = [ln for k, ln in enumerate(block) if k != sep_idx]
                while rows and is_empty_row(rows[0]):
                    rows.pop(0)
                if rows:
                    ncol = max(1, rows[0].count("|") - 1)
                    block = [rows[0], "|" + " --- |" * ncol] + rows[1:]
                else:
                    block = []
            out.extend(block)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)
