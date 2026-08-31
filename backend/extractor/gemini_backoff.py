from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

LOGGER = logging.getLogger(__name__)

# Vertex AI Gemini는 dynamic shared quota라 일시 혼잡 시 429를 돌려준다.
# 같은 호출을 잠깐 기다렸다 재시도하면 대부분 통과하므로, 파이프라인 전체를
# 폴백으로 포기하기 전에 콜 단위로 지수 백오프 재시도한다.
#
# 이 모듈은 번역(app/translation)과 추출(extractor/extractors) 양쪽이 함께 쓴다.
# extractor 는 app 을 임포트하지 않는 단방향 경계이므로 구현이 이쪽에 있고
# app.translation.gemini_client 가 재임포트한다. 복붙하지 말 것.
QUOTA_BACKOFF_DELAYS_SECONDS: tuple[float, ...] = (5.0, 10.0, 20.0, 40.0)


# Bedrock 은 스로틀을 ThrottlingException 으로 돌려주고 메시지는 "Too many requests,
# please wait before trying again." 이다 — 429·quota·rate limit 이 하나도 없다.
# 마커를 넓히지 않으면 백오프가 한 번도 동작하지 않고 잡 실패로 직행한다.
# Gemini 경로에는 무해하다(그 문자열이 나올 일이 없다).
QUOTA_ERROR_MARKERS: tuple[str, ...] = (
    "429",
    "resource_exhausted",
    "rate limit",
    "rate_limit",
    "quota",
    "throttling",
    "too many requests",
    "toomanyrequests",
    "serviceunavailable",
    "modelnotready",
)


def is_quota_exhausted_error(error: Exception) -> bool:
    message = f"{type(error).__name__}: {error}".lower()
    return any(marker in message for marker in QUOTA_ERROR_MARKERS)


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
