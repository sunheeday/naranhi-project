from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from app.core.config import Settings


LOGGER = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Vertex AI Gemini는 dynamic shared quota라 일시 혼잡 시 429를 돌려준다.
# 같은 호출을 잠깐 기다렸다 재시도하면 대부분 통과하므로, 파이프라인 전체를
# 폴백으로 포기하기 전에 콜 단위로 지수 백오프 재시도한다.
QUOTA_BACKOFF_DELAYS_SECONDS: tuple[float, ...] = (5.0, 10.0, 20.0, 40.0)


def is_quota_exhausted_error(error: Exception) -> bool:
    message = f"{type(error).__name__}: {error}".lower()
    return any(
        marker in message
        for marker in ("429", "resource_exhausted", "rate limit", "rate_limit", "quota")
    )


async def call_with_quota_backoff(
    factory: Callable[[], Awaitable[Any]],
    *,
    delays_seconds: tuple[float, ...] = QUOTA_BACKOFF_DELAYS_SECONDS,
    label: str = "gemini",
) -> Any:
    for attempt, delay in enumerate(delays_seconds, start=1):
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 - 429만 흡수, 나머지는 즉시 전파.
            if not is_quota_exhausted_error(exc):
                raise
            LOGGER.warning(
                "Gemini quota(429) hit; retrying call in %.0fs: label=%s attempt=%s/%s",
                delay,
                label,
                attempt,
                len(delays_seconds) + 1,
            )
            await asyncio.sleep(delay)
    return await factory()


class GeminiJsonClient:
    """Gemini JSON client supporting two backends.

    - Vertex AI (``use_vertex=True``): calls Gemini through Vertex AI using the
      google-genai SDK with Application Default Credentials (no API key). This is
      required for GCP free-trial credit to apply.
    - API key (default): legacy AI Studio call via httpx. Kept as a fallback for
      local development and rollback.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str,
        source_hard_fact_model: str | None = None,
        timeout_seconds: float = 60.0,
        use_vertex: bool = False,
        project: str | None = None,
        location: str = "global",
    ) -> None:
        self.api_keys = _split_api_keys(api_key or "")
        self.model = model
        self.source_hard_fact_model = source_hard_fact_model or model
        self.timeout_seconds = timeout_seconds
        self.use_vertex = use_vertex
        self.project = project
        self.location = location
        self._vertex_client: Any = None

    @classmethod
    def from_settings(cls, settings: "Settings") -> "GeminiJsonClient":
        """Build a client based on app settings, preferring Vertex AI when configured."""
        model = settings.gemini_translation_model or settings.gemini_model
        source_hard_fact_model = settings.gemini_source_hard_fact_model or model
        if settings.use_vertex:
            return cls(
                model=model,
                source_hard_fact_model=source_hard_fact_model,
                timeout_seconds=settings.gemini_timeout_seconds,
                use_vertex=True,
                project=settings.vertex_ai_project_id,
                location=settings.vertex_ai_location,
            )
        return cls(
            api_key=settings.gemini_key_material,
            model=model,
            source_hard_fact_model=source_hard_fact_model,
            timeout_seconds=settings.gemini_timeout_seconds,
        )

    async def generate_json(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
        model: str | None = None,
    ) -> dict[str, Any]:
        if self.use_vertex:
            return await self._generate_json_vertex(
                prompt=prompt,
                temperature=temperature,
                model=model or self.model,
            )
        return await self._generate_json_api_key(
            prompt=prompt,
            temperature=temperature,
            model=model or self.model,
        )

    def _get_vertex_client(self) -> Any:
        if self._vertex_client is None:
            from google import genai
            from google.genai import types

            self._vertex_client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                http_options=types.HttpOptions(
                    api_version="v1",
                    timeout=int(self.timeout_seconds * 1000),
                ),
            )
        return self._vertex_client

    async def _generate_json_vertex(
        self,
        *,
        prompt: str,
        temperature: float,
        model: str,
    ) -> dict[str, Any]:
        from google.genai import types

        client = self._get_vertex_client()
        response = await call_with_quota_backoff(
            lambda: client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            ),
            label=f"translation:{model}",
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini(Vertex) 응답에서 텍스트를 찾지 못했습니다.")
        return _parse_json(text)

    async def _generate_json_api_key(
        self,
        *,
        prompt: str,
        temperature: float,
        model: str,
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
        endpoint = f"{GEMINI_API_BASE}/{model}:generateContent"
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
        value = match.group(0)
        try:
            parsed = json.loads(value, strict=False)
        except json.JSONDecodeError:
            parsed = json.loads(_repair_invalid_json_escapes(value), strict=False)

    if not isinstance(parsed, dict):
        raise ValueError("Gemini JSON 응답이 object가 아닙니다.")
    return parsed


def _repair_invalid_json_escapes(value: str) -> str:
    """LLM 응답 JSON 문자열 안의 잘못된 백슬래시 이스케이프(\\m 등)를 리터럴로 교정한다.

    유효한 이스케이프(\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX)는 쌍 단위로 소비해
    그대로 보존하고, 그 외의 홀로 남은 백슬래시만 \\\\ 로 바꾼다.
    """
    return re.sub(
        r"\\(u[0-9a-fA-F]{4}|[\"\\/bfnrt])|\\",
        lambda m: m.group(0) if m.group(1) else "\\\\",
        value,
    )
