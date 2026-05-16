from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.crawler.gemini_finder import GEMINI_ENDPOINT


@dataclass(frozen=True)
class GeminiRowChoice:
    row_id: str
    is_post: bool
    title: str
    post_id_candidate: str | None
    post_id_source: str
    confidence: float


@dataclass(frozen=True)
class GeminiUrlOrder:
    ordered_candidate_ids: list[str]
    reason: str
    confidence: float


@dataclass(frozen=True)
class GeminiFailureClassification:
    classification: str
    retryable: bool
    reason: str


class UnknownPostGeminiResolver:
    def __init__(self, api_keys: str | None, timeout: float = 30.0) -> None:
        self.api_keys = _split_api_keys(api_keys or "")
        self.timeout = timeout

    async def choose_post_rows(
        self,
        *,
        board_url: str,
        page_title: str,
        forms: list[dict[str, Any]],
        script_snippets: list[str],
        row_candidates: list[dict[str, Any]],
    ) -> list[GeminiRowChoice]:
        if not self.api_keys or not row_candidates:
            return []

        payload = {
            "board_url": board_url,
            "page_title": page_title,
            "cms_detection": "unknown",
            "forms": forms[:8],
            "scripts": script_snippets[:6],
            "row_candidates": row_candidates[:25],
        }
        parsed = await self._generate_json(_row_prompt(payload))
        choices: list[GeminiRowChoice] = []
        for item in parsed.get("post_rows") or []:
            if not isinstance(item, dict):
                continue
            choices.append(
                GeminiRowChoice(
                    row_id=str(item.get("row_id") or ""),
                    is_post=bool(item.get("is_post")),
                    title=str(item.get("title") or ""),
                    post_id_candidate=(
                        str(item.get("post_id_candidate"))
                        if item.get("post_id_candidate") is not None
                        else None
                    ),
                    post_id_source=str(item.get("post_id_source") or "gemini"),
                    confidence=float(item.get("confidence") or 0),
                )
            )
        return choices

    async def order_url_candidates(
        self,
        *,
        row_id: str,
        post_id: str,
        board_url: str,
        url_candidates: list[dict[str, str]],
        script_snippets: list[str],
    ) -> GeminiUrlOrder | None:
        if not self.api_keys or not url_candidates:
            return None

        payload = {
            "row_id": row_id,
            "post_id": post_id,
            "board_url": board_url,
            "url_candidates": url_candidates[:12],
            "javascript_snippets": script_snippets[:6],
        }
        parsed = await self._generate_json(_url_order_prompt(payload))
        return GeminiUrlOrder(
            ordered_candidate_ids=[
                str(item) for item in parsed.get("ordered_candidate_ids") or []
            ],
            reason=str(parsed.get("reason") or ""),
            confidence=float(parsed.get("confidence") or 0),
        )

    async def classify_failure(
        self,
        *,
        attempted_url: str,
        status_code: int | None,
        final_url: str,
        title: str,
        snippet: str,
        row_title: str,
    ) -> GeminiFailureClassification | None:
        if not self.api_keys:
            return None

        payload = {
            "attempted_url": attempted_url,
            "status_code": status_code,
            "final_url": final_url,
            "title": title,
            "snippet": snippet[:800],
            "row_title": row_title,
        }
        parsed = await self._generate_json(_failure_prompt(payload))
        return GeminiFailureClassification(
            classification=str(parsed.get("classification") or "detail_url_failed"),
            retryable=bool(parsed.get("retryable", False)),
            reason=str(parsed.get("reason") or ""),
        )

    async def _generate_json(self, prompt: str) -> dict[str, Any]:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.05,
                "responseMimeType": "application/json",
            },
        }
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for api_key in self.api_keys:
                try:
                    response = await client.post(
                        GEMINI_ENDPOINT,
                        headers={
                            "x-goog-api-key": api_key,
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    return _parse_json(_extract_text(response.json()))
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code in {403, 429}:
                        continue
                    raise
            if last_error:
                raise last_error
        return {}


def _row_prompt(payload: dict[str, Any]) -> str:
    return f"""
너는 한국 학교 홈페이지 게시판 HTML 구조 분석기다.

목표:
- row_candidates 중 실제 게시글 row만 고른다.
- 각 게시글을 구분하는 post_id 후보를 찾는다.
- 새 URL은 만들지 않는다. 주어진 href/data/onclick/forms/scripts에서 근거를 찾아라.

판단 기준:
- 제목/등록일/작성자/조회수/첨부파일 같은 게시판 row 신호를 우선한다.
- 메뉴, 푸터, 팝업, 급식, 일정, 사진첩, 파일 다운로드 링크는 게시글 row가 아니다.
- data-id, nttSn, boardSeq, nttId, number, /view/숫자는 post_id 후보가 될 수 있다.

입력 JSON:
{json.dumps(payload, ensure_ascii=False)}

반드시 아래 JSON만 반환해라.
{{
  "post_rows": [
    {{
      "row_id": "R1",
      "is_post": true,
      "title": "게시글 제목",
      "post_id_candidate": "12345 또는 null",
      "post_id_source": "data-id / onclick arg 3 / href query nttSn / path /view",
      "confidence": 0.0
    }}
  ]
}}
""".strip()


def _url_order_prompt(payload: dict[str, Any]) -> str:
    return f"""
너는 한국 학교 게시판의 상세 URL 후보 우선순위 분류기다.

목표:
- url_candidates 중 실제 상세글로 들어갈 가능성이 높은 순서로 candidate_id만 정렬한다.
- 새 URL을 만들지 않는다.
- JavaScript snippet에 명확한 location.href/action 템플릿이 있으면 그 템플릿과 일치하는 후보를 우선한다.

입력 JSON:
{json.dumps(payload, ensure_ascii=False)}

반드시 아래 JSON만 반환해라.
{{
  "ordered_candidate_ids": ["U1", "U2"],
  "reason": "판단 이유",
  "confidence": 0.0
}}
""".strip()


def _failure_prompt(payload: dict[str, Any]) -> str:
    return f"""
너는 학교 게시판 상세글 접속 실패 원인을 분류한다.

분류값은 다음 중 하나만 사용한다.
- unsupported_login_required
- unsupported_forbidden
- unsupported_external_dynamic
- detail_url_failed
- parse_failed
- retryable_transient

입력 JSON:
{json.dumps(payload, ensure_ascii=False)}

반드시 아래 JSON만 반환해라.
{{
  "classification": "detail_url_failed",
  "retryable": false,
  "reason": "짧은 이유"
}}
""".strip()


def _split_api_keys(value: str) -> list[str]:
    keys: list[str] = []
    for item in re.split(r"[\s,;]+", value):
        stripped = item.strip()
        if stripped and stripped not in keys:
            keys.append(stripped)
    return keys


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return "{}"
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    return "\n".join(
        part.get("text", "") for part in parts if isinstance(part, dict)
    ).strip()


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {}

