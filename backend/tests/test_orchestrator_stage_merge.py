import asyncio
import unittest

from app.translation.orchestrator import TranslationPipeline

from backend.tests.test_orchestrator_parallel_thinking import (
    _MATCHING_HARD_FACTS,
    _payload_input,
    _RecordingGemini,
)


class _OrderedGemini(_RecordingGemini):
    """호출 시작 시각을 재서 동시 실행을 판별한다."""

    def __init__(self, responses) -> None:
        super().__init__(responses)
        self.started: list[str] = []
        self.finished: list[str] = []

    async def generate_json(self, **kwargs):
        kind_probe = len(self.calls)
        result = None
        # 시작 기록은 부모 호출 전에 해야 순서가 보인다 — 부모가 kind 를 계산하므로
        # 여기서는 프롬프트로 직접 분류한다.
        from backend.tests.test_orchestrator_parallel_thinking import _classify

        kind = _classify(kwargs["prompt"])
        self.started.append(kind)
        await asyncio.sleep(0)
        result = await super().generate_json(**kwargs)
        self.finished.append(kind)
        del kind_probe
        return result


def _responses() -> dict:
    meal_facts = dict(_MATCHING_HARD_FACTS)
    meal_facts["meal_and_allergy"] = {"has_meal_info": True, "ingredients_raw": ["우유"], "menu_items_raw": ["급식"]}
    return {
        "source_hf": meal_facts,
        "ingredient": {"mapped_ingredients": [], "unmapped_ingredients": [], "critical_flags": {}},
        "pivot": {"pivot_translation_en": "Notice EN"},
        "target": {"target_translation": "Translated body"},
        "target_hf": _MATCHING_HARD_FACTS,
        "back": {"back_translation_ko": "역번역"},
        "tone": {"verdict": "PASS", "issues": []},
        "payload": {"title": "안내", "validation_status": "passed"},
    }


class StageMergeTest(unittest.TestCase):
    def test_m1_source_hard_facts_and_ingredient_map_start_together(self) -> None:
        """둘 다 source_text 만 읽는다. 순차로 돌 이유가 없다."""
        gemini = _OrderedGemini(_responses())
        asyncio.run(TranslationPipeline(gemini).run(_payload_input(source_text="급식 안내. 6월 10일까지 신청서를 제출하세요.")))
        first_two = gemini.started[:2]
        self.assertCountEqual(first_two, ["source_hf", "ingredient"], gemini.started)

    def test_m2_card_metadata_starts_before_tone_validation_finishes(self) -> None:
        """카드 메타데이터는 최종 번역문만 필요하고 검증 결과와 무관하다."""
        gemini = _OrderedGemini(_responses())
        asyncio.run(TranslationPipeline(gemini).run(_payload_input(source_text="급식 안내. 6월 10일까지 신청서를 제출하세요.")))
        self.assertIn("payload", gemini.started)
        self.assertIn("tone", gemini.finished)
        self.assertLess(
            gemini.started.index("payload"),
            gemini.finished.index("tone"),
            f"started={gemini.started} finished={gemini.finished}",
        )

    def test_card_metadata_is_generated_exactly_once_on_clean_pass(self) -> None:
        """투기 실행이 중복 콜을 만들면 안 된다."""
        gemini = _OrderedGemini(_responses())
        result = asyncio.run(
            TranslationPipeline(gemini).run(_payload_input(source_text="급식 안내. 6월 10일까지 신청서를 제출하세요."))
        )
        self.assertEqual(len(gemini.calls_of("payload")), 1)
        self.assertEqual(result["metadata"]["title"], "안내")

    def test_card_metadata_is_redone_when_tone_fix_changes_the_translation(self) -> None:
        """자동수정 루프가 번역문을 바꾸면 미리 띄운 카드는 버리고 새로 돈다.

        미리 띄운 카드 콜은 검증(tone)과 진짜로 동시에 나간다 — 그래서 검증이
        FAIL_FIXABLE 을 돌려줄 때 이미 응답이 와 있을 수도 있다(계획서 §7 Step 7이
        스스로 인정한 부분: "자동수정 루프에서 콜이 늘 수는 있다(투기 폐기 + 재실행
        = 2콜)"). 여기서 반드시 지켜야 하는 것은 호출 횟수가 아니라 **최종적으로
        쓰이는 카드가 고쳐진 번역문 기준이라는 것** — 버려진 콜의 결과가 새어나가
        오래된(stale) 카드가 저장되면 안 된다.
        """
        responses = _responses()
        responses["tone"] = [
            {"verdict": "FAIL_FIXABLE", "issues": [{"severity": "high"}]},
            {"verdict": "PASS", "issues": []},
        ]
        responses["tone_fix"] = {"corrected_target_translation": "Corrected body"}
        gemini = _OrderedGemini(responses)
        result = asyncio.run(
            TranslationPipeline(gemini).run(_payload_input(source_text="급식 안내. 6월 10일까지 신청서를 제출하세요."))
        )
        payload_calls = gemini.calls_of("payload")
        self.assertIn(len(payload_calls), (1, 2), payload_calls)
        self.assertIn("Corrected body", payload_calls[-1]["prompt"])
        self.assertEqual(result["final_translation"], "Corrected body")


if __name__ == "__main__":
    unittest.main()
