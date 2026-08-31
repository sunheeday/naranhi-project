"""번역 파이프라인이 쓰는 JSON 모델 클라이언트의 이음매.

오케스트레이터가 클라이언트에서 쓰는 것은 generate_json 과 source_hard_fact_model
둘뿐이다(orchestrator.py:60-65, :63). 그래서 프로토콜이 이만큼 작다.

GeminiJsonClient 는 이미 이 프로토콜을 만족하므로 한 글자도 고치지 않는다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.core.config import Settings

LOGGER = logging.getLogger(__name__)

BACKEND_GEMINI = "gemini"
BACKEND_BEDROCK = "bedrock"


@runtime_checkable
class JsonModelClient(Protocol):
    """JSON 을 돌려주는 LLM 클라이언트. 시그니처는 gemini_client.py:125-132 그대로."""

    source_hard_fact_model: str | None

    async def generate_json(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
        model: str | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]: ...


def build_json_client(settings: "Settings") -> JsonModelClient:
    """설정에 따라 번역용 JSON 클라이언트를 만든다.

    알 수 없는 값이면 경고만 남기고 Gemini 로 간다 — env 오타로 번역이 멈추는 것보다
    현행 백엔드로 계속 도는 편이 낫다.
    """
    backend = (settings.translation_backend or BACKEND_GEMINI).strip().lower()

    if backend == BACKEND_BEDROCK:
        from app.translation.bedrock_client import BedrockJsonClient

        return BedrockJsonClient.from_settings(settings)

    if backend != BACKEND_GEMINI:
        LOGGER.warning(
            "알 수 없는 TRANSLATION_BACKEND=%r — gemini 로 폴백한다.",
            settings.translation_backend,
        )

    from app.translation.gemini_client import GeminiJsonClient

    return GeminiJsonClient.from_settings(settings)
