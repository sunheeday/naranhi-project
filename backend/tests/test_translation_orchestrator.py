import unittest
import asyncio
from unittest.mock import AsyncMock

from app.translation.orchestrator import (
    TranslationPipeline,
    TranslationPipelineInput,
    _validation_status,
)


class TranslationOrchestratorTest(unittest.TestCase):
    def test_validation_status_preserves_skipped(self):
        self.assertEqual(
            _validation_status({"status": "skipped", "issues": []}),
            "skipped",
        )

    def test_validation_status_uses_verdict_when_status_missing(self):
        self.assertEqual(_validation_status({"verdict": "PASS"}), "passed")
        self.assertEqual(_validation_status({"verdict": "FAIL"}), "failed")

    def test_source_hard_fact_extraction_uses_dedicated_model_override(self):
        gemini = type(
            "FakeGemini",
            (),
            {
                "source_hard_fact_model": "gemini-2.5-pro",
                "generate_json": AsyncMock(
                    side_effect=[
                        {"hard_facts": {}},
                        {
                            "mapped_ingredients": [],
                            "unmapped_ingredients": [],
                            "critical_flags": {
                                "contains_allergen": False,
                                "contains_religious_restriction_item": False,
                                "contains_unmapped_critical_item": False,
                            },
                        },
                        {"pivot_translation_en": "Notice"},
                        {"target_translation": "Notice"},
                        {"hard_facts": {}},
                        {"back_translation_ko": "안내문"},
                        {"verdict": "PASS", "issues": []},
                        {"title": "안내문", "validation_status": "passed"},
                    ]
                ),
            },
        )()

        result = asyncio.run(
            TranslationPipeline(gemini).run(
                TranslationPipelineInput(
                    source_text="작성일 2026.05.22\n행사일 2026.05.30",
                    target_language="en",
                    approved_ingredient_dictionary=[],
                    approved_ingredient_dictionary_target=[],
                )
            )
        )

        self.assertEqual(result["status"], "ready_to_save")
        first_call = gemini.generate_json.await_args_list[0]
        self.assertEqual(first_call.kwargs["model"], "gemini-2.5-pro")


if __name__ == "__main__":
    unittest.main()
