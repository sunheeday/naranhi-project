import asyncio
import unittest
from typing import Any

from app.translation.orchestrator import (
    MECHANICAL_THINKING_BUDGET,
    TranslationPipeline,
    TranslationPipelineInput,
)


def _classify(prompt: str) -> str:
    """프롬프트 본문에서 파이프라인 단계 종류를 식별한다 (마커는 고유성 검증됨)."""
    if "Extract and normalize verifiable hard facts" in prompt:
        return "source_hf"
    if "MEAL_TEXT" in prompt:
        return "ingredient"
    if "corrected_target_translation" in prompt and "FAIL_FIXABLE" not in prompt:
        return "hf_fix" if "mismatches" in prompt else "tone_fix"
    if "translated_hard_facts" in prompt:
        return "hf_validate"
    if "FAIL_FIXABLE" in prompt:
        return "tone"
    if '"back_translation_ko"' in prompt:
        return "back"
    if '"pivot_translation_en"' in prompt:
        return "pivot"
    if "card_sections" in prompt:
        return "payload"
    if '"target_translation"' in prompt:
        return "target"
    return "target_hf"


_MATCHING_HARD_FACTS = {
    "hard_facts": {
        "deadlines": [{"raw_text": "6월 10일", "normalized": "2026-06-10"}],
        "actions_required": [{"raw_text": "신청서 제출"}],
    },
}


class _RecordingGemini:
    """단계별 canned 응답을 돌려주며 호출 종류·thinking_budget·프롬프트를 기록한다."""

    source_hard_fact_model = None

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def generate_json(
        self,
        *,
        prompt: str,
        temperature: float = 0.0,
        model: str | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        kind = _classify(prompt)
        self.calls.append(
            {"kind": kind, "prompt": prompt, "thinking_budget": thinking_budget}
        )
        value = self.responses[kind]
        if callable(value):
            return value(prompt)
        if isinstance(value, list):
            return value.pop(0)
        return value

    def kinds(self) -> list[str]:
        return [call["kind"] for call in self.calls]

    def calls_of(self, kind: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call["kind"] == kind]


def _payload_input(**overrides: Any) -> TranslationPipelineInput:
    kwargs: dict[str, Any] = {
        "source_text": "6월 10일까지 신청서를 제출하세요.",
        "target_language": "en",
        "approved_ingredient_dictionary": [],
        "approved_ingredient_dictionary_target": [],
        "max_target_hard_fact_extraction_attempts": 1,
    }
    kwargs.update(overrides)
    return TranslationPipelineInput(**kwargs)


class OrchestratorThinkingBudgetTest(unittest.TestCase):
    def _run_clean_high_risk(self) -> tuple[dict[str, Any], _RecordingGemini]:
        gemini = _RecordingGemini(
            {
                "source_hf": _MATCHING_HARD_FACTS,
                "pivot": {"pivot_translation_en": "Notice EN"},
                "target": {"target_translation": "Translated body"},
                "target_hf": _MATCHING_HARD_FACTS,
                "back": {"back_translation_ko": "역번역"},
                "tone": {"verdict": "PASS", "issues": []},
                "payload": {"title": "안내", "validation_status": "passed"},
            }
        )
        result = asyncio.run(TranslationPipeline(gemini).run(_payload_input()))
        return result, gemini

    def test_mechanical_steps_disable_thinking_and_others_keep_default(self) -> None:
        result, gemini = self._run_clean_high_risk()

        self.assertEqual(result["status"], "ready_to_save")
        budget_by_kind = {
            call["kind"]: call["thinking_budget"] for call in gemini.calls
        }
        # 기계적 단계(①④⑤)만 thinking 차단
        self.assertEqual(budget_by_kind["source_hf"], MECHANICAL_THINKING_BUDGET)
        self.assertEqual(budget_by_kind["target_hf"], MECHANICAL_THINKING_BUDGET)
        self.assertEqual(budget_by_kind["back"], MECHANICAL_THINKING_BUDGET)
        # 번역·검증·카드 단계(②③⑥⑦)는 설정값을 따른다 — 기본값 None = 모델 기본(동적 thinking)
        self.assertIsNone(budget_by_kind["pivot"])
        self.assertIsNone(budget_by_kind["target"])
        self.assertIsNone(budget_by_kind["tone"])
        self.assertIsNone(budget_by_kind["payload"])

    def test_clean_pass_reuses_prestarted_back_translation_once(self) -> None:
        result, gemini = self._run_clean_high_risk()

        back_calls = gemini.calls_of("back")
        self.assertEqual(len(back_calls), 1)
        self.assertIn("Translated body", back_calls[0]["prompt"])
        self.assertEqual(
            result["raw_steps"]["back_translation"], {"back_translation_ko": "역번역"}
        )

    def test_fix_loop_discards_stale_back_translation_and_redoes_with_corrected_text(
        self,
    ) -> None:
        def back_response(prompt: str) -> dict[str, Any]:
            marker = "corrected" if "Corrected body" in prompt else "original"
            return {"back_translation_ko": f"BACK::{marker}"}

        gemini = _RecordingGemini(
            {
                "source_hf": _MATCHING_HARD_FACTS,
                "pivot": {"pivot_translation_en": "Notice EN"},
                "target": {"target_translation": "Translated body"},
                # 1차 추출은 마감일 누락(코드 검증 FAIL 유도), 수정 후 2차는 일치
                "target_hf": [{"hard_facts": {}}, _MATCHING_HARD_FACTS],
                "hf_validate": {"verdict": "FAIL", "mismatches": []},
                "hf_fix": {"corrected_target_translation": "Corrected body"},
                "back": back_response,
                "tone": {"verdict": "PASS", "issues": []},
                "payload": {"title": "안내", "validation_status": "passed"},
            }
        )

        result = asyncio.run(TranslationPipeline(gemini).run(_payload_input()))

        self.assertEqual(result["status"], "ready_to_save")
        self.assertEqual(result["final_translation"], "Corrected body")
        # 미리 띄운 역번역(원본 기준)은 시작 전에 취소돼 기록되지 않고,
        # 수정된 번역으로 새 역번역 1회만 실행된다.
        back_calls = gemini.calls_of("back")
        self.assertEqual(len(back_calls), 1)
        self.assertIn("Corrected body", back_calls[0]["prompt"])
        self.assertEqual(
            result["raw_steps"]["back_translation"],
            {"back_translation_ko": "BACK::corrected"},
        )

    def test_low_risk_does_not_start_back_translation(self) -> None:
        gemini = _RecordingGemini(
            {
                "source_hf": {"hard_facts": {"dates": [{"raw_text": "다음 주 월요일"}]}},
                "pivot": {"pivot_translation_en": "Notice EN"},
                "target": {"target_translation": "Translated body"},
                "target_hf": {"hard_facts": {"dates": [{"raw_text": "next Monday"}]}},
                "payload": {"title": "안내", "validation_status": "passed"},
            }
        )

        result = asyncio.run(
            TranslationPipeline(gemini).run(
                _payload_input(source_text="다음 주 월요일은 재량휴업일입니다.")
            )
        )

        self.assertEqual(result["status"], "ready_to_save")
        self.assertEqual(gemini.calls_of("back"), [])
        self.assertEqual(gemini.calls_of("tone"), [])

    def test_validation_failed_early_return_discards_pending_back_translation(self) -> None:
        gemini = _RecordingGemini(
            {
                "source_hf": _MATCHING_HARD_FACTS,
                "pivot": {"pivot_translation_en": "Notice EN"},
                "target": {"target_translation": "Translated body"},
                # 추출이 계속 마감일을 놓침 → 수정 루프 소진 → 검증실패 경로
                "target_hf": {"hard_facts": {}},
                "hf_validate": {"verdict": "FAIL", "mismatches": []},
                "hf_fix": {"corrected_target_translation": "Corrected body"},
                "back": {"back_translation_ko": "역번역"},
                "payload": {"title": "안내", "validation_status": "passed"},
            }
        )

        result = asyncio.run(TranslationPipeline(gemini).run(_payload_input()))

        self.assertEqual(result["status"], "ready_to_save")
        self.assertEqual(
            result["metadata"]["validation_failure_reason"], "hard_fact_validation_failed"
        )
        # 검증실패로 조기 반환할 때 미리 띄운 역번역은 실행되지 않아야 한다.
        self.assertEqual(gemini.calls_of("back"), [])


if __name__ == "__main__":
    unittest.main()
