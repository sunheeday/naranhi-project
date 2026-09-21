import asyncio
import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.translation.orchestrator import TranslationPipeline

from backend.tests.test_orchestrator_parallel_thinking import (
    _MATCHING_HARD_FACTS,
    _payload_input,
    _RecordingGemini,
)

_NON_MECHANICAL = {"pivot", "target", "tone", "payload"}


def _clean_run(**settings_kwargs) -> _RecordingGemini:
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
    settings = Settings(**settings_kwargs)
    with patch("app.translation.orchestrator.get_settings", return_value=settings):
        asyncio.run(TranslationPipeline(gemini).run(_payload_input()))
    return gemini


class ThinkingBudgetSettingTest(unittest.TestCase):
    def test_default_is_thinking_off(self) -> None:
        """기본값 0 — thinking 은 쓰지 않는다(사용자 지시).

        Bedrock 경로는 thinking 을 애초에 보내지 않으므로 이 값은 Gemini 폴백에만
        영향을 준다. 전면 off 로 hard_fact 가 무너졌던 arm-b 실측은 코드 검사가
        없던 조건이었고, 지금은 validate_output_by_code 가 한글잔존·잘림·구조·반복을
        AI 없이 먼저 잡는다."""
        gemini = _clean_run()
        self.assertTrue(gemini.calls)
        for call in gemini.calls:
            self.assertEqual(call["thinking_budget"], 0, call["kind"])

    def test_explicit_none_restores_model_default(self) -> None:
        """되돌리려면 env 한 줄이다 — 코드 revert 가 필요 없다."""
        gemini = _clean_run(TRANSLATION_THINKING_BUDGET=None)
        self.assertTrue(gemini.calls)
        for call in gemini.calls:
            if call["kind"] in _NON_MECHANICAL:
                self.assertIsNone(call["thinking_budget"], call["kind"])

    def test_setting_zero_turns_thinking_off_everywhere(self) -> None:
        """TRANSLATION_THINKING_BUDGET=0 이면 번역·검증·카드 단계도 전부 0."""
        gemini = _clean_run(TRANSLATION_THINKING_BUDGET=0)
        self.assertTrue(gemini.calls)
        for call in gemini.calls:
            self.assertEqual(call["thinking_budget"], 0, call["kind"])


if __name__ == "__main__":
    unittest.main()
