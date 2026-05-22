from __future__ import annotations

import json
import re
from typing import Any

import httpx


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiJsonClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.api_keys = _split_api_keys(api_key)
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def generate_json(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        if not self.api_keys:
            raise RuntimeError("GEMINI_API_KEY 또는 GEMINI_API_KEYS가 필요합니다.")

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        endpoint = f"{GEMINI_API_BASE}/{self.model}:generateContent"
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for api_key in self.api_keys:
                try:
                    response = await client.post(
                        endpoint,
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
        raise RuntimeError("Gemini 요청에 실패했습니다.")


def _split_api_keys(value: str) -> list[str]:
    keys: list[str] = []
    for item in re.split(r"[\s,;]+", value):
        stripped = item.strip()
        if stripped and stripped not in keys:
            keys.append(stripped)
    return keys


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise RuntimeError("Gemini 응답에서 텍스트를 찾지 못했습니다.")


def _parse_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("Gemini JSON 응답이 object가 아닙니다.")
    return parsed
