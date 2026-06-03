"""공지 요약(summary) 생성 — 구조화 형식(제목 + 핵심 항목).

정제된 소스(본문 + 첨부)를 받아 '이 공지가 무엇인지'를 **줄글이 아니라 구조화**로 만든다:
  제목(한 줄) + 핵심 항목들(label: value, 키워드 형식) — 날짜·참가비·대상·신청방법 등.

JSON {title, points:[{label, value}]} 로 LLM 에게 받아서, 사람이 읽는 텍스트
("제목\nlabel: value\n…")로 렌더한다(extracted_content.summary.rendered). 프론트가 이를
파싱해 제목 강조 + 항목 라벨 볼드로 보여준다.

환각 차단: 요약 속 날짜·금액이 원문(본문+첨부)에 실제 있는지 대조 → 없으면 1회 재생성 →
그래도 실패하면 제목만 남긴다. best-effort(gemini 없음/예외/빈 입력이면 제목만, raise 안 함).
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services.refinement_service import DATE_RE

_MONEY_RE = re.compile(r"\d[\d,]*\s*원")


PROMPT = """너는 학교 가정통신문을 외국인 학부모가 한눈에 파악하도록 돕는 '요약기'다.
아래 [제목]·[본문]·[첨부]를 읽고 JSON 객체 하나만 출력하라.

[출력 형식 — 오직 JSON 만. 설명·머리말·코드펜스 금지]
{
  "title": "이 공지의 핵심을 담은 짧은 제목(한 줄)",
  "points": [
    {"label": "항목 이름", "value": "간결한 내용"}
  ]
}

[규칙]
1. [구조화] 줄글로 풀어쓰지 마라. 핵심을 'label: value' 항목들로 쪼개라.
   label 예시(해당되는 것만): 프로그램 내용, 대상, 날짜, 시간, 장소, 참가비, 신청 방법, 납부 방법, 준비물, 신청 기간, 문의.
   value 는 키워드·짧은 구로(완전한 문장 X). 여러 개면 쉼표로(예: "공연관람, 한국문화체험").
2. [개수] points 는 2~6개. 원문에 없는 항목은 만들지 마라.
3. [충실] 날짜·금액·숫자는 원문에 있는 값만 그대로 써라. 불확실하면 그 항목을 빼라. 지어내지 마라.
4. [한국어] 한국어로만 쓴다.

[입력]
"""


def _strip_fence(text: str) -> str:
    out = (text or "").strip()
    out = re.sub(r"^```[a-zA-Z]*\n", "", out)
    out = re.sub(r"\n```$", "", out)
    return out.strip()


def _parse_json(text: str) -> dict[str, Any] | None:
    """LLM 출력에서 JSON 객체를 안전하게 뽑는다(코드펜스/주변 텍스트 허용)."""
    raw = _strip_fence(text)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 - 바깥 중괄호만 잘라 재시도
        i, j = raw.find("{"), raw.rfind("}")
        if i != -1 and j > i:
            try:
                data = json.loads(raw[i : j + 1])
                return data if isinstance(data, dict) else None
            except Exception:  # noqa: BLE001
                return None
    return None


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def _collect_facts(text: str) -> list[str]:
    """요약 충실도 검증용 — 날짜·금액 토큰을 추출."""
    facts = [m.group(0) for m in DATE_RE.finditer(text or "")]
    facts += [m.group(0) for m in _MONEY_RE.finditer(text or "")]
    return facts


# 날짜를 (월, 일) 쌍으로 추출 — 연도 유무·형식 차이를 흡수한다(LLM 이 연도를 덧붙이거나
# 2026.6.8 ↔ 6월 8일 처럼 형식만 달라도 같은 날로 인정).
_MD_PATTERNS = [
    re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일"),            # 6월 8일
    re.compile(r"\d{4}\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})"),    # 2026. 6. 8
    re.compile(r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*\("),       # 6. 8.(월)
]


def _md_pairs(text: str) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for pattern in _MD_PATTERNS:
        for match in pattern.finditer(text or ""):
            pairs.add((int(match.group(1)), int(match.group(2))))
    return pairs


def _hallucinated_facts(summary_text: str, source: str) -> list[str]:
    """요약 속 날짜·금액 중 원문에 없는 것 = 환각.

    - 날짜: (월, 일) 쌍이 원문에 있으면 OK. 연도 덧붙임·형식 차이는 허용(오탐 방지),
      엉뚱한 월/일만 잡는다.
    - 금액: 구분자 무시한 숫자가 원문 숫자열에 있으면 OK(금액은 정확해야 하므로 엄격).
    """
    bad: list[str] = []
    src_md = _md_pairs(source)
    for month, day in _md_pairs(summary_text):
        if (month, day) not in src_md:
            bad.append(f"{month}월 {day}일")
    src_digits = _digits(source)
    for match in _MONEY_RE.finditer(summary_text or ""):
        key = _digits(match.group(0))
        if key and key not in src_digits:
            bad.append(match.group(0))
    return bad


def _coerce(data: dict[str, Any]) -> dict[str, Any]:
    """LLM JSON 을 {title, points:[{label,value}]} 로 정규화."""
    title = str(data.get("title") or "").strip()
    raw_points = data.get("points")
    points: list[dict[str, str]] = []
    if isinstance(raw_points, list):
        for item in raw_points:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            value = str(item.get("value") or "").strip()
            if value:
                points.append({"label": label, "value": value})
    return {"title": title, "points": points}


def _minimal_summary(title: str) -> dict[str, Any]:
    """LLM 없이/실패 시의 안전 폴백 — 제목만(숫자 안 지어냄)."""
    return {"title": (title or "").strip() or "가정통신문", "points": []}


def _build_prompt(title: str, body: str, attachments: list[dict[str, Any]]) -> str:
    lines = [PROMPT, f"[제목] {title}".strip(), "", "[본문]", body.strip() or "(본문 없음)", ""]
    for idx, att in enumerate(attachments, 1):
        lines.append(f"[첨부 {idx}] {att.get('name') or ''}")
        text = str(att.get("text") or "").strip()
        lines.append(text if text else "(읽을 수 없는 자료)")
        lines.append("")
    return "\n".join(lines)


async def summarize(
    *,
    title: str,
    body: str,
    attachments: list[dict[str, Any]] | None,
    gemini: Any,
) -> tuple[dict[str, Any], int]:
    """본문 + 첨부 정제본을 구조화 요약한다.

    반환: (요약 dict {title, points:[{label,value}]}, gemini 호출수)
    """
    title = (title or "").strip()
    body = (body or "").strip()
    atts = attachments or []

    has_content = bool(body) or any(str(a.get("text") or "").strip() for a in atts)
    if gemini is None or not has_content:
        return _minimal_summary(title), 0

    source_all = "\n".join([body] + [str(a.get("text") or "") for a in atts])
    base_prompt = _build_prompt(title, body, atts)
    calls = 0

    for attempt in range(2):  # 최초 1회 + 환각 감지 시 1회 재생성
        prompt = base_prompt
        if attempt == 1:
            prompt += "\n주의: 날짜·금액은 원문에 실제로 있는 값만 쓰고, 없으면 그 항목을 빼라."
        try:
            calls += 1
            raw = await gemini.generate_text(prompt)
        except Exception:  # noqa: BLE001 - 요약 실패가 공지를 잃게 하지 않는다(폴백).
            break
        data = _parse_json(raw or "")
        if not data:
            continue
        cleaned = _coerce(data)
        if not cleaned["title"]:
            cleaned["title"] = title or "가정통신문"
        check_text = cleaned["title"] + " " + " ".join(p["value"] for p in cleaned["points"])
        if not _hallucinated_facts(check_text, source_all):
            return cleaned, calls

    # 파싱 실패 또는 환각 미해결 → 제목만(숫자 안 지어냄).
    return _minimal_summary(title), calls


def render_summary_markdown(summary: dict[str, Any] | None) -> str:
    """요약 구조 JSON → 사람이 읽는 텍스트("제목\\nlabel: value\\n…"). 번역·표시 대상.

    프론트가 이 텍스트를 파싱해 제목 강조 + 항목 라벨 볼드로 렌더한다.
    """
    if not isinstance(summary, dict):
        return ""
    lines: list[str] = []
    title = str(summary.get("title") or "").strip()
    if title:
        lines.append(title)
    for point in summary.get("points") or []:
        if not isinstance(point, dict):
            continue
        label = str(point.get("label") or "").strip()
        value = str(point.get("value") or "").strip()
        if not value:
            continue
        lines.append(f"{label}: {value}" if label else value)
    return "\n".join(lines).strip()
