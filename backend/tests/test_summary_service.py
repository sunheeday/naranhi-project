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
    def test_body_and_attachments_prose(self) -> None:
        s = {
            "body": "이 공지는 체험학습 정산 안내입니다.",
            "attachments": [{"source_id": "a1", "name": "정산표", "summary": "체험비 정산 내역."}],
        }
        md = render_summary_markdown(s)
        self.assertIn("이 공지는 체험학습 정산 안내입니다.", md)
        self.assertIn("첨부 '정산표'에는 체험비 정산 내역.", md)

    def test_empty_inputs(self) -> None:
        self.assertEqual(render_summary_markdown(None), "")
        self.assertEqual(render_summary_markdown({"body": "", "attachments": []}), "")


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


class SummarizeTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_json_parsed_and_attachment_id_preserved(self) -> None:
        resp = json.dumps(
            {
                "body": "이 공지는 체험학습 정산 안내입니다.",
                "attachments": [{"source_id": "att1", "name": "정산표", "summary": "체험비 30,000원 정산."}],
            },
            ensure_ascii=False,
        )
        g = FakeGemini([resp])
        out, calls = await summarize(
            title="정산",
            body="체험비 30,000원 정산 결과",
            attachments=[{"source_id": "att1", "name": "정산표", "text": "체험비 30,000원", "needs_file": False}],
            gemini=g,
        )
        self.assertEqual(calls, 1)
        self.assertEqual(out["attachments"][0]["source_id"], "att1")
        self.assertIn("정산", out["body"])

    async def test_hallucination_twice_falls_back_to_minimal(self) -> None:
        bad = json.dumps({"body": "행사는 2026년 12월 25일입니다.", "attachments": []}, ensure_ascii=False)
        g = FakeGemini([bad, bad])
        out, calls = await summarize(title="행사", body="행사 안내", attachments=[], gemini=g)
        self.assertEqual(calls, 2)  # 최초 + 재생성
        self.assertNotIn("12월 25일", out["body"])  # 환각 숫자 제거
        self.assertIn("행사", out["body"])  # title 기반 최소 요약

    async def test_empty_input_minimal_no_llm_call(self) -> None:
        g = FakeGemini([])
        out, calls = await summarize(title="제목", body="", attachments=[], gemini=g)
        self.assertEqual(calls, 0)
        self.assertEqual(g.calls, 0)
        self.assertIn("제목", out["body"])

    async def test_gemini_none_minimal(self) -> None:
        out, calls = await summarize(title="제목", body="내용", attachments=[], gemini=None)
        self.assertEqual(calls, 0)
        self.assertIn("제목", out["body"])

    async def test_needs_file_attachment_always_included_with_note(self) -> None:
        resp = json.dumps({"body": "공지입니다.", "attachments": []}, ensure_ascii=False)
        g = FakeGemini([resp])
        out, calls = await summarize(
            title="t",
            body="본문 내용",
            attachments=[{"source_id": "a2", "name": "규정.pdf", "text": "", "needs_file": True}],
            gemini=g,
        )
        self.assertEqual(len(out["attachments"]), 1)
        self.assertEqual(out["attachments"][0]["source_id"], "a2")
        self.assertIn("원본", out["attachments"][0]["summary"])


if __name__ == "__main__":
    unittest.main()
