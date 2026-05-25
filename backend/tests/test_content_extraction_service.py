from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import unittest
from unittest.mock import MagicMock, patch

from postgrest.exceptions import APIError

from app.services.content_extraction_service import (
    EXTRACTED_CONTENT_SCHEMA_VERSION,
    _claim_notice,
    build_extracted_content,
    classify_extraction_error,
    _save_success,
    _is_successful_extraction,
    _failure_payload,
    _missing_supabase_config_names,
    _pick_claimable_notice,
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
    included_source_ids: list[str] = field(default_factory=lambda: ["source-1"])
    sources: list[FakeSource] = field(default_factory=lambda: [FakeSource()])
    metadata: dict[str, object] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class ContentExtractionServiceHelperTests(unittest.TestCase):
    def test_extracted_content_omits_raw_text_and_structured(self) -> None:
        payload = build_extracted_content(FakeResult())

        self.assertEqual(payload["schema_version"], EXTRACTED_CONTENT_SCHEMA_VERSION)
        self.assertNotIn("summary_card", payload)
        self.assertNotIn("canonical_summary", payload)
        self.assertNotIn("canonical" + "_source_ids", payload)
        self.assertEqual(payload["included_source_ids"], ["source-1"])
        self.assertNotIn("raw_text", payload)
        self.assertNotIn("combined_text", payload)
        self.assertNotIn("structured", payload["sources"][0])
        self.assertNotIn("raw_text", payload["sources"][0])
        self.assertEqual(payload["sources"][0]["raw_text_chars"], 5)

    def test_save_success_payload_excludes_summary_fields(self) -> None:
        client = MagicMock()

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            _save_success({"id": "notice-1", "summary_translations": {"en": "old"}}, FakeResult())

        payload = client.table.return_value.update.call_args.args[0]
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["original_text"], "전체 원문입니다")
        self.assertIn("extracted_content", payload)
        for removed in (
            "summary_oneliner",
            "summary_translations",
            "document_type",
            "urgency",
            "deadline_at",
            "extraction_finished_at",
        ):
            self.assertNotIn(removed, payload)

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
        self.assertNotIn("extraction_finished_at", payload)

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

    def test_pick_claimable_notice_accepts_homepage_pending_error_when_due(self) -> None:
        row = {
            "id": "notice-1",
            "school_id": "school-1",
            "detail_url": "https://example.edu/1",
            "status": "error",
            "extraction_attempts": 1,
            "extraction_error_code": "transient_network",
            "extraction_next_run_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        }

        picked = _pick_claimable_notice(
            [row],
            notice_id=None,
            force=False,
            stale_minutes=180,
        )

        self.assertEqual(picked, row)

    def test_claim_notice_falls_back_when_rpc_is_missing(self) -> None:
        rpc_query = MagicMock()
        rpc_query.execute.side_effect = APIError(
            {
                "code": "PGRST202",
                "message": "Could not find the function public.claim_notice_extractions(p_force, p_limit, p_notice_id, p_stale_minutes) in the schema cache",
                "details": "",
                "hint": None,
            }
        )

        select_query = MagicMock()
        select_query.eq.return_value = select_query
        select_query.limit.return_value = select_query
        select_query.execute.return_value.data = [
            {
                "id": "notice-1",
                "school_id": "school-1",
                "detail_url": "https://example.edu/1",
                "status": "pending",
                "extraction_attempts": 0,
                "extraction_started_at": None,
                "extraction_next_run_at": None,
                "extraction_error_code": None,
            }
        ]

        update_query = MagicMock()
        update_query.eq.return_value = update_query
        update_query.execute.return_value.data = []

        notices_table = MagicMock()
        notices_table.select.return_value = select_query
        notices_table.update.return_value = update_query

        client = MagicMock()
        client.rpc.return_value = rpc_query
        client.table.return_value = notices_table

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            claimed = _claim_notice(notice_id="notice-1", force=True, stale_minutes=180)

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], "notice-1")
        self.assertEqual(claimed["status"], "processing")
        notices_table.update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
