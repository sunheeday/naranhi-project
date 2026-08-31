import asyncio
import threading
import unittest
from typing import Any

from app.core.config import Settings
from app.translation.bedrock_client import BedrockJsonClient, _extract_bedrock_text


def _response(text: str, *, with_reasoning: bool = False) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if with_reasoning:
        content.append({"reasoningContent": {"reasoningText": {"text": "생각"}}})
    content.append({"text": text})
    return {"output": {"message": {"role": "assistant", "content": content}}}


class _FakeBedrock:
    """converse() 를 흉내낸다. 요청과 호출 스레드를 기록한다."""

    def __init__(self, text: str = '"a": 1}') -> None:
        self.text = text
        self.requests: list[dict[str, Any]] = []
        self.threads: set[str] = set()
        self.barrier: threading.Barrier | None = None

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        self.threads.add(threading.current_thread().name)
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        return _response(self.text)


def _client(fake: _FakeBedrock, **kwargs: Any) -> BedrockJsonClient:
    client = BedrockJsonClient(model="global.anthropic.claude-haiku-4-5-20251001-v1:0", **kwargs)
    client._client = fake
    return client


class ExtractTextTest(unittest.TestCase):
    def test_skips_reasoning_blocks(self) -> None:
        self.assertEqual(_extract_bedrock_text(_response('"a": 1}', with_reasoning=True)), '"a": 1}')

    def test_raises_when_no_text_block(self) -> None:
        with self.assertRaises(RuntimeError):
            _extract_bedrock_text({"output": {"message": {"content": []}}})


class RequestShapeTest(unittest.IsolatedAsyncioTestCase):
    async def test_prefill_is_sent_and_reattached(self) -> None:
        fake = _FakeBedrock('"a": 1}')
        result = await _client(fake).generate_json(prompt="P", temperature=0.0)
        self.assertEqual(result, {"a": 1})
        messages = fake.requests[0]["messages"]
        self.assertEqual(messages[0], {"role": "user", "content": [{"text": "P"}]})
        self.assertEqual(messages[1], {"role": "assistant", "content": [{"text": "{"}]})

    async def test_model_echoing_the_brace_is_not_double_prefixed(self) -> None:
        """프리필을 무시하고 완전한 JSON 을 돌려주는 모델이 있다.

        무조건 "{" 를 앞에 붙이면 "{{...}" 가 되어 파싱이 깨진다.
        """
        fake = _FakeBedrock('{"a": 1}')
        self.assertEqual(await _client(fake).generate_json(prompt="P"), {"a": 1})

    async def test_prefill_can_be_disabled(self) -> None:
        fake = _FakeBedrock('{"a": 1}')
        await _client(fake, use_json_prefill=False).generate_json(prompt="P")
        self.assertEqual(len(fake.requests[0]["messages"]), 1)

    async def test_thinking_is_never_sent(self) -> None:
        """thinking 을 켜면 Bedrock 이 temperature 를 1로 강제한다.

        현행 0.0/0.1 설정의 결정성이 validate_hard_facts_by_code 의 전제라
        Bedrock 경로에서는 항상 OFF 다.
        """
        fake = _FakeBedrock()
        client = _client(fake)
        await client.generate_json(prompt="P", temperature=0.0, thinking_budget=0)
        with self.assertLogs("app.translation.bedrock_client", level="WARNING") as logs:
            await client.generate_json(prompt="P", temperature=0.0, thinking_budget=4096)
        self.assertTrue(any("thinking" in line for line in logs.output))
        for request in fake.requests:
            self.assertNotIn("additionalModelRequestFields", request)
            self.assertEqual(request["inferenceConfig"]["temperature"], 0.0)

    async def test_model_override_wins(self) -> None:
        fake = _FakeBedrock()
        client = _client(fake, source_hard_fact_model="apac.anthropic.claude-3-haiku-20240307-v1:0")
        await client.generate_json(prompt="P", model=client.source_hard_fact_model)
        self.assertEqual(fake.requests[0]["modelId"], "apac.anthropic.claude-3-haiku-20240307-v1:0")


class ExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_calls_run_on_the_clients_own_threads(self) -> None:
        """asyncio 기본 executor 는 워커(--cpu=1)에서 5개라 조용히 직렬화된다.

        전용 풀이 있으면 8개가 동시에 안에 들어가야 한다.
        """
        fake = _FakeBedrock()
        fake.barrier = threading.Barrier(8)
        client = _client(fake, max_workers=8)
        await asyncio.gather(*(client.generate_json(prompt=f"P{i}") for i in range(8)))
        self.assertEqual(len(fake.requests), 8)
        self.assertTrue(all(name.startswith("bedrock") for name in fake.threads), fake.threads)


class FromSettingsTest(unittest.TestCase):
    def test_reads_settings(self) -> None:
        settings = Settings(
            TRANSLATION_BACKEND="bedrock",
            BEDROCK_TRANSLATION_MODEL="global.anthropic.claude-sonnet-4-6",
            BEDROCK_MECHANICAL_MODEL="global.anthropic.claude-haiku-4-5-20251001-v1:0",
            GEMINI_MAX_CONCURRENCY=16,
        )
        client = BedrockJsonClient.from_settings(settings)
        self.assertEqual(client.model, "global.anthropic.claude-sonnet-4-6")
        self.assertEqual(client.source_hard_fact_model, "global.anthropic.claude-haiku-4-5-20251001-v1:0")
        self.assertEqual(client.region, "ap-northeast-2")

    def test_mechanical_model_defaults_to_translation_model(self) -> None:
        client = BedrockJsonClient.from_settings(Settings(TRANSLATION_BACKEND="bedrock"))
        self.assertEqual(client.source_hard_fact_model, client.model)


if __name__ == "__main__":
    unittest.main()
