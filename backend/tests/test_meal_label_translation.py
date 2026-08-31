import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services.notice_service import NoticeService, _parse_meal_label_source_text
from app.translation.prompts import translate_meal_labels_prompt


class MealLabelTranslationPromptTest(unittest.TestCase):
    def test_translate_meal_labels_prompt_contains_meal_specific_contract(self):
        prompt = translate_meal_labels_prompt(
            target_language="en",
            items=[
                {"id": "M001", "text": "기장밥"},
                {"id": "M002", "text": "*오쭈낙볶음"},
            ],
        )

        self.assertIn("short Korean school meal labels", prompt)
        self.assertIn("Do not preserve Korean menu labels unchanged", prompt)
        self.assertIn("Preserve leading or trailing symbols exactly", prompt)
        self.assertIn("Do not leave Korean food words as Hangul, romanization, or transliteration", prompt)
        self.assertIn("keep all of those named components in the translation", prompt)
        self.assertIn('"id": ""', prompt)
        self.assertIn('"translation": ""', prompt)

    def test_translate_meal_labels_prompt_includes_russian_menu_rules(self):
        prompt = translate_meal_labels_prompt(
            target_language="ru",
            items=[{"id": "M001", "text": "기장밥"}],
        )

        self.assertIn("Russian meal-label rules", prompt)
        self.assertIn("`рис с ...`", prompt)
        self.assertIn("`пшенной рис`", prompt)

    def test_parse_meal_label_source_text_extracts_marker_rows(self):
        items = _parse_meal_label_source_text(
            "# 급식 번역 항목\n"
            "[[M001]] 기장밥\n"
            "[[M002]] *오쭈낙볶음\n"
            "[[M003]] 깍두기 (9)\n"
        )

        self.assertEqual(
            items,
            [
                {"id": "M001", "text": "기장밥"},
                {"id": "M002", "text": "*오쭈낙볶음"},
                {"id": "M003", "text": "깍두기 (9)"},
            ],
        )


class MealLabelTranslationServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_translate_text_meal_labels_returns_structured_mapping(self):
        service = NoticeService()
        settings = Mock(gemini_configured=True, gemini_key_material="dummy")
        gemini = Mock()
        gemini.generate_json = AsyncMock(
            return_value={
                "items": [
                    {"id": "M001", "translation": "Millet Rice"},
                    {"id": "M002", "translation": "*Stir-Fried Baby Octopus, Webfoot Octopus, and Squid"},
                ]
            }
        )

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.build_json_client", return_value=gemini),
        ):
            result = await service.translate_text(
                source_text="# 급식 번역 항목\n[[M001]] 기장밥\n[[M002]] *오쭈낙볶음\n",
                target_language="en",
                translation_kind="meal_labels",
            )

        self.assertEqual(result["status"], "ready_to_save")
        self.assertEqual(
            result["translations"],
            {
                "M001": "Millet Rice",
                "M002": "*Stir-Fried Baby Octopus, Webfoot Octopus, and Squid",
            },
        )
        self.assertIn("[[M001]] Millet Rice", result["translation"])
        self.assertIn(
            "[[M002]] *Stir-Fried Baby Octopus, Webfoot Octopus, and Squid",
            result["translation"],
        )

    async def test_translate_text_meal_labels_falls_back_to_original_when_item_missing(self):
        service = NoticeService()
        settings = Mock(gemini_configured=True, gemini_key_material="dummy")
        gemini = Mock()
        gemini.generate_json = AsyncMock(
            return_value={
                "items": [
                    {"id": "M001", "translation": "Radish Kimchi (9)"},
                ]
            }
        )

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.build_json_client", return_value=gemini),
        ):
            result = await service.translate_text(
                source_text="# 급식 번역 항목\n[[M001]] 깍두기 (9)\n[[M002]] 한방닭곰탕\n",
                target_language="en",
                translation_kind="meal_labels",
            )

        self.assertEqual(
            result["translations"],
            {
                "M001": "Radish Kimchi (9)",
                "M002": "한방닭곰탕",
            },
        )


if __name__ == "__main__":
    unittest.main()
