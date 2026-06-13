import unittest

from app.services.notice_service import (
    _MAX_ACTION_CARD_ITEMS,
    _canonical_action_card_items,
    _submission_already_in_actions,
    _translated_card_content_for_type,
)


class ActionCardCapTest(unittest.TestCase):
    def test_korean_card_from_hard_facts_capped_at_five(self):
        source_facts = {
            "actions_required": [{"raw_text": f"할일 {i}"} for i in range(1, 8)],
            "deadlines": [{"raw_text": "2026.06.30."}],
        }

        items = _canonical_action_card_items(source_facts=source_facts, metadata={})

        self.assertEqual(len(items), _MAX_ACTION_CARD_ITEMS)
        self.assertEqual(items[0]["text"], "할일 1")
        self.assertEqual(items[-1]["text"], "할일 5")

    def test_korean_card_under_cap_is_unchanged(self):
        source_facts = {
            "actions_required": [{"raw_text": "동의서 제출"}, {"raw_text": "도시락 준비"}],
        }

        items = _canonical_action_card_items(source_facts=source_facts, metadata={})

        self.assertEqual([item["text"] for item in items], ["동의서 제출", "도시락 준비"])

    def test_translated_action_card_capped_at_five(self):
        pipeline_result = {
            "metadata": {
                "card_sections_target_language": {
                    "action": {
                        "items": [{"text": f"task {i}"} for i in range(1, 9)],
                    },
                },
            },
        }

        content = _translated_card_content_for_type(
            pipeline_result=pipeline_result,
            card_type="action",
            target_language="vi",
        )

        self.assertEqual(len(content["items"]), _MAX_ACTION_CARD_ITEMS)
        self.assertEqual(content["items"][0]["text"], "task 1")


class SubmissionDedupTest(unittest.TestCase):
    def test_redundant_submission_dropped_when_action_already_submits_it(self):
        # 소변검사 실제 케이스: 한 문장이 actions와 submissions에 모두 잡힘.
        source_facts = {
            "actions_required": [
                {"raw_text": "학생이 결석이나 조퇴하지 않고 검사 받기"},
                {"raw_text": "(이상소견 시) 병원 방문하여 재검진 받고 결과 학교 제출"},
            ],
            "submissions": [{"raw_text": "재검진 결과"}],
        }

        items = _canonical_action_card_items(source_facts=source_facts, metadata={})
        texts = [item["text"] for item in items]

        self.assertIn("(이상소견 시) 병원 방문하여 재검진 받고 결과 학교 제출", texts)
        self.assertNotIn("제출: 재검진 결과", texts)
        self.assertEqual(len(texts), 2)

    def test_distinct_submission_is_kept(self):
        # 제출물이 어떤 할일에도 온전히 안 담겨 있으면 유지한다.
        source_facts = {
            "actions_required": [{"raw_text": "참가 여부 회신"}],
            "submissions": [{"raw_text": "참가 동의서"}],
        }

        items = _canonical_action_card_items(source_facts=source_facts, metadata={})
        texts = [item["text"] for item in items]

        self.assertIn("제출: 참가 동의서", texts)

    def test_submission_with_no_actions_is_kept(self):
        source_facts = {"submissions": [{"raw_text": "현장체험학습 신청서"}]}

        items = _canonical_action_card_items(source_facts=source_facts, metadata={})

        self.assertEqual([item["text"] for item in items], ["제출: 현장체험학습 신청서"])

    def test_helper_matches_only_with_submit_cue(self):
        # 단어가 다 들어 있어도 제출 동사가 없으면 중복 아님.
        self.assertFalse(
            _submission_already_in_actions("재검진 결과", ["재검진 결과 확인하기"])
        )
        self.assertTrue(
            _submission_already_in_actions("재검진 결과", ["재검진 결과 학교 제출"])
        )


if __name__ == "__main__":
    unittest.main()
