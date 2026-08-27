from __future__ import annotations

import asyncio
import json
import logging
import random
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
            # full-ish jitter: 공유풀(DSQ)에서 여러 콜이 동시에 같은 간격으로 재시도해
            # 다시 몰리는 thundering herd를 깬다.
            jittered = delay * (0.5 + random.random())
            LOGGER.warning(
                "Gemini quota(429) hit; retrying call in %.1fs: label=%s attempt=%s/%s",
                jittered,
                label,
                attempt,
                len(delays_seconds) + 1,
            )
            await asyncio.sleep(jittered)
    return await factory()


_CALL_SEMAPHORE: "asyncio.Semaphore | None" = None


def _get_call_semaphore() -> asyncio.Semaphore:
    """동시 Gemini 호출 수의 전역 상한(DSQ guard). 실행 중인 이벤트 루프에 지연 바인딩한다."""
    global _CALL_SEMAPHORE
    if _CALL_SEMAPHORE is None:
        from app.core.config import get_settings

        _CALL_SEMAPHORE = asyncio.Semaphore(get_settings().gemini_max_concurrency)
    return _CALL_SEMAPHORE


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
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        # 전역 세마포어로 동시 Gemini 호출 수를 묶는다(DSQ self-inflicted 429 방지).
        # 백오프 대기 중에도 슬롯을 쥐고 있어 자연스러운 backpressure가 된다.
        async with _get_call_semaphore():
            if self.use_vertex:
                return await self._generate_json_vertex(
                    prompt=prompt,
                    temperature=temperature,
                    model=model or self.model,
                    thinking_budget=thinking_budget,
                )
            return await self._generate_json_api_key(
                prompt=prompt,
                temperature=temperature,
                model=model or self.model,
                thinking_budget=thinking_budget,
            )

    def _get_vertex_client(self) -> Any:
        if self._vertex_client is None:
            import socket

            from google import genai
            from google.genai import types

            # googleapis/python-genai #2705: 기본 httpx transport 가 SO_KEEPALIVE 를
            # 켜지 않아, 콜당 20~30초 무응답이 정상인 이 워크로드에서 NAT 가 연결을 끊는다.
            # TCP_KEEPIDLE 계열은 리눅스에만 있으므로 있는 것만 넣는다.
            socket_options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
            for name, value in (("TCP_KEEPIDLE", 15), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 6)):
                option = getattr(socket, name, None)
                if option is not None:
                    socket_options.append((socket.IPPROTO_TCP, option, value))

            self._vertex_client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                http_options=types.HttpOptions(
                    api_version="v1",
                    timeout=int(self.timeout_seconds * 1000),
                    # #1875: SDK 내부 재시도(고정 백오프 5회)가 앱 백오프 4회와 중첩돼
                    # 최악 ~20회 시도가 된다. SDK 쪽을 1회로 묶고 앱 백오프만 남긴다.
                    retry_options=types.HttpRetryOptions(attempts=1),
                    async_client_args={
                        "transport": httpx.AsyncHTTPTransport(socket_options=socket_options),
                    },
                ),
            )
        return self._vertex_client

    async def _generate_json_vertex(
        self,
        *,
        prompt: str,
        temperature: float,
        model: str,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        from google.genai import types

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "response_mime_type": "application/json",
        }
        if thinking_budget is not None:
            # 기계적 추출·역번역 콜은 thinking을 제한해 지연·비용을 줄인다 (0 = 끔).
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=thinking_budget
            )

        client = self._get_vertex_client()
        response = await call_with_quota_backoff(
            lambda: client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
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
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        if not self.api_keys:
            raise RuntimeError("GEMINI_API_KEY 또는 GEMINI_API_KEYS가 필요합니다.")

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "responseMimeType": "application/json",
        }
        if thinking_budget is not None:
            generation_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
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
