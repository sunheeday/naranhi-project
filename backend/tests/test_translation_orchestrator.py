import unittest
import asyncio
from unittest.mock import AsyncMock

from app.translation.orchestrator import (
    TranslationPipeline,
    TranslationPipelineInput,
    _risk_profile_from_source,
    _validation_status,
)


class TranslationOrchestratorTest(unittest.TestCase):
    def test_risk_profile_marks_simple_notice_low_risk(self):
        profile = _risk_profile_from_source(
            source_text="다음 주 월요일은 재량휴업일입니다.",
            source_hard_facts={"hard_facts": {"dates": [{"raw_text": "다음 주 월요일"}]}},
        )

        self.assertEqual(profile["level"], "low")

    def test_risk_profile_marks_action_deadline_notice_high_risk(self):
        profile = _risk_profile_from_source(
            source_text="6월 10일까지 신청서를 제출하세요.",
            source_hard_facts={
                "hard_facts": {
                    "deadlines": [{"raw_text": "6월 10일", "normalized": "2026-06-10"}],
                    "actions_required": [{"raw_text": "신청서 제출"}],
                },
            },
        )

        self.assertEqual(profile["level"], "high")
        self.assertIn("has_deadlines", profile["reasons"])

    def test_risk_profile_keeps_simple_action_notice_low_risk(self):
        profile = _risk_profile_from_source(
            source_text="체험학습 당일 모자와 물을 준비해 주세요.",
            source_hard_facts={
                "hard_facts": {
                    "actions_required": [{"raw_text": "모자와 물 준비"}],
                    "materials": [{"raw_text": "모자"}, {"raw_text": "물"}],
                },
            },
        )

        self.assertEqual(profile["level"], "low")

    def test_risk_profile_marks_submission_notice_high_risk(self):
        profile = _risk_profile_from_source(
            source_text="참가 동의서를 작성해서 보내주세요.",
            source_hard_facts={
                "hard_facts": {
                    "submissions": [{"raw_text": "참가 동의서"}],
                    "actions_required": [{"raw_text": "참가 동의서 제출"}],
                },
            },
        )

        self.assertEqual(profile["level"], "high")
        self.assertIn("has_submissions", profile["reasons"])

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

    def test_low_risk_notice_skips_back_translation_and_context_tone(self):
        gemini = type(
            "FakeGemini",
            (),
            {
                "source_hard_fact_model": "gemini-2.5-pro",
                "generate_json": AsyncMock(
                    side_effect=[
                        {"hard_facts": {"dates": [{"raw_text": "다음 주 월요일"}]}},
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
                        {"hard_facts": {"dates": [{"raw_text": "next Monday"}]}},
                        {"title": "안내문", "validation_status": "passed"},
                    ]
                ),
            },
        )()

        result = asyncio.run(
            TranslationPipeline(gemini).run(
                TranslationPipelineInput(
                    source_text="다음 주 월요일은 재량휴업일입니다.",
                    target_language="en",
                    approved_ingredient_dictionary=[],
                    approved_ingredient_dictionary_target=[],
                )
            )
        )

        self.assertEqual(result["status"], "ready_to_save")
        self.assertEqual(result["validation"]["context_tone"]["status"], "skipped")
        self.assertNotIn("back_translation", result["raw_steps"])
        self.assertEqual(len(gemini.generate_json.await_args_list), 6)


if __name__ == "__main__":
    unittest.main()
