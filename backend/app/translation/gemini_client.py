from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from app.core.config import Settings


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


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
        timeout_seconds: float = 60.0,
        use_vertex: bool = False,
        project: str | None = None,
        location: str = "global",
    ) -> None:
        self.api_keys = _split_api_keys(api_key or "")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.use_vertex = use_vertex
        self.project = project
        self.location = location
        self._vertex_client: Any = None

    @classmethod
    def from_settings(cls, settings: "Settings") -> "GeminiJsonClient":
        """Build a client based on app settings, preferring Vertex AI when configured."""
        model = settings.gemini_translation_model or settings.gemini_model
        if settings.use_vertex:
            return cls(
                model=model,
                timeout_seconds=settings.gemini_timeout_seconds,
                use_vertex=True,
                project=settings.vertex_ai_project_id,
                location=settings.vertex_ai_location,
            )
        return cls(
            api_key=settings.gemini_key_material,
            model=model,
            timeout_seconds=settings.gemini_timeout_seconds,
        )

    async def generate_json(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        if self.use_vertex:
            return await self._generate_json_vertex(prompt=prompt, temperature=temperature)
        return await self._generate_json_api_key(prompt=prompt, temperature=temperature)

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
    ) -> dict[str, Any]:
        from google.genai import types

        client = self._get_vertex_client()
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
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
