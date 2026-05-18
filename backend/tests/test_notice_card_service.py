from __future__ import annotations

import unittest

from app.services.notice_card_service import build_notice_cards, build_notice_cards_from_extracted_content


def _content(canonical_summary: dict[str, object]) -> dict[str, object]:
    return {"canonical_summary": canonical_summary}


def _by_type(cards: list[object]) -> dict[str, object]:
    return {card.type: card for card in cards}  # type: ignore[attr-defined]


class NoticeCardServiceTests(unittest.TestCase):
    def test_raw_text_drives_summary_instead_of_date_list(self) -> None:
        cards = build_notice_cards(
            title="2026년 4월 축구부 운영결과 안내",
            original_text="""
[attachment_pdf_1 attachment_pdf]
서울특별시교육청 공익제보센터 운영 안내
○ 신고방법 : 이메일 cleanedu@sen.go.kr / ☎ 1588-0260
안녕하십니까?
선진형 학교 운동부 운영의 투명성을 제고하고자 다음과 같이 2026년 4월 (2026년 4월 1일 ~ 2026년 4월 30일) 축구부 운영
회비 납부 현황과 운영 결과를 안내해 드립니다.
운영회비 총괄표
익월 이월액 (1) - (2)
- 7,998,400원
상세한 지출 내용을 확인하시고 싶으신 학부모님께서는 서울시교육청 열린교육홈페이지 및 학교홈페이지에서 열람해주시기 바랍니다.
""",
            extracted_content=_content(
                {
                    "summary_oneliner": "2026년 4월 축구부 운영결과 안내",
                    "important_dates": ["2026-05-07", "2026년 5월 7일", "2026년 4월 1일", "2026년 4월 30일"],
                }
            ),
        )

        items = [item["text"] for item in _by_type(cards)["summary"].content["items"]]  # type: ignore[attr-defined]
        self.assertTrue(any("회비 납부 현황과 운영 결과를 안내해 드립니다." in item for item in items))
        self.assertNotIn("일정: 2026-05-07", items)
        self.assertTrue(all("공익제보센터" not in item for item in items))

    def test_raw_text_recovers_sparse_canonical_summary(self) -> None:
        cards = build_notice_cards(
            title="5월 15일(금)일과표 변경 안내 가정통신문",
            original_text="""
[html_body_1 html_body]
게시판 상세보기
이름
강**
등록일
2026-05-13 13:38:21
제목
5월 15일(금)일과표 변경 안내 가정통신문
내용
목록
---
[inline_image_1 inline_image]
5월 15일 일과표 안내
대상: 전학년
학부모님, 안녕하십니까?
정부 주관 민방위 훈련 실시와 관련하여 학생들의 안전한 귀가와 원활한 훈련 운영을 위해 아래와 같이 단축수업을 실시하고자 합니다.
학부모님께서는 일정을 확인해 주시기 바랍니다.
아울러 민방위 훈련 진행 상황에 따라 하교 시간이 다소 변경될 수 있음을 안내드립니다.
민방위 훈련
14:40 ~ 15:00
영등포중학교장
""",
            extracted_content=_content(
                {
                    "summary_oneliner": "5월 15일(금)일과표 변경 안내 가정통신문",
                    "key_facts": ["내용", "대상: 전학년"],
                }
            ),
        )

        items = [item["text"] for item in _by_type(cards)["summary"].content["items"]]  # type: ignore[attr-defined]
        self.assertIn("대상: 전학년", items)
        self.assertIn("정부 주관 민방위 훈련 실시와 관련하여 학생들의 안전한 귀가와 원활한 훈련 운영을 위해 아래와 같이 단축수업을 실시하고자 합니다.", items)
        self.assertTrue(all(item not in {"내용", "등록일", "작성자"} for item in items))

    def test_raw_text_filters_author_metadata_from_hwpx_notice(self) -> None:
        cards = build_notice_cards(
            title="경조사로 인한 출석인정 결석 안내",
            original_text="""
[attachment_hwpx_1 attachment_hwpx]
<경조사로 인한 출석인정 결석 안내>
학부모님 안녕하십니까?
경조사로 인한 출결처리에 대해 다음과 같이 안내해 드립니다.
가. 출결사유: 경조사로 인하여 출석하지 못한 경우
나. 출결처리: 출석인정 결석(지각, 조퇴 포함)
다. 주요내용:
※ 기간 산정 시 토요일, 공휴일, 재량휴업일은 포함하지 않습니다.
※ 출석인정 처리가 되지 않는 경우 : 큰할아버지가 돌아가셨을 경우.
<2026. 5. 14.>
[html_body_1 html_body]
작성자
안산부곡중학교 관리자
등록일
2026.05.14
문의: 031-487-2235
""",
            extracted_content=_content(
                {
                    "summary_oneliner": "경조사로 인한 출석인정 결석 안내",
                    "important_dates": ["2026.05.14", "2026. 5. 14"],
                    "required_actions": ["작성자"],
                    "contacts": ["031-487-2235"],
                }
            ),
        )

        items = [item["text"] for item in _by_type(cards)["summary"].content["items"]]  # type: ignore[attr-defined]
        self.assertIn("가. 출결사유: 경조사로 인하여 출석하지 못한 경우", items)
        self.assertIn("나. 출결처리: 출석인정 결석(지각, 조퇴 포함)", items)
        self.assertNotIn("해야 할 일: 작성자", items)
        self.assertNotIn("일정: 2026.05.14", items)

    def test_builds_summary_with_meaningful_key_facts(self) -> None:
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
        self.assertEqual(
            [item["text"] for item in items],
            ["현장체험학습 안내", "1반 대상", "도시락 지참", "9시 출발", "우천 시 변경"],
        )
        self.assertEqual(summary.content["meta"]["source"], "extracted_content")  # type: ignore[attr-defined]
        self.assertEqual(summary.content["meta"]["confidence"], 0.8)  # type: ignore[attr-defined]

    def test_key_facts_are_limited_after_summary(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "현장체험학습 안내",
                    "key_facts": ["대상: 2학년 전체", "일시: 5월 11일", "장소: 한성아트홀", "준비물: 도시락", "문의: 담임교사"],
                }
            )
        )

        summary = _by_type(cards)["summary"]
        self.assertEqual(
            [item["text"] for item in summary.content["items"]],
            ["현장체험학습 안내", "대상: 2학년 전체", "일시: 5월 11일", "장소: 한성아트홀", "준비물: 도시락"],
        )  # type: ignore[attr-defined]
        self.assertEqual(len(cards), 1)

    def test_action_fields_are_folded_into_summary_only_card(self) -> None:
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
        summary = _by_type(cards)["summary"]
        self.assertIn({"text": "해야 할 일: 참가 동의서 제출"}, summary.content["items"])  # type: ignore[attr-defined]
        self.assertIn({"text": "제출: 신청서"}, summary.content["items"])  # type: ignore[attr-defined]

    def test_non_summary_fields_are_prioritized_inside_summary(self) -> None:
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
        items = [item["text"] for item in by_type["summary"].content["items"]]  # type: ignore[attr-defined]
        self.assertEqual(items[0], "민방위 훈련 안내")
        self.assertIn("일정: 2026. 5. 12. 12:50 ~ 13:10", items)
        self.assertIn("장소: 운동장", items)

    def test_omits_raw_text_and_uses_consistent_shape(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            {
                "raw_text": "저장하면 안 됨",
                "canonical_summary": {
                    "summary_oneliner": "요약 안내",
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

    def test_noise_lines_are_removed_from_summary(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "민방위 훈련 안내",
                    "key_facts": [
                        "내용",
                        "작성자",
                        "등록일",
                        "공익제보센터 운영 안내",
                        "신고방법 : 이메일 cleanedu@sen.go.kr / 1588-0260",
                        "훈련내용: 공습 대비 대피방법 숙달",
                    ],
                }
            )
        )

        items = [item["text"] for item in _by_type(cards)["summary"].content["items"]]  # type: ignore[attr-defined]
        self.assertEqual(items, ["민방위 훈련 안내", "훈련내용: 공습 대비 대피방법 숙달"])

    def test_generic_targets_do_not_displace_real_summary_lines(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content(
                {
                    "summary_oneliner": "2026년 5월 공습대비 민방위 훈련 안내",
                    "targets": ["학생", "학부모"],
                    "preparation_items": ["공회 준비!", "준비하세요"],
                    "key_facts": [
                        "내용",
                        "방법을 확인하는 등 예방훈련이 성공적으로 실시되어 미래의 주역인 학생들이 안전하게 자라날",
                        "○ 훈련기간 : 2026. 5. 12.(화) 12:50 ~ 13:10 (20분간)",
                        "○ 훈련내용 : 공습 대비 대피방법 숙달, 비상시 국민행동요령 교육 및 과제물 부여",
                        "○ 자녀에게 민방위 훈련의 필요성과 대피방법을 지도하여 주시기 바랍니다.",
                        "○ 화재 및 지진대피 방법을 확인해 주시기 바랍니다.",
                    ],
                }
            )
        )

        items = [item["text"] for item in _by_type(cards)["summary"].content["items"]]  # type: ignore[attr-defined]
        self.assertEqual(
            items,
            [
                "2026년 5월 공습대비 민방위 훈련 안내",
                "○ 훈련기간 : 2026. 5. 12.(화) 12:50 ~ 13:10 (20분간)",
                "○ 훈련내용 : 공습 대비 대피방법 숙달, 비상시 국민행동요령 교육 및 과제물 부여",
                "○ 자녀에게 민방위 훈련의 필요성과 대피방법을 지도하여 주시기 바랍니다.",
                "○ 화재 및 지진대피 방법을 확인해 주시기 바랍니다.",
            ],
        )

    def test_omits_confidence_when_missing(self) -> None:
        cards = build_notice_cards_from_extracted_content(_content({"summary_oneliner": "요약 안내"}))

        self.assertNotIn("confidence", cards[0].content["meta"])

    def test_keeps_zero_confidence(self) -> None:
        cards = build_notice_cards_from_extracted_content(
            _content({"summary_oneliner": "요약 안내", "confidence": 0.0})
        )

        self.assertEqual(cards[0].content["meta"]["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
