"""AWS Bedrock Converse 로 문서·이미지를 판독한다.

왜 있는가: 문서 판독이 Vertex(Gemini)로 나가면 «현금»이 청구된다. Bedrock 은 보유
크레딧에서 차감된다. 사용자 지시로 GCP AI 지출을 0 으로 만든다.

GeminiDocumentExtractor 와 «같은 모양» 을 돌려준다 — 파이프라인 12곳이 그 타입을
그대로 쓰고 있어서 반환 형태를 바꾸면 전부 손봐야 한다.

app.* 를 import 하지 않는다. extractor 패키지는 app 보다 아래층이고, 위로 import 하면
순환이 된다. boto3 를 직접 쓴다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

LOGGER = logging.getLogger(__name__)

BEDROCK_MAX_TOKENS = 8192
JSON_PREFILL = "{"

# Converse 이미지 블록이 받는 형식.
IMAGE_FORMATS: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/gif": "gif",
    "image/webp": "webp",
}
# Converse 문서 블록이 받는 형식. PDF·한글변환본이 여기로 간다.
DOCUMENT_FORMATS: dict[str, str] = {
    "application/pdf": "pdf",
    "text/csv": "csv",
    "text/html": "html",
    "text/plain": "txt",
    "text/markdown": "md",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


def default_model() -> str:
    return (
        os.getenv("BEDROCK_TRANSLATION_MODEL")
        or "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    )


def default_region() -> str:
    return os.getenv("BEDROCK_REGION") or "ap-northeast-2"


def bedrock_enabled() -> bool:
    """문서 판독을 Bedrock 으로 돌릴지. 자격증명이 없으면 켜지지 않는다."""
    if (os.getenv("DOCUMENT_BACKEND") or os.getenv("TRANSLATION_BACKEND") or "").strip().lower() != "bedrock":
        return False
    return bool(os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ROLE_ARN") or os.getenv("AWS_PROFILE"))


def content_block(data: bytes, mime_type: str, *, name: str = "document") -> dict[str, Any]:
    """바이트를 Converse content 블록으로. 지원하지 않는 형식이면 ValueError.

    Bedrock 은 지원하지 않는 형식에 400 을 내므로 호출 전에 막는다.
    """
    if not data:
        raise ValueError("판독할 내용이 비어 있습니다.")
    mime = (mime_type or "").split(";", 1)[0].strip().lower()

    if mime in IMAGE_FORMATS:
        return {"image": {"format": IMAGE_FORMATS[mime], "source": {"bytes": data}}}
    if mime in DOCUMENT_FORMATS:
        # 문서 이름에 허용되는 문자가 제한적이다(영숫자·공백·괄호·하이픈 정도).
        safe = re.sub(r"[^A-Za-z0-9 \-()\[\]]", "", name).strip() or "document"
        return {
            "document": {
                "format": DOCUMENT_FORMATS[mime],
                "name": safe[:60],
                "source": {"bytes": data},
            }
        }

    supported = ", ".join(sorted(set(IMAGE_FORMATS) | set(DOCUMENT_FORMATS)))
    raise ValueError(f"Bedrock 이 지원하지 않는 형식입니다: {mime_type!r} (가능: {supported})")


def extract_text_block(response: dict[str, Any]) -> str:
    message = (response.get("output") or {}).get("message") or {}
    for block in message.get("content") or []:
        if isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise RuntimeError("Bedrock 응답에서 텍스트를 찾지 못했습니다.")


def parse_json_text(text: str) -> dict[str, Any]:
    """모델이 낸 텍스트에서 JSON 객체를 꺼낸다. 코드펜스·앞뒤 산문을 견딘다."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0), strict=False)


class BedrockDocumentExtractor:
    def __init__(
        self,
        *,
        model: str | None = None,
        region: str | None = None,
        timeout_seconds: float = 120.0,
        max_workers: int = 8,
    ) -> None:
        self.model = model or default_model()
        self.region = region or default_region()
        self.timeout_seconds = timeout_seconds
        self._client: Any = None
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="bedrock-doc",
        )

    def close(self) -> None:
        self._executor.shutdown(wait=False)

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                config=Config(
                    tcp_keepalive=True,
                    retries={"max_attempts": 2, "mode": "standard"},
                    connect_timeout=10,
                    read_timeout=self.timeout_seconds,
                    max_pool_connections=8,
                ),
            )
        return self._client

    async def _converse(self, content: list[dict[str, Any]], *, prefill: bool) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        if prefill:
            messages.append({"role": "assistant", "content": [{"text": JSON_PREFILL}]})
        request = {
            "modelId": self.model,
            "messages": messages,
            "inferenceConfig": {"temperature": 0.0, "maxTokens": BEDROCK_MAX_TOKENS},
        }
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            self._executor, lambda: self._get_client().converse(**request),
        )
        text = extract_text_block(response)
        if prefill and not text.startswith(JSON_PREFILL):
            text = JSON_PREFILL + text
        return text

    async def extract_bytes(
        self, data: bytes, *, mime_type: str, prompt: str, name: str = "document",
    ) -> dict[str, Any]:
        """문서·이미지 판독. GeminiDocumentExtractor 와 같은 dict 를 돌려준다."""
        text = await self._converse(
            [content_block(data, mime_type, name=name), {"text": prompt}], prefill=True,
        )
        return parse_json_text(text)

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        return parse_json_text(await self._converse([{"text": prompt}], prefill=True))

    async def generate_text(self, prompt: str) -> str:
        return await self._converse([{"text": prompt}], prefill=False)
