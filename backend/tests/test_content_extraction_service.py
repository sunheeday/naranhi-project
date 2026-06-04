from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import unittest
from unittest.mock import MagicMock, patch

from postgrest.exceptions import APIError

from app.services.content_extraction_service import (
    EXTRACTED_CONTENT_SCHEMA_VERSION,
    _attachment_too_long,
    _auto_translate_notice_locales,
    _claim_notice,
    build_extracted_content,
    classify_extraction_error,
    _missing_translation_locales,
    _normalized_locale,
    _primary_source_id,
    _refine_sources,
    _save_success,
    translate_sources_for_locale,
    _school_translation_locales,
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


class FakeQueryResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, client, name: str):
        self.client = client
        self.name = name
        self.filters: dict[str, object] = {}
        self.selected = "*"

    def select(self, columns: str):
        self.selected = columns
        return self

    def eq(self, column: str, value: object):
        self.filters[column] = value
        return self

    def in_(self, column: str, values: list[object]):
        self.filters[column] = list(values)
        return self

    def execute(self):
        if self.name == "children":
            school_id = self.filters.get("school_id")
            rows = [row for row in self.client.children if row.get("school_id") == school_id]
            return FakeQueryResult(rows)
        if self.name == "profiles":
            ids = set(self.filters.get("id", []))
            rows = [row for row in self.client.profiles if row.get("id") in ids]
            return FakeQueryResult(rows)
        if self.name == "notice_ai_translations":
            notice_id = self.filters.get("notice_id")
            rows = [row for row in self.client.translations if row.get("notice_id") == notice_id]
            return FakeQueryResult(rows)
        raise AssertionError(f"Unexpected table access: {self.name}")


class FakeSupabaseClient:
    def __init__(self):
        self.children: list[dict[str, object]] = []
        self.profiles: list[dict[str, object]] = []
        self.translations: list[dict[str, object]] = []

    def table(self, name: str):
        return FakeTable(self, name)


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

    def test_save_success_payload_uses_refined_text(self) -> None:
        client = MagicMock()
        refinements = {
            "source-1": {
                "refined_text": "# 정제된 본문입니다",
                "needs_file": False,
                "needs_file_reason": [],
                "quality_signals": {"tag": "ok"},
            }
        }

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            _save_success(
                {"id": "notice-1", "summary_translations": {"en": "old"}},
                FakeResult(),
                refinements,
            )

        payload = client.table.return_value.update.call_args.args[0]
        self.assertEqual(payload["status"], "done")
        # original_text 는 추출 날것(raw_text)이 아니라 대표 소스의 정제본이어야 한다.
        self.assertEqual(payload["original_text"], "# 정제된 본문입니다")
        self.assertNotEqual(payload["original_text"], FakeResult().raw_text)
        self.assertIn("extracted_content", payload)
        self.assertFalse(payload["extracted_content"]["needs_file"])
        # 소스별 정제본이 sources[] 에 들어가야 한다(프론트 카드용).
        self.assertEqual(payload["extracted_content"]["sources"][0]["refined_text"], "# 정제된 본문입니다")
        for removed in (
            "summary_oneliner",
            "summary_translations",
            "document_type",
            "urgency",
            "deadline_at",
            "extraction_finished_at",
        ):
            self.assertNotIn(removed, payload)

    def test_save_success_records_needs_file_flag(self) -> None:
        client = MagicMock()
        refinements = {
            "source-1": {
                "refined_text": "깨진 본문",
                "needs_file": True,
                "needs_file_reason": ["폴백(LLM 정제 실패)"],
                "quality_signals": {"tag": "FALLBACK"},
            }
        }

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            _save_success({"id": "notice-1"}, FakeResult(), refinements)

        extracted_content = client.table.return_value.update.call_args.args[0]["extracted_content"]
        self.assertTrue(extracted_content["needs_file"])
        self.assertEqual(extracted_content["needs_file_reason"], ["폴백(LLM 정제 실패)"])
        self.assertTrue(extracted_content["sources"][0]["needs_file"])

    def test_save_success_full_body_to_original_text_summary_to_extracted(self) -> None:
        client = MagicMock()
        refinements = {
            "source-1": {
                "refined_text": "# 본문 정제본",
                "needs_file": False,
                "needs_file_reason": [],
                "quality_signals": {"tag": "ok"},
            }
        }
        summary = {
            "title": "정산 안내",
            "points": [{"label": "참가비", "value": "무료"}],
        }

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            _save_success({"id": "notice-1", "title": "테스트 공지"}, FakeResult(), refinements, None, summary)

        payload = client.table.return_value.update.call_args.args[0]
        # original_text = 풀 본문(정제본) — 요약이 아니라 팀 구조화 파이프라인 입력용.
        self.assertEqual(payload["original_text"], "# 본문 정제본")
        # 요약은 extracted_content.summary 에 (구조 JSON + 렌더 텍스트).
        ec_summary = payload["extracted_content"]["summary"]
        self.assertEqual(ec_summary["title"], "정산 안내")
        self.assertIn("정산 안내", ec_summary["rendered"])
        self.assertIn("참가비: 무료", ec_summary["rendered"])

    def test_primary_source_prefers_body(self) -> None:
        result = FakeResult(
            included_source_ids=["att", "body"],
            sources=[
                FakeSource(source_id="att", source_type="attachment_pdf"),
                FakeSource(source_id="body", source_type="html_body"),
            ],
        )
        self.assertEqual(_primary_source_id(result), "body")

    def test_build_extracted_content_merges_refined_text_per_source(self) -> None:
        refinements = {"source-1": {"refined_text": "정제본", "needs_file": False, "needs_file_reason": []}}
        payload = build_extracted_content(FakeResult(), refinements)
        self.assertEqual(payload["sources"][0]["refined_text"], "정제본")
        self.assertFalse(payload["sources"][0]["needs_file"])

    def test_refine_sources_falls_back_to_raw_on_failure(self) -> None:
        class BoomGemini:
            async def generate_text(self, prompt, *, model=None):
                raise RuntimeError("vertex unavailable")

        import asyncio

        result = FakeResult(sources=[FakeSource(raw_text="원문 그대로 보존")])
        refinements, calls = asyncio.run(
            _refine_sources(result, gemini_client=BoomGemini(), notice_id="notice-1")
        )
        # 정제 실패 시에도 소스 원문을 그대로 쓰고 호출수는 0.
        self.assertEqual(refinements["source-1"]["refined_text"], "원문 그대로 보존")
        self.assertEqual(calls, 0)
        self.assertIn("needs_file", refinements["source-1"])

    def test_attachment_too_long_by_pages_and_length(self) -> None:
        self.assertTrue(_attachment_too_long(FakeSource(metadata={"page_count": 25})))
        self.assertFalse(_attachment_too_long(FakeSource(metadata={"page_count": 10})))
        self.assertTrue(_attachment_too_long(FakeSource(raw_text="가" * 20001, metadata={})))
        self.assertFalse(_attachment_too_long(FakeSource(raw_text="짧은 첨부", metadata={})))

    def test_refine_sources_skips_long_attachment(self) -> None:
        # 20페이지 초과 첨부는 정제하지 않고(refined_text="") needs_file=True 로 원본 안내.
        class FakeGemini:
            async def generate_text(self, prompt, *, model=None):
                return "정제된 본문"

        import asyncio

        result = FakeResult(
            included_source_ids=["body", "att"],
            sources=[
                FakeSource(source_id="body", source_type="html_body", raw_text="본문 내용입니다"),
                FakeSource(source_id="att", source_type="attachment_pdf", raw_text="x" * 100,
                           metadata={"page_count": 30}),
            ],
        )
        refinements, _ = asyncio.run(
            _refine_sources(result, gemini_client=FakeGemini(), notice_id="n")
        )
        self.assertTrue(refinements["att"]["needs_file"])
        self.assertEqual(refinements["att"]["refined_text"], "")
        self.assertIn("body", refinements)  # 본문은 정상 정제됨

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

    def test_school_translation_locales_collects_unique_non_korean_locales(self) -> None:
        client = FakeSupabaseClient()
        client.children = [
            {"school_id": "school-1", "user_id": "user-1"},
            {"school_id": "school-1", "user_id": "user-2"},
            {"school_id": "school-1", "user_id": "user-3"},
        ]
        client.profiles = [
            {"id": "user-1", "locale": "vi", "native_language": "vi"},
            {"id": "user-2", "locale": "en", "native_language": "ko"},
            {"id": "user-3", "locale": "ko", "native_language": "ru"},
        ]

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            locales = _school_translation_locales("school-1")

        self.assertEqual(locales, ["vi", "en", "ru"])

    def test_school_translation_locales_falls_back_to_korean_when_no_foreign_locale(self) -> None:
        client = FakeSupabaseClient()
        client.children = [
            {"school_id": "school-1", "user_id": "user-1"},
            {"school_id": "school-1", "user_id": "user-2"},
        ]
        client.profiles = [
            {"id": "user-1", "locale": "ko", "native_language": "ko"},
            {"id": "user-2", "locale": "ko", "native_language": "ko"},
        ]

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            locales = _school_translation_locales("school-1")

        self.assertEqual(locales, ["ko"])

    def test_missing_translation_locales_skips_cached_non_failed_rows(self) -> None:
        client = FakeSupabaseClient()
        client.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "vi",
                "translated_text": "ok",
                "validation_status": "human_review_required",
            },
            {
                "notice_id": "notice-1",
                "target_language": "en",
                "translated_text": "retry me",
                "validation_status": "failed",
            },
        ]

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            missing = _missing_translation_locales("notice-1", ["vi", "en", "ru"])

        self.assertEqual(missing, ["en", "ru"])

    def test_auto_translate_notice_locales_translates_only_missing_locales(self) -> None:
        client = FakeSupabaseClient()
        client.children = [
            {"school_id": "school-1", "user_id": "user-1"},
            {"school_id": "school-1", "user_id": "user-2"},
        ]
        client.profiles = [
            {"id": "user-1", "locale": "vi", "native_language": "ko"},
            {"id": "user-2", "locale": "en", "native_language": "en"},
        ]
        client.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "vi",
                "translated_text": "cached",
                "validation_status": "passed",
            },
        ]
        settings = type("FakeSettings", (), {"gemini_configured": True})()
        translated: list[tuple[str, str]] = []

        class FakeNoticeService:
            async def translate_notice(self, *, notice_id: str, target_language: str, **kwargs):
                translated.append((notice_id, target_language))
                return {"ok": True}

        with (
            patch("app.services.content_extraction_service.get_supabase_client", return_value=client),
            patch("app.services.content_extraction_service.get_settings", return_value=settings),
            patch("app.services.notice_service.NoticeService", return_value=FakeNoticeService()),
        ):
            import asyncio

            asyncio.run(_auto_translate_notice_locales({"id": "notice-1", "school_id": "school-1"}))

        self.assertEqual(translated, [("notice-1", "en")])

    def test_normalized_locale_rejects_korean_and_invalid_values(self) -> None:
        self.assertIsNone(_normalized_locale("ko"))
        self.assertIsNone(_normalized_locale("bad locale"))
        self.assertEqual(_normalized_locale("VI"), "vi")


class TranslateSourcesForLocaleTests(unittest.IsolatedAsyncioTestCase):
    """요약·본문·첨부를 팀 translate_text 재사용해 번역·저장(이미 있는 언어는 건너뜀)."""

    class FakeService:
        async def translate_text(self, *, source_text: str, target_language: str) -> dict[str, object]:
            return {"translation": f"[{target_language}] {source_text}"}

    async def test_translates_summary_and_sources_skips_cached(self) -> None:
        client = MagicMock()
        extracted = {
            "summary": {"rendered": "요약문", "points": []},
            "sources": [
                {"source_id": "s1", "refined_text": "본문 정제본"},
                {"source_id": "s2", "refined_text": "첨부 정제본", "translations": {"en": "이미있음"}},
            ],
        }
        (
            client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data
        ) = {"extracted_content": extracted}

        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            await translate_sources_for_locale(self.FakeService(), "notice-1", "en")

        saved = client.table.return_value.update.call_args.args[0]["extracted_content"]
        self.assertEqual(saved["summary"]["translations"]["en"], "[en] 요약문")
        self.assertEqual(saved["sources"][0]["translations"]["en"], "[en] 본문 정제본")
        # 이미 en 번역 있는 소스는 그대로(재번역 안 함)
        self.assertEqual(saved["sources"][1]["translations"]["en"], "이미있음")

    async def test_ko_does_nothing(self) -> None:
        client = MagicMock()
        with patch("app.services.content_extraction_service.get_supabase_client", return_value=client):
            await translate_sources_for_locale(self.FakeService(), "notice-1", "ko")
        client.table.return_value.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
