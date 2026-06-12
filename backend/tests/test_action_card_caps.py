import unittest

from app.services.notice_service import (
    _MAX_ACTION_CARD_ITEMS,
    _canonical_action_card_items,
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


if __name__ == "__main__":
    unittest.main()
