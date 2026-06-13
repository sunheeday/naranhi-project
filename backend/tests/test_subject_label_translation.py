import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services.notice_service import NoticeService
from app.translation.prompts import translate_subject_labels_prompt


class SubjectLabelTranslationPromptTest(unittest.TestCase):
    def test_prompt_contains_subject_specific_contract(self):
        prompt = translate_subject_labels_prompt(
            target_language="en",
            items=[
                {"id": "S001", "text": "국어"},
                {"id": "S002", "text": "창의적 체험활동"},
            ],
        )

        self.assertIn("school timetable subject and activity labels", prompt)
        self.assertIn("국어 is the Korean language subject", prompt)
        self.assertIn("한국사 is Korean history specifically", prompt)
        self.assertIn("secular, civic/ethics wording", prompt)
        self.assertIn("Keep 사회 (general social studies) and 통합사회", prompt)
        self.assertIn('"id": ""', prompt)
        self.assertIn('"translation": ""', prompt)

    def test_prompt_includes_arabic_secular_rule(self):
        prompt = translate_subject_labels_prompt(
            target_language="ar",
            items=[{"id": "S001", "text": "도덕"}],
        )

        self.assertIn("Arabic subject-label rules", prompt)
        self.assertIn("definite article", prompt)
        self.assertIn("التربية الإسلامية", prompt)

    def test_prompt_includes_chinese_kukeo_rule(self):
        prompt = translate_subject_labels_prompt(
            target_language="zh",
            items=[{"id": "S001", "text": "국어"}],
        )

        self.assertIn("Simplified Chinese subject-label rules", prompt)
        self.assertIn("韩国语", prompt)
        self.assertIn("语文", prompt)


class SubjectLabelTranslationServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_translate_text_subject_labels_returns_structured_mapping(self):
        service = NoticeService()
        settings = Mock(gemini_configured=True, gemini_key_material="dummy")
        gemini = Mock()
        gemini.generate_json = AsyncMock(
            return_value={
                "items": [
                    {"id": "S001", "translation": "Korean"},
                    {"id": "S002", "translation": "Creative Experiential Activities"},
                ]
            }
        )

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.GeminiJsonClient.from_settings", return_value=gemini),
        ):
            result = await service.translate_text(
                source_text="# 시간표 과목 번역 항목\n[[S001]] 국어\n[[S002]] 창의적 체험활동\n",
                target_language="en",
                translation_kind="subject_labels",
            )

        self.assertEqual(result["status"], "ready_to_save")
        self.assertEqual(
            result["translations"],
            {
                "S001": "Korean",
                "S002": "Creative Experiential Activities",
            },
        )
        self.assertIn("[[S001]] Korean", result["translation"])
        self.assertIn("[[S002]] Creative Experiential Activities", result["translation"])

    async def test_translate_text_subject_labels_falls_back_to_original_when_item_missing(self):
        service = NoticeService()
        settings = Mock(gemini_configured=True, gemini_key_material="dummy")
        gemini = Mock()
        gemini.generate_json = AsyncMock(
            return_value={
                "items": [
                    {"id": "S001", "translation": "Math"},
                ]
            }
        )

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.GeminiJsonClient.from_settings", return_value=gemini),
        ):
            result = await service.translate_text(
                source_text="# 시간표 과목 번역 항목\n[[S001]] 수학\n[[S002]] 해양과학탐구\n",
                target_language="en",
                translation_kind="subject_labels",
            )

        self.assertEqual(
            result["translations"],
            {
                "S001": "Math",
                "S002": "해양과학탐구",
            },
        )


if __name__ == "__main__":
    unittest.main()
