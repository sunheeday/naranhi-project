import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.notice_service import NoticeService


def _fake_gemini(payload_response):
    """첫 콜은 간이번역, 두 번째 콜은 카드 메타데이터 페이로드를 돌려주는 가짜."""

    async def generate_json(*, prompt, temperature, model=None):
        if generate_json.calls == 0:
            generate_json.calls += 1
            return {
                "target_translation": "Translated body",
                "title": "Fallback title",
            }
        generate_json.calls += 1
        if isinstance(payload_response, Exception):
            raise payload_response
        return payload_response

    generate_json.calls = 0
    return SimpleNamespace(generate_json=AsyncMock(side_effect=generate_json))


class BestEffortFallbackMetadataTest(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_generates_card_metadata(self) -> None:
        gemini = _fake_gemini(
            {
                "title": "Generated title",
                "title_target_language": "Generated title",
                "summary_ko": "요약",
                "card_sections": {
                    "action": {"items": [{"text": "Submit the consent form"}]},
                },
            }
        )

        result = await NoticeService()._best_effort_translate_notice(
            gemini=gemini,
            notice={},
            target_language="en",
            source_text="한국어 원문",
        )

        metadata = result["metadata"]
        self.assertEqual(result["final_translation"], "Translated body")
        self.assertEqual(
            metadata["card_sections"]["action"]["items"][0]["text"],
            "Submit the consent form",
        )
        # 폴백 마커는 생성된 페이로드보다 우선해야 한다.
        self.assertEqual(metadata["fallback_mode"], "quota_best_effort")
        self.assertEqual(metadata["validation_failure_reason"], "quota_best_effort_fallback")
        # 간이번역이 돌려준 제목이 생성된 제목을 이긴다.
        self.assertEqual(metadata["title"], "Fallback title")
        self.assertEqual(gemini.generate_json.await_count, 2)

    async def test_fallback_survives_metadata_generation_failure(self) -> None:
        gemini = _fake_gemini(RuntimeError("429 RESOURCE_EXHAUSTED"))

        result = await NoticeService()._best_effort_translate_notice(
            gemini=gemini,
            notice={},
            target_language="en",
            source_text="한국어 원문",
        )

        metadata = result["metadata"]
        self.assertEqual(result["final_translation"], "Translated body")
        self.assertEqual(metadata["fallback_mode"], "quota_best_effort")
        self.assertNotIn("card_sections", metadata)

    async def test_generated_title_used_when_fallback_title_missing(self) -> None:
        async def generate_json(*, prompt, temperature, model=None):
            if generate_json.calls == 0:
                generate_json.calls += 1
                return {"target_translation": "Translated body"}
            generate_json.calls += 1
            return {"title": "Generated title", "title_target_language": "Generated title"}

        generate_json.calls = 0
        gemini = SimpleNamespace(generate_json=AsyncMock(side_effect=generate_json))

        result = await NoticeService()._best_effort_translate_notice(
            gemini=gemini,
            notice={},
            target_language="en",
            source_text="한국어 원문",
        )

        self.assertEqual(result["metadata"]["title"], "Generated title")


if __name__ == "__main__":
    unittest.main()
