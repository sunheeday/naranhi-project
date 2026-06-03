"""공지 요약(summary) 생성.

정제된 소스(본문 + 첨부)를 받아 '이 공지가 무엇인지' 자연어 요약을 만든다.
얇은 구조 JSON {body, attachments:[{source_id, name, summary}]} 로 LLM 에게 받아서
(빠짐없음 보장) 사람이 읽는 markdown 문장으로 렌더한다. 렌더 결과가 notices.original_text
에 들어가 기존 번역 파이프라인(auto + lazy)이 그대로 요약을 번역한다.

환각 차단: 요약 속 날짜·금액이 원문(본문+첨부)에 실제 있는지 대조 → 없으면 1회 재생성 →
그래도 실패하면 숫자 없는 최소 요약으로 폴백한다(지어낸 숫자는 절대 출력 안 됨).

요약 실패가 공지를 잃게 하지 않는다(best-effort): gemini 없음/예외/빈 내용이면 최소 요약을
반환하고 절대 raise 하지 않는다.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services.refinement_service import DATE_RE

# 금액(예: 30,000원) — 날짜와 함께 LLM 이 가장 자주 지어내는 값이라 검증 대상.
_MONEY_RE = re.compile(r"\d[\d,]*\s*원")
_NEEDS_FILE_SUMMARY = "표·서식이 복잡해 원본 파일에서 직접 확인해 주세요."


PROMPT = """너는 학교 가정통신문을 외국인 학부모가 한눈에 이해하도록 돕는 '요약기'다.
아래 [제목]·[본문]과 0개 이상의 [첨부]를 읽고 JSON 객체 하나만 출력하라.

[출력 형식 — 오직 JSON 만. 설명·머리말·코드펜스 금지]
{
  "body": "이 공지가 무엇인지 자연스러운 한국어 문장으로 요약(2~4문장). 누가·언제·어디서·무엇을·왜·어떻게 중 해당되는 것만 자연스럽게 녹여라.",
  "attachments": [
    {"source_id": "<주어진 값 그대로>", "name": "<주어진 값 그대로>", "summary": "이 첨부에 무슨 내용이 들었는지 1~2문장"}
  ]
}

[규칙]
1. [충실] 원문에 없는 사실·날짜·금액·숫자를 절대 지어내지 마라. 날짜·금액은 원문에 있는 값만 그대로 써라. 불확실하면 쓰지 마라.
2. [빠짐없이] 주어진 모든 [첨부]를 attachments 에 하나씩 넣고, source_id 와 name 은 주어진 값을 그대로 복사하라.
3. [자연·간결] 불릿 나열 말고 자연스러운 문장으로. 큰 표를 통째로 옮기지 말고 "무엇이 안내되었는지" 수준으로 요약하라.
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


def _hallucinated_facts(summary_text: str, source: str) -> list[str]:
    """요약 속 날짜·금액 중 원문에 없는 것 = 환각.

    날짜는 형식이 달라도(2026. 5. 21. ↔ 2026년 5월 21일) 같은 값이므로, 구분자를 무시한
    숫자 시퀀스로 비교한다(원문 숫자열의 부분열이면 OK). → 형식 차이로 인한 오탐 방지.
    """
    src_digits = _digits(source)
    bad: list[str] = []
    for fact in _collect_facts(summary_text):
        key = _digits(fact)
        if key and key not in src_digits:
            bad.append(fact)
    return bad


def _coerce(data: dict[str, Any], attachments: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM JSON 을 신뢰 가능한 구조로 정규화.

    첨부는 우리가 준 목록(source_id·name 권위값)을 기준으로 재구성하고, LLM summary 만
    source_id 로 매칭해 붙인다. → 첨부 누락/조작 없이 모든 첨부가 정확한 id·name 으로 보장됨.
    """
    body = str(data.get("body") or "").strip()
    llm_atts = data.get("attachments")
    by_id: dict[str, str] = {}
    if isinstance(llm_atts, list):
        for item in llm_atts:
            if isinstance(item, dict):
                sid = str(item.get("source_id") or "").strip()
                if sid:
                    by_id[sid] = str(item.get("summary") or "").strip()

    out_atts: list[dict[str, str]] = []
    for att in attachments:
        sid = str(att.get("source_id") or "")
        name = str(att.get("name") or "")
        if att.get("needs_file"):
            summ = _NEEDS_FILE_SUMMARY
        else:
            summ = by_id.get(sid, "")
        out_atts.append({"source_id": sid, "name": name, "summary": summ})
    return {"body": body, "attachments": out_atts}


def _minimal_summary(title: str, attachments: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM 없이/실패 시의 안전 폴백 — 숫자를 일절 지어내지 않는 최소 요약."""
    title = (title or "").strip()
    if title:
        body = f"이 공지는 '{title}' 안내입니다. 자세한 내용은 아래 본문과 첨부 자료를 확인해 주세요."
    else:
        body = "자세한 내용은 아래 본문과 첨부 자료를 확인해 주세요."
    out_atts = [
        {
            "source_id": str(att.get("source_id") or ""),
            "name": str(att.get("name") or ""),
            "summary": _NEEDS_FILE_SUMMARY if att.get("needs_file") else "",
        }
        for att in attachments
    ]
    return {"body": body, "attachments": out_atts}


def _build_prompt(title: str, body: str, attachments: list[dict[str, Any]]) -> str:
    lines = [PROMPT, f"[제목] {title}".strip(), "", "[본문]", body.strip() or "(본문 없음)", ""]
    for idx, att in enumerate(attachments, 1):
        lines.append(f"[첨부 {idx}] source_id={att.get('source_id')} name={att.get('name')}")
        text = str(att.get("text") or "").strip()
        lines.append(text if text else "(읽을 수 없는 자료 — 원본 파일 확인)")
        lines.append("")
    return "\n".join(lines)


async def summarize(
    *,
    title: str,
    body: str,
    attachments: list[dict[str, Any]] | None,
    gemini: Any,
) -> tuple[dict[str, Any], int]:
    """본문 + 첨부 정제본을 요약한다.

    반환: (요약 dict {body, attachments:[{source_id,name,summary}]}, gemini 호출수)
    """
    title = (title or "").strip()
    body = (body or "").strip()
    atts = attachments or []

    has_content = bool(body) or any(str(a.get("text") or "").strip() for a in atts)
    if gemini is None or not has_content:
        return _minimal_summary(title, atts), 0

    source_all = "\n".join([body] + [str(a.get("text") or "") for a in atts])
    base_prompt = _build_prompt(title, body, atts)
    calls = 0

    for attempt in range(2):  # 최초 1회 + 환각 감지 시 1회 재생성
        prompt = base_prompt
        if attempt == 1:
            prompt += "\n주의: 날짜·금액은 원문에 실제로 있는 값만 쓰고, 없으면 절대 쓰지 마라."
        try:
            calls += 1
            raw = await gemini.generate_text(prompt)
        except Exception:  # noqa: BLE001 - 요약 실패가 공지를 잃게 하지 않는다(폴백).
            break
        data = _parse_json(raw or "")
        if not data:
            continue
        cleaned = _coerce(data, atts)
        check_text = cleaned["body"] + " " + " ".join(a["summary"] for a in cleaned["attachments"])
        if not _hallucinated_facts(check_text, source_all):
            return cleaned, calls

    # 파싱 실패 또는 환각 미해결 → 숫자 없는 최소 요약으로 폴백(충실 최우선).
    return _minimal_summary(title, atts), calls


# 파일명은 URL 인코딩 흔적(+, _)이 많아 사람이 읽기 좋게 공백으로 편다.
def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").replace("+", " ").replace("_", " ")).strip()


# 렌더 시 "첨부 '…'에는" 리드인을 붙이므로, 요약문이 또 "이 첨부파일에는…"으로 시작하면
# "…에는 이 첨부파일에는…"으로 중복된다. 그 머리말을 떼어 자연스럽게 잇는다.
_ATT_LEADIN_RE = re.compile(r"^\s*(이\s*)?(첨부\s*파일|첨부|자료|파일)\s*(에는|에|은|는|:)?\s*")


def render_summary_markdown(summary: dict[str, Any] | None) -> str:
    """요약 구조 JSON → 사람이 읽는 markdown 문단 prose(번역·렌더 대상)."""
    if not isinstance(summary, dict):
        return ""
    parts: list[str] = []
    body = str(summary.get("body") or "").strip()
    if body:
        parts.append(body)
    for att in summary.get("attachments") or []:
        if not isinstance(att, dict):
            continue
        name = _clean_name(str(att.get("name") or ""))
        summ = _ATT_LEADIN_RE.sub("", str(att.get("summary") or "").strip()).strip()
        if name and summ:
            parts.append(f"첨부 '{name}'에는 {summ}")
        elif name:
            parts.append(f"첨부 '{name}'이(가) 포함되어 있습니다.")
    return "\n\n".join(parts).strip()
