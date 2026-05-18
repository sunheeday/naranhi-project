from __future__ import annotations

from dataclasses import dataclass, field
import unittest

from app.services.content_extraction_service import (
    EXTRACTED_CONTENT_SCHEMA_VERSION,
    build_extracted_content,
    classify_extraction_error,
    _is_successful_extraction,
    _failure_payload,
    _missing_supabase_config_names,
)


@dataclass
class FakeSource:
    source_id: str = "source-1"
    source_type: str = "attachment_pdf"
    source_role: str = "primary"
    origin_url: str = "https://example.edu/notice.pdf"
    filename: str = "notice.pdf"
    file_hash: str = "hash"
    text_fingerprint: str = "fingerprint"
    extraction_method: str = "pdf_pymupdf"
    status: str = "success"
    raw_text: str = "본문입니다"
    structured: dict[str, object] = field(default_factory=lambda: {"summary_oneliner": "저장하면 안 됨"})
    confidence: float = 0.9
    quality_score: float = 42.0
    metadata: dict[str, object] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class FakeResult:
    status: str = "success"
    content_kind: str = "attachment_only"
    raw_text: str = "전체 원문입니다"
    final_url: str = "https://example.edu/detail"
    canonical_summary: dict[str, object] = field(default_factory=lambda: {"summary_oneliner": "요약"})
    canonical_source_ids: list[str] = field(default_factory=lambda: ["source-1"])
    sources: list[FakeSource] = field(default_factory=lambda: [FakeSource()])
    metadata: dict[str, object] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class ContentExtractionServiceHelperTests(unittest.TestCase):
    def test_extracted_content_omits_raw_text_and_structured(self) -> None:
        payload = build_extracted_content(FakeResult())

        self.assertEqual(payload["schema_version"], EXTRACTED_CONTENT_SCHEMA_VERSION)
        self.assertNotIn("summary_card", payload)
        self.assertNotIn("raw_text", payload)
        self.assertNotIn("combined_text", payload)
        self.assertNotIn("structured", payload["sources"][0])
        self.assertNotIn("raw_text", payload["sources"][0])
        self.assertEqual(payload["sources"][0]["raw_text_chars"], 5)

    def test_extracted_content_can_store_gemini_summary_card(self) -> None:
        payload = build_extracted_content(
            FakeResult(),
            summary_card={
                "schema_version": "1",
                "source": "gemini_summary",
                "model": "gemini-2.5-flash-lite",
                "items": [{"text": "본문 전체를 기반으로 만든 핵심 요약"}],
                "confidence": 0.9,
            },
        )

        self.assertEqual(payload["summary_card"]["source"], "gemini_summary")
        self.assertEqual(payload["summary_card"]["items"][0]["text"], "본문 전체를 기반으로 만든 핵심 요약")

    def test_classifies_budget_exhausted(self) -> None:
        result = FakeResult(status="partial_success", metadata={"budget_exhausted": True})

        self.assertEqual(classify_extraction_error(result), "budget_exhausted")

    def test_classifies_quota(self) -> None:
        result = FakeResult(status="internal_error", errors=["HTTP 429 quota exceeded"])

        self.assertEqual(classify_extraction_error(result), "gemini_quota_exhausted")

    def test_classifies_unsupported_file(self) -> None:
        result = FakeResult(status="partial_success", errors=["unsupported_or_spoofed_file"])

        self.assertEqual(classify_extraction_error(result), "unsupported_file")

    def test_empty_or_unreadable_is_not_success(self) -> None:
        result = FakeResult(content_kind="empty_or_unreadable", raw_text="게시판 상세보기")

        self.assertFalse(_is_successful_extraction(result))
        self.assertEqual(classify_extraction_error(result), "empty_or_unreadable")

    def test_quota_failure_does_not_adjust_attempts(self) -> None:
        payload = _failure_payload(
            {"extraction_attempts": 7},
            error_code="gemini_quota_exhausted",
            error_message="quota",
        )

        self.assertEqual(payload["extraction_attempts"], 7)
        self.assertIsNotNone(payload["extraction_next_run_at"])

    def test_immediate_giveup_sets_attempts_to_three(self) -> None:
        payload = _failure_payload(
            {"extraction_attempts": 1},
            error_code="unsupported_file",
            error_message="bad file",
        )

        self.assertEqual(payload["extraction_attempts"], 3)
        self.assertIsNone(payload["extraction_next_run_at"])

    def test_reports_missing_supabase_config_names(self) -> None:
        settings = type(
            "FakeSettings",
            (),
            {"supabase_url": "", "supabase_service_role_key": None},
        )()

        self.assertEqual(
            _missing_supabase_config_names(settings),
            ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"],
        )


if __name__ == "__main__":
    unittest.main()
