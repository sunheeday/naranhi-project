import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.notice_service import NoticeService


def _fake_gemini():
    """첫 콜은 간이번역, 이후 콜은 카드 메타데이터 페이로드."""

    async def generate_json(*, prompt, temperature, model=None, thinking_budget=None):
        if generate_json.calls == 0:
            generate_json.calls += 1
            return {"target_translation": "Translated body", "title": "Fallback title"}
        generate_json.calls += 1
        return {"title": "Generated title", "card_sections": {}}

    generate_json.calls = 0
    return SimpleNamespace(generate_json=AsyncMock(side_effect=generate_json))


class BestEffortCardMetadataFlagTest(unittest.IsolatedAsyncioTestCase):
    async def test_default_still_generates_card_metadata(self) -> None:
        """쿼터 폴백 경로(notice_service:173, :302)는 카드가 비면 앱이 무한 재요청한다.

        그래서 기본값은 True 여야 한다.
        """
        gemini = _fake_gemini()
        result = await NoticeService()._best_effort_translate_notice(
            gemini=gemini,
            notice={},
            target_language="en",
            source_text="한국어 원문",
        )
        self.assertEqual(gemini.generate_json.await_count, 2)
        self.assertIn("card_sections", result["metadata"])

    async def test_flag_off_skips_the_metadata_call(self) -> None:
        """요약·본문 소스 번역(notice_service:249)은 pipeline_result 를 버린다.

        메타데이터 콜은 그대로 낭비이므로 끈다.
        """
        gemini = _fake_gemini()
        result = await NoticeService()._best_effort_translate_notice(
            gemini=gemini,
            notice={},
            target_language="en",
            source_text="한국어 원문",
            with_card_metadata=False,
        )
        self.assertEqual(gemini.generate_json.await_count, 1)
        self.assertEqual(result["final_translation"], "Translated body")
        self.assertNotIn("card_sections", result["metadata"])
        # 폴백 마커와 제목은 메타데이터 콜 없이도 남아야 한다.
        self.assertEqual(result["metadata"]["fallback_mode"], "quota_best_effort")
        self.assertEqual(result["metadata"]["title"], "Fallback title")


if __name__ == "__main__":
    unittest.main()
