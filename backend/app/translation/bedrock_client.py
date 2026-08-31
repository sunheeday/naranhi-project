"""AWS Bedrock Converse API 로 JSON 을 받아오는 클라이언트.

전역 세마포어(gemini_client:61-71)·백오프(:35-58)·JSON 파서(:270-298)를 그대로
재사용한다. 새로 쓰는 것은 요청 조립·응답 추출·스레드 브리지 셋뿐이다.

크롤러가 빌려 쓰는 call_with_quota_backoff / _repair_invalid_json_escapes 의
이름·위치는 건드리지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from app.translation.gemini_client import (
    _get_call_semaphore,
    _parse_json,
    call_with_quota_backoff,
)

if TYPE_CHECKING:
    from app.core.config import Settings

LOGGER = logging.getLogger(__name__)

# Converse 는 응답 길이 상한을 요청에서 받는다. Gemini 의 기본과 맞춘다.
BEDROCK_MAX_TOKENS = 8192
# Bedrock 에는 response_mime_type 동등 기능이 없다. assistant 턴을 "{" 로 시작시켜
# 모델이 산문 없이 JSON 을 이어 쓰게 만든다. toolConfig 는 쓰지 않는다 —
# 프롬프트 13개의 스키마를 JSON Schema 로 다시 써야 해서 A/B 통제가 무너진다.
JSON_PREFILL = "{"


def _extract_bedrock_text(response: dict[str, Any]) -> str:
    """Converse 응답에서 텍스트 블록을 꺼낸다. reasoningContent 블록은 건너뛴다."""
    message = (response.get("output") or {}).get("message") or {}
    for block in message.get("content") or []:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    raise RuntimeError("Bedrock 응답에서 텍스트를 찾지 못했습니다.")


class BedrockJsonClient:
    def __init__(
        self,
        *,
        model: str,
        source_hard_fact_model: str | None = None,
        region: str = "ap-northeast-2",
        timeout_seconds: float = 60.0,
        max_workers: int = 32,
        use_json_prefill: bool = True,
    ) -> None:
        self.model = model
        self.source_hard_fact_model = source_hard_fact_model or model
        self.region = region
        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self.use_json_prefill = use_json_prefill
        self._client: Any = None
        # boto3 converse() 는 블로킹이다. asyncio 기본 executor 는 min(32, cpu+4) 이고
        # 워커는 --cpu=1 이라 5다 — 세마포어가 32를 허용해도 5에서 조용히 직렬화된다.
        # 그래서 클라이언트가 자기 풀을 소유한다.
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="bedrock",
        )

    @classmethod
    def from_settings(cls, settings: "Settings") -> "BedrockJsonClient":
        return cls(
            model=settings.bedrock_translation_model,
            source_hard_fact_model=settings.bedrock_mechanical_model,
            region=settings.bedrock_region,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_workers=settings.bedrock_max_workers,
        )

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                config=Config(
                    # Gemini SDK 결함 #2705 의 Bedrock 판 대응 — 여기서는 지원 노브다.
                    tcp_keepalive=True,
                    # SDK 내부 재시도를 끄고 앱 백오프(call_with_quota_backoff)만 남긴다.
                    retries={"max_attempts": 1, "mode": "standard"},
                    connect_timeout=10,
                    read_timeout=self.timeout_seconds,
                    # 커넥션 풀이 스레드 수보다 작으면 거기서 다시 직렬화된다.
                    max_pool_connections=self.max_workers,
                ),
            )
        return self._client

    def _build_request(self, *, prompt: str, temperature: float, model: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": prompt}]}]
        if self.use_json_prefill:
            messages.append({"role": "assistant", "content": [{"text": JSON_PREFILL}]})
        return {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": BEDROCK_MAX_TOKENS,
            },
            # thinking(additionalModelRequestFields)은 넣지 않는다 — 아래 주석 참조.
        }

    async def _converse_in_thread(
        self, *, prompt: str, temperature: float, model: str
    ) -> dict[str, Any]:
        request = self._build_request(prompt=prompt, temperature=temperature, model=model)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._get_client().converse(**request),
        )

    async def generate_json(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
        model: str | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        target_model = model or self.model

        if thinking_budget:
            # Bedrock 은 extended thinking 을 켜면 temperature 를 1로 강제한다.
            # 파이프라인 14곳이 0.0/0.1 을 쓰고 그 결정성이
            # validate_hard_facts_by_code 의 전제라 온도를 조용히 바꿀 수 없다.
            # 그래서 무시하되, 조용히 무시하지 않고 경고를 남긴다.
            LOGGER.warning(
                "Bedrock 경로는 thinking 을 켜지 않는다(temperature=1 강제 회피). "
                "요청값을 무시한다: model=%s thinking_budget=%s",
                target_model,
                thinking_budget,
            )

        # 전역 세마포어로 동시 호출 수를 묶는다(Gemini 경로와 같은 상한을 공유).
        async with _get_call_semaphore():
            response = await call_with_quota_backoff(
                lambda: self._converse_in_thread(
                    prompt=prompt,
                    temperature=temperature,
                    model=target_model,
                ),
                label=f"translation:{target_model}",
            )

        text = _extract_bedrock_text(response)
        # 프리필을 무시하고 완전한 JSON 을 돌려주는 모델이 있다. 무조건 "{" 를 붙이면
        # "{{...}" 가 되어 파서가 깨지므로, 이미 열려 있으면 그대로 둔다.
        if self.use_json_prefill and not text.startswith(JSON_PREFILL):
            text = JSON_PREFILL + text
        return _parse_json(text)
