from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from app.crawler.link_extractor import LinkCandidate


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


@dataclass(frozen=True)
class GeminiDecision:
    best_url: str | None
    confidence: float
    reason: str
    alternatives: list[dict[str, Any]]
    needs_human_check: bool
    raw_text: str = ""


class GeminiFinder:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self.api_keys = _split_api_keys(api_key)
        self.timeout = timeout

    async def choose_notice_board(
        self,
        *,
        school_name: str,
        homepage_url: str,
        page_title: str,
        page_snippet: str,
        candidates: list[LinkCandidate],
    ) -> GeminiDecision:
        if not self.api_keys:
            raise RuntimeError("GEMINI_API_KEY 또는 GEMINI_API_KEYS 환경변수가 필요합니다.")

        prompt = _build_prompt(
            school_name=school_name,
            homepage_url=homepage_url,
            page_title=page_title,
            page_snippet=page_snippet,
            candidates=candidates,
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for api_key in self.api_keys:
                headers = {
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                }
                try:
                    response = await client.post(GEMINI_ENDPOINT, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    break
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code in {429, 403}:
                        continue
                    raise
            else:
                if last_error:
                    raise last_error
                raise RuntimeError("Gemini 요청에 실패했습니다.")

        text = _extract_text(data)
        parsed = _parse_json(text)
        return GeminiDecision(
            best_url=parsed.get("best_url"),
            confidence=float(parsed.get("confidence") or 0),
            reason=str(parsed.get("reason") or ""),
            alternatives=list(parsed.get("alternatives") or []),
            needs_human_check=bool(parsed.get("needs_human_check", True)),
            raw_text=text,
        )


def heuristic_decision(candidates: list[LinkCandidate]) -> GeminiDecision:
    best = candidates[0] if candidates else None
    if not best:
        return GeminiDecision(
            best_url=None,
            confidence=0,
            reason="후보 링크를 찾지 못했습니다.",
            alternatives=[],
            needs_human_check=True,
        )

    confidence = min(max(best.score / 120, 0.2), 0.85)
    return GeminiDecision(
        best_url=best.url,
        confidence=confidence,
        reason="Gemini 키가 없어서 규칙 기반 점수 1위 후보를 선택했습니다.",
        alternatives=[asdict(item) for item in candidates[1:4]],
        needs_human_check=True,
    )


def _split_api_keys(value: str) -> list[str]:
    keys: list[str] = []
    for item in re.split(r"[\s,;]+", value):
        stripped = item.strip()
        if stripped and stripped not in keys:
            keys.append(stripped)
    return keys


def _build_prompt(
    *,
    school_name: str,
    homepage_url: str,
    page_title: str,
    page_snippet: str,
    candidates: list[LinkCandidate],
) -> str:
    compact_candidates = [
        {
            "text": item.text,
            "url": item.url,
            "context": item.context[:260],
            "score": item.score,
        }
        for item in candidates[:50]
    ]

    return f"""
너는 한국 초등학교/중학교 홈페이지에서 '가정통신문' 게시판 위치를 찾는 분류기다.

절대 규칙:
- 학교 홈페이지 URL은 이미 NEIS에서 받은 값이다. 이것을 의심하지 마라.
- 후보 링크 중에서 가정통신문 게시판 또는 가정통신문 메뉴로 가장 가까운 URL을 골라라.
- '가정통신문(교육청)', '교육청 가정통신문'은 학교 자체 가정통신문 게시판이 아니므로 고르지 마라.
- 학교 자체 가정통신문 후보가 없고 교육청 가정통신문만 있으면 best_url을 null로 둬라.
- URL 패턴만 보고 목록/상세를 단정하지 마라. 어떤 학교는 상세글에 들어가도 URL이 그대로 유지된다.
- selectNttInfo.do, view.do, nttSn, boardSeq 같은 패턴은 참고만 하고, 최종 판단은 링크 텍스트/메뉴 맥락/페이지 내용으로 해라.
- 확실하지 않으면 best_url을 null로 두고 needs_human_check를 true로 둬라.

학교명: {school_name}
학교 홈페이지: {homepage_url}
홈페이지 title: {page_title}
홈페이지 snippet: {page_snippet}

후보 링크 JSON:
{json.dumps(compact_candidates, ensure_ascii=False)}

반드시 아래 JSON 스키마만 반환해라.
{{
  "best_url": "https://... 또는 null",
  "confidence": 0.0,
  "reason": "판단 이유",
  "alternatives": [
    {{"url": "https://...", "reason": "대안 이유"}}
  ],
  "needs_human_check": true
}}
""".strip()


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return "{}"
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "\n".join(texts).strip()


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise

