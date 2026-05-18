from __future__ import annotations

import unittest

from app.services.notice_card_service import build_notice_cards_from_extracted_content


def _content(canonical_summary: dict[str, object]) -> dict[str, object]:
    return {"canonical_summary": canonical_summary}


def _by_type(cards: list[object]) -> dict[str, object]:
    return {card.type: card for card in cards}  # type: ignore[attr-defined]


class NoticeCardServiceTests(unittest.TestCase):
    def test_builds_summary_with_first_three_key_facts(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "현장체험학습 안내",
                    "key_facts": ["1반 대상", "도시락 지참", "9시 출발", "우천 시 변경"],
                    "confidence": 0.8,
                }
            )
        )

        summary = _by_type(cards)["summary"]
        items = summary.content["items"]  # type: ignore[attr-defined]
        self.assertEqual([item["text"] for item in items], ["현장체험학습 안내", "1반 대상", "도시락 지참", "9시 출발"])
        self.assertEqual(summary.content["meta"]["source"], "extracted_content")  # type: ignore[attr-defined]
        self.assertEqual(summary.content["meta"]["confidence"], 0.8)  # type: ignore[attr-defined]

    def test_remaining_key_facts_go_to_info(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "공지",
                    "key_facts": ["a", "b", "c", "d", "e"],
                }
            )
        )

        info = _by_type(cards)["info"]
        self.assertEqual([item["text"] for item in info.content["items"]], ["d", "e"])  # type: ignore[attr-defined]

    def test_requires_response_alone_does_not_create_action(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "응답 필요 안내",
                    "requires_response": True,
                }
            )
        )

        self.assertNotIn("action", _by_type(cards))

    def test_required_action_creates_action_with_deadline_hint(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "required_actions": ["참가 동의서 제출"],
                    "deadline": "5월 20일까지",
                }
            )
        )

        action = _by_type(cards)["action"]
        self.assertEqual(action.content["items"], [{"text": "참가 동의서 제출", "hint": "5월 20일까지"}])  # type: ignore[attr-defined]

    def test_schedule_supplies_and_info_cards(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "important_dates": ["2026. 5. 12. 12:50 ~ 13:10"],
                    "activity_summary": ["민방위 훈련"],
                    "locations": ["운동장"],
                    "preparation_items": ["도시락", "운동화"],
                    "supplement_summary": ["대피 방법을 확인해 주세요"],
                    "contacts": ["02-123-4567"],
                    "links": ["https://example.edu"],
                    "warnings": ["일정 변경 가능"],
                }
            )
        )

        by_type = _by_type(cards)
        self.assertIn("schedule", by_type)
        self.assertIn("supplies", by_type)
        self.assertIn("info", by_type)
        self.assertEqual(
            [item["text"] for item in by_type["supplies"].content["items"]],  # type: ignore[attr-defined]
            ["도시락", "운동화"],
        )
        self.assertIn(
            {"text": "연락처: 02-123-4567"},
            by_type["info"].content["items"],  # type: ignore[attr-defined]
        )

    def test_omits_raw_text_and_uses_consistent_shape(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            {
                "raw_text": "저장하면 안 됨",
                "canonical_summary": {
                    "summary_oneliner": "요약",
                    "required_actions": ["확인"],
                    "preparation_items": ["실내화"],
                },
            }
        )

        for card in cards:
            self.assertEqual(set(card.content.keys()), {"items", "meta"})
            self.assertIsInstance(card.content["items"], list)
            self.assertNotIn("raw_text", card.content)


if __name__ == "__main__":
    unittest.main()
