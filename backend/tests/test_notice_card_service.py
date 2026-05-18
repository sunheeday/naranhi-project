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

    def test_remaining_key_facts_are_not_carded_in_summary_only_v1(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "공지",
                    "key_facts": ["a", "b", "c", "d", "e"],
                }
            )
        )

        summary = _by_type(cards)["summary"]
        self.assertEqual([item["text"] for item in summary.content["items"]], ["공지", "a", "b", "c"])  # type: ignore[attr-defined]
        self.assertEqual(len(cards), 1)

    def test_action_fields_do_not_create_extra_cards_in_summary_only_v1(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "응답 필요 안내",
                    "requires_response": True,
                    "required_actions": ["참가 동의서 제출"],
                    "forms_to_submit": ["신청서"],
                    "fees": ["50000원"],
                    "deadline": "5월 20일까지",
                }
            )
        )

        self.assertNotIn("action", _by_type(cards))
        self.assertEqual([card.type for card in cards], ["summary"])

    def test_non_summary_fields_do_not_create_extra_cards(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "민방위 훈련 안내",
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
        self.assertEqual(set(by_type), {"summary"})

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

    def test_empty_input_returns_no_cards(self) -> None:
        self.assertEqual(build_notice_cards_from_extracted_content({}), [])

    def test_omits_confidence_when_missing(self) -> None:
        cards = build_notice_cards_from_extracted_content(_content({"summary_oneliner": "요약"}))

        self.assertNotIn("confidence", cards[0].content["meta"])

    def test_keeps_zero_confidence(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content({"summary_oneliner": "요약", "confidence": 0.0})
        )

        self.assertEqual(cards[0].content["meta"]["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
