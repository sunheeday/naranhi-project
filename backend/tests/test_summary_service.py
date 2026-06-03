from __future__ import annotations

import json
import unittest

from app.services.summary_service import (
    _collect_facts,
    _hallucinated_facts,
    render_summary_markdown,
    summarize,
)


class FakeGemini:
    """generate_text 호출마다 미리 준 응답을 순서대로 돌려주는 목."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def generate_text(self, prompt: str) -> str:
        self.calls += 1
        return self.responses.pop(0) if self.responses else ""


class RenderSummaryTests(unittest.TestCase):
    def test_title_and_points(self) -> None:
        s = {
            "title": "2026 다문화가정 문화 동행 프로그램 모집",
            "points": [
                {"label": "프로그램 내용", "value": "공연관람, 한국문화체험"},
                {"label": "참가비", "value": "무료"},
                {"label": "날짜", "value": "2026년 6월 4일"},
            ],
        }
        md = render_summary_markdown(s)
        self.assertEqual(
            md,
            "2026 다문화가정 문화 동행 프로그램 모집\n프로그램 내용: 공연관람, 한국문화체험\n참가비: 무료\n날짜: 2026년 6월 4일",
        )

    def test_empty_inputs(self) -> None:
        self.assertEqual(render_summary_markdown(None), "")
        self.assertEqual(render_summary_markdown({"title": "", "points": []}), "")


class FactCheckTests(unittest.TestCase):
    def test_collect_dates_and_money(self) -> None:
        facts = _collect_facts("행사는 2026년 6월 1일, 비용 30,000원입니다.")
        self.assertIn("2026년 6월 1일", facts)
        self.assertIn("30,000원", facts)

    def test_hallucinated_date_detected(self) -> None:
        bad = _hallucinated_facts("행사는 2026년 7월 1일입니다.", "행사는 2026년 6월 1일입니다.")
        self.assertTrue(bad)

    def test_money_ok_when_present_in_source(self) -> None:
        self.assertEqual(_hallucinated_facts("비용은 30,000원입니다.", "체험비 30,000원 납부"), [])

    def test_added_year_not_flagged(self) -> None:
        # 원문 '6월 8일' → 요약 '2026년 6월 8일'(연도 추가)도 같은 (월,일)이라 통과.
        self.assertEqual(_hallucinated_facts("신청 마감일: 2026년 6월 8일", "신청은 6월 8일까지"), [])

    def test_dotted_date_matches_month_day(self) -> None:
        self.assertEqual(_hallucinated_facts("기간: 2026.6.9.(화)", "6월 9일부터 운영"), [])


class SummarizeTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_json_parsed(self) -> None:
        resp = json.dumps(
            {
                "title": "진로체험학습 경비 정산",
                "points": [
                    {"label": "날짜", "value": "2026년 5월 21일"},
                    {"label": "참여 인원", "value": "116명"},
                ],
            },
            ensure_ascii=False,
        )
        g = FakeGemini([resp])
        out, calls = await summarize(
            title="정산",
            body="2026년 5월 21일 진행, 참여 116명",
            attachments=[],
            gemini=g,
        )
        self.assertEqual(calls, 1)
        self.assertEqual(out["title"], "진로체험학습 경비 정산")
        self.assertEqual(out["points"][0]["label"], "날짜")
        self.assertEqual(out["points"][0]["value"], "2026년 5월 21일")

    async def test_hallucination_twice_falls_back_to_title_only(self) -> None:
        bad = json.dumps(
            {"title": "행사", "points": [{"label": "날짜", "value": "2026년 12월 25일"}]},
            ensure_ascii=False,
        )
        g = FakeGemini([bad, bad])
        out, calls = await summarize(title="행사 안내", body="행사 안내", attachments=[], gemini=g)
        self.assertEqual(calls, 2)
        self.assertEqual(out["points"], [])  # 환각 항목 제거(제목만)
        self.assertEqual(out["title"], "행사 안내")

    async def test_empty_input_minimal_no_llm_call(self) -> None:
        g = FakeGemini([])
        out, calls = await summarize(title="제목", body="", attachments=[], gemini=g)
        self.assertEqual(calls, 0)
        self.assertEqual(g.calls, 0)
        self.assertEqual(out["title"], "제목")

    async def test_gemini_none_minimal(self) -> None:
        out, calls = await summarize(title="제목", body="내용", attachments=[], gemini=None)
        self.assertEqual(calls, 0)
        self.assertEqual(out["title"], "제목")


if __name__ == "__main__":
    unittest.main()
