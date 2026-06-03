"""품질게이트: 정제 결과(original_text 용 본문)가 '사용자에게 보여줄 만한가' 자동 판정.

needs_file=True 이면 앱은 본문 대신 "📎 원본 파일을 직접 확인하세요"를 띄운다(요약 카드는 유지).
복잡 행정양식·콜라주 포스터처럼 정제해도 구조가 죽은 세로 덤프가 되는 문서를 걸러,
깨진 텍스트를 억지로 보여주는 대신 우아하게 파일로 넘긴다(graceful degradation).

판정은 '실제로 못 읽는' 신호로만 한다(하나라도 걸리면 needs_file):
  ① 평탄화      제목(#)·표 없고 짧은 파편 줄이 FRAG_RATIO_TH 초과 (= 세로 덤프)
  ② 중첩표 깨짐  콘텐츠 행 안에 구분선(| --- |)이 끼어 표가 직선화됨
  ③ 저품질      extractor.quality.is_low_quality_text (빈문서/거의 한글 없음)
주의: 'FALLBACK'(LLM 정제 실패)·'동일셀 반복'은 사유가 아니다(신호로만 기록). 폴백이라도 내용이
멀쩡하면(사진 OCR) 그대로 보여주고, 같은 셀 반복도 정상('자습 자습 자습 자습')일 때가 많아서다.

(파일럿 backend/outputs/quality_gate.py 의 검증된 assess 로직을 프로덕션 모듈로 포팅.)
"""
from __future__ import annotations

import re
from typing import Any

from extractor.quality import is_low_quality_text


_SEP_RE = re.compile(r"^\s*\|[-\s|:]+\|\s*$")
_SENT_END = (".", "!", "?", ":", ")", "）", "」", "』", "]")
_BULLETS = ("#", "-", "|", "*", "※", "☎", "○", "•", "□", ">")
# 같은 셀 텍스트가 4번 이상 연달아 반복되는 깨진 표(와이드 빈표/반복 헤더)
_REPEAT_RE = re.compile(r"(\|[^|\n]*[가-힣A-Za-z0-9]{2,}[^|\n]*)\1{3,}")
# 콘텐츠 행 안에 끼인 구분선(`| --- |`) = 중첩표가 markdown 한 셀로 직선화된 흔적(표 레이아웃 HWP)
_INLINE_SEP_RE = re.compile(r"\|\s*:?-{3,}:?\s*\|")
FRAG_RATIO_TH = 0.40  # 파편 줄 비율 임계 (평탄화 덤프 판정)


def _is_sep(line: str) -> bool:
    return bool(_SEP_RE.match(line)) and "-" in line


def _has_nested_table_soup(md: str) -> bool:
    """표(`|`) 행인데 자체 구분선이 아닌 줄에 `| --- |` 가 끼어 있으면 중첩표 직선화(깨짐)로 본다.

    표 레이아웃 HWP 는 바깥 표 안에 진짜 표가 중첩되는데, markdown 은 표 중첩을 못 그려
    안쪽 표가 한 셀 안에서 `| --- |` 로 직선화된다. 그 깨진 흔적을 잡아 원본 파일로 우회시킨다.
    (추출 단계의 _unwrap_nested_tables 가 대부분 막지만, 못 막은 잔여를 여기서 안전망으로 거른다.)
    """
    for line in md.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and not _is_sep(line) and _INLINE_SEP_RE.search(stripped):
            return True
    return False


def _table_cell_empty_ratio(md: str) -> float:
    """표 셀 빈칸 비율(참고용 신호 — 빈 양식 오탐이 있어 needs_file 판정엔 미사용)."""
    total = empty = 0
    for line in md.split("\n"):
        if line.lstrip().startswith("|") and not _is_sep(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            total += len(cells)
            empty += sum(1 for c in cells if not c)
    return (empty / total) if total else 0.0


def assess(md: str, tag: str) -> dict[str, Any]:
    """정제본(md)과 처리 tag 로 needs_file 판정. {needs_file, reasons, signals} 반환."""
    lines = [line for line in md.split("\n") if line.strip()]
    n = max(len(lines), 1)
    headings = sum(1 for line in lines if line.lstrip().startswith("#"))
    real_tables = sum(1 for line in md.split("\n") if _is_sep(line))
    frags = sum(
        1
        for line in lines
        if len(line.strip()) < 12
        and not line.lstrip().startswith(_BULLETS)
        and not line.strip().endswith(_SENT_END)
    )
    frag_ratio = round(frags / n, 3)
    empty_ratio = round(_table_cell_empty_ratio(md), 3)
    repeat_junk = bool(_REPEAT_RE.search(md))
    nested_table = _has_nested_table_soup(md)
    low = bool(is_low_quality_text(md))

    # 주의: 'FALLBACK'(LLM 정제 실패)·'동일셀 반복' 자체는 needs_file 사유가 아니다.
    #  - 폴백이라도 내용이 멀쩡(예: 사진 OCR)할 수 있고,
    #  - 같은 셀 반복도 정상일 때가 많다(시험일정의 '자습 자습 자습 자습' 등).
    # 그래서 '실제로 못 읽는' 신호 — 평탄화(세로덤프)·중첩표 직선화·저품질 — 으로만 판정한다.
    reasons: list[str] = []
    if headings == 0 and real_tables == 0 and frag_ratio > FRAG_RATIO_TH:
        reasons.append(f"평탄화(제목0·표0·파편{int(frag_ratio * 100)}%)")
    if nested_table:
        reasons.append("표 중첩 깨짐")
    if low:
        reasons.append("빈문서/저품질")

    return {
        "needs_file": bool(reasons),
        "reasons": reasons,
        "signals": {
            "fallback": tag == "FALLBACK",
            "tag": tag,
            "headings": headings,
            "tables": real_tables,
            "fragment_ratio": frag_ratio,
            "table_empty_ratio": empty_ratio,
            "repeat_junk": repeat_junk,
            "nested_table": nested_table,
            "low_quality": low,
            "chars": len(md),
        },
    }


def empty_gate(tag: str = "unknown") -> dict[str, Any]:
    """정제를 건너뛰거나 판정 불가일 때의 기본값(needs_file=False)."""
    return {"needs_file": False, "reasons": [], "signals": {"tag": tag}}
