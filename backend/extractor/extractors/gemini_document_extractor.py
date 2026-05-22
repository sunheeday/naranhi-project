from __future__ import annotations

import base64
import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from extractor.http_security import sanitize_error


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_HTTP_STATUS_CODES = {403, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class GeminiExtractResult:
    text: str
    confidence: float | None
    is_readable: bool
    warnings: list[str]
    detected_layout: str
    source_pages: list[int]


class GeminiDocumentExtractor:
    def __init__(
        self,
        api_keys: str | None = None,
        *,
        model: str | None = None,
        timeout: float = 90.0,
        max_inline_mb: int = 20,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_keys = _split_api_keys(api_keys or os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or "")
        self.models = _ocr_model_candidates(model)
        self.timeout = _float_env("GEMINI_TIMEOUT_SECONDS", timeout)
        self.max_inline_mb = max_inline_mb
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> GeminiDocumentExtractor:
        self._get_client()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client and not self._client.is_closed:
            await self._client.aclose()
        if self._owns_client:
            self._client = None

    async def extract_path(self, path: Path, *, mime_type: str, prompt: str) -> GeminiExtractResult:
        data = path.read_bytes()
        return await self.extract_bytes(data, mime_type=mime_type, prompt=prompt)

    async def extract_bytes(self, data: bytes, *, mime_type: str, prompt: str) -> GeminiExtractResult:
        if not self.api_keys:
            raise RuntimeError("GEMINI_API_KEYS 또는 GEMINI_API_KEY 환경변수가 필요합니다.")
        if len(data) > self.max_inline_mb * 1024 * 1024:
            raise RuntimeError(f"Gemini inline upload limit exceeded for POC: {len(data)} bytes")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64.b64encode(data).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
        parsed = await self._generate_json_payload(payload, models=self.models, retry_empty_text=True)
        return GeminiExtractResult(
            text=str(parsed.get("text") or ""),
            confidence=_optional_float(parsed.get("confidence")),
            is_readable=bool(parsed.get("is_readable", False)),
            warnings=[str(item) for item in parsed.get("warnings") or []],
            detected_layout=str(parsed.get("detected_layout") or "unknown"),
            source_pages=[int(item) for item in parsed.get("source_pages") or [] if str(item).isdigit()],
        )

    async def generate_json(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        if not self.api_keys:
            raise RuntimeError("GEMINI_API_KEYS 또는 GEMINI_API_KEY 환경변수가 필요합니다.")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
        return await self._generate_json_payload(
            payload,
            models=[model or os.getenv("GEMINI_STRUCT_MODEL", "gemini-2.5-flash")],
        )

    async def _generate_json_payload(
        self,
        payload: dict[str, Any],
        *,
        models: list[str],
        retry_empty_text: bool = False,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        last_parsed: dict[str, Any] | None = None
        client = self._get_client()
        model_candidates = _dedupe(models)
        for model_index, model in enumerate(model_candidates):
            for attempt in range(3):
                retry_after_seconds = 0.0
                for api_key in self.api_keys:
                    try:
                        response = await client.post(
                            f"{GEMINI_API_BASE}/{model}:generateContent",
                            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                            json=payload,
                        )
                        response.raise_for_status()
                        parsed = _parse_json(_extract_text(response.json()))
                        if _should_retry_empty_result(parsed, retry_empty_text) and model_index + 1 < len(model_candidates):
                            last_parsed = parsed
                            break
                        return parsed
                    except httpx.HTTPStatusError as exc:
                        last_error = exc
                        retry_after_seconds = max(retry_after_seconds, _retry_after_seconds(exc.response))
                        if exc.response.status_code in RETRYABLE_HTTP_STATUS_CODES:
                            continue
                        raise RuntimeError(sanitize_error(exc)) from exc
                    except httpx.TimeoutException as exc:
                        last_error = exc
                        continue
                    except (json.JSONDecodeError, ValueError) as exc:
                        last_error = exc
                        continue
                if last_parsed is not None and model_index + 1 < len(model_candidates):
                    break
                if attempt < 2:
                    await asyncio.sleep(retry_after_seconds or 2**attempt)
        if last_error:
            raise RuntimeError(sanitize_error(last_error)) from last_error
        if last_parsed is not None:
            return last_parsed
        raise RuntimeError("Gemini request failed without response")

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._owns_client = True
        return self._client


def ocr_prompt(source_name: str) -> str:
    return f"""
너는 한국 학교 가정통신문 OCR 엔진이다.

대상: {source_name}

규칙:
- 보이는 텍스트를 원문 그대로 추출한다.
- 요약하지 않는다.
- 문장을 새로 만들지 않는다.
- 표는 줄과 탭을 최대한 보존한다.
- 읽기 어려운 부분은 [판독불가]로 표시한다.
- 문서에 텍스트가 거의 없으면 is_readable=false로 둔다.

반드시 JSON만 반환한다.
{{
  "text": "추출 원문",
  "confidence": 0.0,
  "is_readable": true,
  "warnings": [],
  "detected_layout": "plain/table/photo_notice/scanned_pdf/unknown",
  "source_pages": [1]
}}
""".strip()


def _split_api_keys(value: str) -> list[str]:
    keys: list[str] = []
    for item in re.split(r"[\s,;]+", value):
        stripped = item.strip()
        if stripped and stripped not in keys:
            keys.append(stripped)
    return keys


def _ocr_model_candidates(model: str | None) -> list[str]:
    if model:
        return [model]
    legacy_model = os.getenv("GEMINI_MODEL")
    if legacy_model:
        return [legacy_model]
    return _dedupe(
        [
            os.getenv("GEMINI_OCR_MODEL_PRIMARY", "gemini-2.5-flash-lite"),
            os.getenv("GEMINI_OCR_MODEL_FALLBACK", "gemini-2.5-flash"),
        ]
    )


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        stripped = value.strip()
        if stripped and stripped not in deduped:
            deduped.append(stripped)
    return deduped


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(response: httpx.Response) -> float:
    value = response.headers.get("retry-after", "")
    try:
        return max(0.0, min(float(value), 30.0))
    except ValueError:
        return 0.0


def _should_retry_empty_result(parsed: dict[str, Any], retry_empty_text: bool) -> bool:
    if not retry_empty_text:
        return False
    text = str(parsed.get("text") or "").strip()
    return not text


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    return "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))


def _parse_json(value: str) -> dict[str, Any]:
    value = value.strip()
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, re.DOTALL)
        if not match:
            raise
        value = match.group(0)
    try:
        return json.loads(value, strict=False)
    except json.JSONDecodeError:
        escaped = re.sub(r"""\\(?!["\\/bfnrtu])""", r"\\\\", value)
        return json.loads(escaped, strict=False)
