import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.services.notice_service import (
    NoticeService,
    _execute_optional_single,
    _has_complete_card_translation_cache,
    _with_sanitized_metadata,
    _usable_cached_translation,
)


class FakeResult:
    def __init__(self, data=None):
        self.data = data or []


class FakeTable:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.action = None
        self.payload = None
        self.filters = {}

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        self.client.operations.append((self.name, self.action, payload))
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        self.client.operations.append((self.name, self.action, payload))
        return self

    def upsert(self, payload, on_conflict=None):
        self.action = "upsert"
        self.payload = payload
        self.client.operations.append(
            (self.name, self.action, payload, on_conflict),
        )
        return self

    def delete(self):
        self.action = "delete"
        self.payload = None
        self.client.operations.append((self.name, self.action, None))
        return self

    def select(self, columns):
        self.action = "select"
        self.payload = columns
        self.client.operations.append((self.name, self.action, columns))
        return self

    def eq(self, column, value):
        self.filters[column] = value
        self.client.operations.append((self.name, "eq", column, value))
        return self

    def maybeSingle(self):
        self.action = "maybeSingle"
        self.client.operations.append((self.name, self.action, None))
        return self

    def single(self):
        self.action = "single"
        self.client.operations.append((self.name, self.action, None))
        return self

    def execute(self):
        if self.name == "notices" and self.action in {"select", "single"}:
            return FakeResult(self.client.notice)
        if self.name == "notice_ai_translations" and self.action in {"select", "maybeSingle"}:
            notice_id = self.filters.get("notice_id")
            target_language = self.filters.get("target_language")
            for row in self.client.translations:
                if row.get("notice_id") == notice_id and row.get("target_language") == target_language:
                    return FakeResult(row)
            return FakeResult(None)
        if self.name == "notice_cards" and self.action == "select":
            notice_id = self.filters.get("notice_id")
            rows = self.client.notice_cards
            if notice_id:
                rows = [row for row in rows if row.get("notice_id") == notice_id]
            return FakeResult(rows)
        if self.name == "notice_cards" and self.action == "update":
            row_id = self.filters.get("id") or "card-1"
            row = {"id": row_id, **self.payload}
            self.client.notice_cards = [
                row if existing.get("id") == row_id else existing
                for existing in self.client.notice_cards
            ]
            return FakeResult([row])
        if self.name == "notice_cards" and self.action == "delete":
            row_id = self.filters.get("id")
            notice_id = self.filters.get("notice_id")
            self.client.notice_cards = [
                row
                for row in self.client.notice_cards
                if not (
                    (row_id and row.get("id") == row_id)
                    or (notice_id and row.get("notice_id") == notice_id)
                )
            ]
            return FakeResult([])
        if self.name == "notice_cards" and self.action == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            saved = []
            for index, row in enumerate(rows, start=1):
                next_row = dict(row)
                next_row.setdefault("id", f"card-{len(self.client.notice_cards) + index}")
                self.client.notice_cards.append(next_row)
                saved.append(next_row)
            return FakeResult(saved)
        if self.name == "notice_card_translations" and self.action in {"select", "maybeSingle"}:
            notice_card_id = self.filters.get("notice_card_id")
            target_language = self.filters.get("target_language")
            matched = [
                row for row in self.client.notice_card_translations
                if (notice_card_id is None or row.get("notice_card_id") == notice_card_id)
                and (target_language is None or row.get("target_language") == target_language)
            ]
            if self.action == "maybeSingle":
                return FakeResult(matched[0] if matched else None)
            return FakeResult(matched)
        if self.name == "notice_card_translations" and self.action == "delete":
            notice_card_id = self.filters.get("notice_card_id")
            target_language = self.filters.get("target_language")
            self.client.notice_card_translations = [
                row
                for row in self.client.notice_card_translations
                if not (
                    (notice_card_id is None or row.get("notice_card_id") == notice_card_id)
                    and (target_language is None or row.get("target_language") == target_language)
                )
            ]
            return FakeResult([])
        if self.name == "notice_card_translations" and self.action == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            saved = []
            for index, row in enumerate(rows, start=1):
                next_row = dict(row)
                next_row.setdefault("id", f"translation-{len(self.client.notice_card_translations) + index}")
                self.client.notice_card_translations.append(next_row)
                saved.append(next_row)
            return FakeResult(saved)
        if self.name == "notice_card_translations" and self.action == "upsert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            saved = []
            for index, row in enumerate(rows, start=1):
                next_row = dict(row)
                existing = next(
                    (
                        current
                        for current in self.client.notice_card_translations
                        if current.get("notice_card_id") == next_row.get("notice_card_id")
                        and current.get("target_language") == next_row.get("target_language")
                    ),
                    None,
                )
                if existing:
                    existing.update(next_row)
                    saved.append(existing)
                    continue
                next_row.setdefault("id", f"translation-{len(self.client.notice_card_translations) + index}")
                self.client.notice_card_translations.append(next_row)
                saved.append(next_row)
            return FakeResult(saved)
        if self.name == "school_events" and self.action == "delete":
            row_id = self.filters.get("id")
            notice_id = self.filters.get("notice_id")
            self.client.school_events = [
                row
                for row in self.client.school_events
                if not (
                    (row_id and row.get("id") == row_id)
                    or (notice_id and row.get("notice_id") == notice_id)
                )
            ]
            return FakeResult([])
        if self.name == "school_events" and self.action == "select":
            notice_id = self.filters.get("notice_id")
            rows = self.client.school_events
            if notice_id:
                rows = [row for row in rows if row.get("notice_id") == notice_id]
            return FakeResult(rows)
        if self.name == "school_events" and self.action == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            saved = []
            for index, row in enumerate(rows, start=1):
                next_row = dict(row)
                next_row.setdefault("id", f"event-{len(self.client.school_events) + index}")
                self.client.school_events.append(next_row)
                saved.append(next_row)
            return FakeResult(saved)
        if self.name == "school_events" and self.action == "upsert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            saved = []
            for index, row in enumerate(rows, start=1):
                next_row = dict(row)
                existing = next(
                    (
                        current
                        for current in self.client.school_events
                        if current.get("notice_id") == next_row.get("notice_id")
                        and current.get("event_date") == next_row.get("event_date")
                    ),
                    None,
                )
                if existing:
                    existing.update(next_row)
                    saved.append(existing)
                    continue
                next_row.setdefault("id", f"event-{len(self.client.school_events) + index}")
                self.client.school_events.append(next_row)
                saved.append(next_row)
            return FakeResult(saved)
        if self.action in {"insert", "update", "upsert"}:
            return FakeResult([self.payload])
        return FakeResult([])


class FakeSupabase:
    def __init__(self):
        self.operations = []
        self.notice = None
        self.notice_cards = []
        self.notice_card_translations = []
        self.school_events = []
        self.children = []
        self.translations = []

    def table(self, name):
        return FakeTable(self, name)


class NoticeServiceSchoolOnlyTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_notice_uses_school_only_columns(self):
        supabase = FakeSupabase()
        settings = Mock(supabase_configured=True)

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
        ):
            result = await NoticeService().create_notice(
                {
                    "title": "가정통신문",
                    "raw_text": "본문",
                    "school_id": "school-1",
                    "source_url": "https://example.test/notice",
                },
            )

        inserted = result["notice"]
        self.assertEqual(inserted["school_id"], "school-1")
        self.assertEqual(inserted["detail_url"], "https://example.test/notice")
        self.assertNotIn("child_id", inserted)
        self.assertNotIn("source", inserted)

    def test_save_translation_does_not_write_removed_notice_columns(self):
        supabase = FakeSupabase()
        supabase.notice_cards = [
            {
                "id": "card-1",
                "notice_id": "notice-1",
                "type": "action",
                "order": 0,
                "content": {"ko": {"items": [{"text": "동의서 제출"}]}},
            },
        ]
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "동의서 제출",
            "final_translation": "Nộp giấy đồng ý",
            "source_hard_facts": {
                "hard_facts": {"actions_required": ["동의서 제출"]},
            },
            "target_hard_facts": {},
            "metadata": {
                "title": "동의서 안내",
                "title_target_language": "Hướng dẫn nộp giấy đồng ý",
                "card_sections": {
                    "action": {
                        "items": [{"text": "Nộp giấy đồng ý"}],
                    },
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1"},
            notice_id="notice-1",
            target_language="vi",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        notice_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notices" and op[1] == "update"
        ]
        self.assertEqual(notice_updates, [])
        self.assertNotIn("child_id", str(supabase.operations))
        self.assertEqual(saved["school_events"], [])

        card_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_cards" and op[1] == "update"
        ]
        self.assertEqual(card_updates, [])
        card_translation_upserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_card_translations" and op[1] == "upsert"
        ]
        translation_upserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_ai_translations" and op[1] == "upsert"
        ]
        self.assertEqual(
            card_translation_upserts[-1]["translated_content"]["items"],
            [{"text": "Nộp giấy đồng ý"}],
        )
        self.assertEqual(
            translation_upserts[-1]["translated_title"], "Hướng dẫn nộp giấy đồng ý"
        )
        self.assertIsNone(translation_upserts[-1]["translated_location"])

    def test_save_translation_title_falls_back_to_first_translation_line(self):
        supabase = FakeSupabase()
        supabase.notice_cards = [
            {
                "id": "card-1",
                "notice_id": "notice-1",
                "type": "action",
                "order": 0,
                "content": {"ko": {"items": [{"text": "동의서 제출"}]}},
            },
        ]
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "동의서 제출",
            "final_translation": "## Nộp giấy đồng ý\n\n상세 안내",
            "source_hard_facts": {
                "hard_facts": {"actions_required": ["동의서 제출"]},
            },
            "target_hard_facts": {},
            "metadata": {
                "title": "동의서 안내",
                "card_sections": {
                    "action": {
                        "items": [{"text": "Nộp giấy đồng ý"}],
                    },
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1"},
            notice_id="notice-1",
            target_language="vi",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        translation_upserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_ai_translations" and op[1] == "upsert"
        ]
        self.assertEqual(translation_upserts[-1]["translated_title"], "Nộp giấy đồng ý")

    async def test_translate_notice_uses_cached_translation_before_ai_pipeline(self):
        supabase = FakeSupabase()
        supabase.notice = {
            "id": "notice-1",
            "school_id": "school-1",
            "title": "가정통신문",
            "original_text": "원문",
            "source_hard_facts": {
                "hard_facts": {
                    "dates": [{"normalized": "2026-06-12"}],
                    "deadlines": [{"normalized": "2026-06-12"}],
                    "locations": [{"normalized": "강당"}],
                },
            },
            "due_date": "2026-06-12",
            "event_dates": ["2026-06-12"],
            "event_location": "강당",
            "extracted_content": {},
            "status": "done",
            "detail_url": None,
            "source_post_uid": None,
            "crawl_result": None,
        }
        supabase.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "vi",
                "translated_text": "Thông báo",
                "validation_status": "passed",
                "target_hard_facts": {
                    "hard_facts": {
                        "dates": [{"normalized": "2026-06-12"}],
                        "deadlines": [{"normalized": "2026-06-12"}],
                        "locations": [{"normalized": "Gym"}],
                    },
                },
                "ingredient_identity_map": {},
                "validation": {},
                "metadata": {"title": "가정통신문 제목"},
                "raw_pipeline": {},
            },
        ]
        settings = Mock(supabase_configured=True, gemini_configured=True)

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
            patch("app.services.notice_service.build_json_client") as gemini_factory,
        ):
            result = await NoticeService().translate_notice(
                notice_id="notice-1",
                target_language="vi",
            )

        self.assertEqual(result["translation"], "Thông báo")
        self.assertTrue(result["saved"]["cached"])
        self.assertFalse(result["admin_review"]["required"])
        gemini_factory.assert_not_called()

    async def test_translate_notice_ko_short_circuits_without_gemini(self):
        supabase = FakeSupabase()
        supabase.notice = {
            "id": "notice-1",
            "title": "가정통신문",
            "original_text": "한국어 원문",
            "detail_url": None,
            "crawl_result": None,
        }
        settings = Mock(supabase_configured=True, gemini_configured=False, crawler_timeout_seconds=5)

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
        ):
            result = await NoticeService().translate_notice(
                notice_id="notice-1",
                target_language="ko",
            )

        self.assertEqual(result["translation"], "한국어 원문")
        self.assertEqual(result["target_language"], "ko")
        self.assertEqual(result["status"], "ready_to_save")

    async def test_translate_text_ko_short_circuits_without_gemini(self):
        settings = Mock(gemini_configured=False)

        with patch("app.services.notice_service.get_settings", return_value=settings):
            result = await NoticeService().translate_text(
                source_text="한국어 문장",
                target_language="ko",
            )

        self.assertEqual(result["translation"], "한국어 문장")
        self.assertEqual(result["target_language"], "ko")
        self.assertEqual(result["status"], "ready_to_save")

    async def test_translate_text_message_to_ko_uses_best_effort_translation(self):
        settings = Mock(gemini_configured=True)
        gemini = Mock()

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.build_json_client", return_value=gemini),
            patch.object(
                NoticeService,
                "_translate_message_to_korean",
                AsyncMock(
                    return_value={
                        "status": "ready_to_save",
                        "final_translation": "안녕하세요 선생님, 오늘 아이가 병원에 다녀와서 지각할 예정입니다.",
                    }
                ),
            ) as fallback_mock,
        ):
            result = await NoticeService().translate_text(
                source_text="Hello teacher, my child will be late today after a hospital visit.",
                target_language="ko",
                translation_kind="message_to_ko",
            )

        fallback_mock.assert_awaited_once()
        self.assertEqual(result["target_language"], "ko")
        self.assertEqual(
            result["translation"],
            "안녕하세요 선생님, 오늘 아이가 병원에 다녀와서 지각할 예정입니다.",
        )

    async def test_refresh_notice_canonical_artifacts_builds_canonical_cards_when_missing(self):
        supabase = FakeSupabase()
        supabase.notice = {
            "id": "notice-1",
            "school_id": "school-1",
            "title": "가정통신문",
            "original_text": "한국어 원문",
            "source_hard_facts": {},
            "due_date": None,
            "event_dates": [],
            "event_location": None,
            "extracted_content": {},
            "status": "done",
            "detail_url": None,
            "source_post_uid": None,
            "crawl_result": None,
        }
        settings = Mock(supabase_configured=True, gemini_configured=True, crawler_timeout_seconds=5)

        async def fake_generate_json(*, prompt, temperature, model=None):
            if '"hard_facts"' in prompt and 'SOURCE_TEXT' in prompt:
                return {
                    "hard_facts": {
                        "actions_required": [{"raw_text": "신청서 제출", "normalized": "신청서 제출"}],
                        "deadlines": [{"raw_text": "2026년 6월 10일", "normalized": "2026-06-10"}],
                        "dates": [{"raw_text": "2026년 6월 12일", "normalized": "2026-06-12"}],
                    },
                }
            return {
                "title": "가정통신문",
                "summary_ko": "행사 안내",
                "actions_required": ["신청서 제출"],
                "deadlines": ["2026-06-10"],
                "important_dates": ["2026-06-12"],
                "card_sections": {
                    "action": {"items": [{"text": "신청서 제출", "hint": "2026-06-10"}]},
                    "schedule": {"items": [{"text": "2026-06-12"}]},
                },
            }

        gemini = SimpleNamespace(generate_json=AsyncMock(side_effect=fake_generate_json))

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
            patch("app.services.notice_service.build_json_client", return_value=gemini),
        ):
            result = await NoticeService().refresh_notice_canonical_artifacts(
                notice_id="notice-1",
                source_text=None,
            )

        self.assertEqual(result["translation"], "한국어 원문")
        card_inserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_cards" and op[1] == "insert"
        ]
        self.assertTrue(card_inserts)
        notice_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notices" and op[1] == "update"
        ]
        self.assertEqual(notice_updates[-1]["due_date"], "2026-06-10")
        self.assertEqual(notice_updates[-1]["event_dates"], ["2026-06-12", "2026-06-10"])

    async def test_translate_notice_cached_warning_status_is_treated_as_passed(self):
        supabase = FakeSupabase()
        supabase.notice = {
            "id": "notice-1",
            "school_id": "school-1",
            "title": "가정통신문",
            "original_text": "원문",
            "source_hard_facts": {
                "hard_facts": {"dates": [{"normalized": "2026-06-12"}]},
            },
            "due_date": None,
            "event_dates": ["2026-06-12"],
            "event_location": None,
            "extracted_content": {},
            "status": "done",
            "detail_url": None,
            "source_post_uid": None,
            "crawl_result": None,
        }
        supabase.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "vi",
                "translated_text": "검토가 필요한 번역",
                "validation_status": "passed",
                "target_hard_facts": {
                    "hard_facts": {"dates": [{"normalized": "2026-06-12"}]},
                },
            },
        ]
        settings = Mock(supabase_configured=True, gemini_configured=True)

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
            patch("app.services.notice_service.build_json_client") as gemini_factory,
        ):
            result = await NoticeService().translate_notice(
                notice_id="notice-1",
                target_language="vi",
            )

        self.assertEqual(result["translation"], "검토가 필요한 번역")
        self.assertTrue(result["saved"]["cached"])
        self.assertFalse(result["admin_review"]["required"])
        gemini_factory.assert_not_called()

    async def test_translate_notice_bypasses_cache_when_source_text_is_explicit(self):
        supabase = FakeSupabase()
        supabase.notice = {
            "id": "notice-1",
            "school_id": "school-1",
            "title": "가정통신문",
            "original_text": "원문",
            "source_hard_facts": {},
            "due_date": None,
            "event_dates": [],
            "event_location": None,
            "extracted_content": {},
            "status": "done",
            "detail_url": None,
            "source_post_uid": None,
            "crawl_result": None,
        }
        supabase.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "vi",
                "translated_text": "Old cached translation",
                "validation_status": "passed",
            },
        ]
        settings = Mock(supabase_configured=True, gemini_configured=True, crawler_timeout_seconds=5)
        pipeline_run = AsyncMock(
            return_value={
                "status": "ready_to_save",
                "admin_review": {"required": False, "reason": None},
                "final_translation": "Fresh translation",
                "source_text": "수정된 원문",
                "source_hard_facts": {},
                "target_hard_facts": {},
                "validation": {},
                "metadata": {"title": "새 제목"},
                "raw_steps": {},
            }
        )
        pipeline_instance = SimpleNamespace(run=pipeline_run)

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
            patch("app.services.notice_service.build_json_client", return_value=object()),
            patch("app.services.notice_service.TranslationPipeline", return_value=pipeline_instance),
        ):
            result = await NoticeService().translate_notice(
                notice_id="notice-1",
                target_language="vi",
                source_text="수정된 원문",
            )

        self.assertEqual(result["translation"], "Fresh translation")
        self.assertNotIn("cached", result["saved"])
        pipeline_run.assert_called_once()

    async def test_translate_notice_retranslates_when_notice_lacks_canonical_fields(self):
        supabase = FakeSupabase()
        supabase.notice = {
            "id": "notice-1",
            "school_id": "school-1",
            "title": "가정통신문",
            "original_text": "원문",
            "source_hard_facts": {},
            "due_date": None,
            "event_dates": [],
            "event_location": None,
            "extracted_content": {},
            "status": "done",
            "detail_url": None,
            "source_post_uid": None,
            "crawl_result": None,
        }
        supabase.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "vi",
                "translated_text": "Thông báo",
                "validation_status": "passed",
                "target_hard_facts": {},
                "ingredient_identity_map": {},
                "validation": {},
                "metadata": {"title": "가정통신문 제목"},
                "raw_pipeline": {},
            },
        ]
        settings = Mock(supabase_configured=True, gemini_configured=True)
        pipeline_run = AsyncMock(
            return_value={
                "status": "ready_to_save",
                "admin_review": {"required": False, "reason": None},
                "final_translation": "새로 번역한 결과",
                "source_text": "원문",
                "source_hard_facts": {
                    "hard_facts": {"deadlines": [{"normalized": "2026-06-20"}]},
                },
                "target_hard_facts": {
                    "hard_facts": {"deadlines": [{"normalized": "2026-06-20"}]},
                },
                "validation_status": "passed",
                "metadata": {"title": "가정통신문 제목"},
                "raw_steps": {},
            }
        )
        pipeline_instance = SimpleNamespace(run=pipeline_run)

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
            patch("app.services.notice_service.build_json_client", return_value=object()) as gemini_factory,
            patch("app.services.notice_service.TranslationPipeline", return_value=pipeline_instance),
        ):
            result = await NoticeService().translate_notice(
                notice_id="notice-1",
                target_language="vi",
            )

        self.assertEqual(result["translation"], "새로 번역한 결과")
        self.assertNotIn("cached", result["saved"])
        school_event_inserts = [op for op in supabase.operations if op[0] == "school_events" and op[1] == "insert"]
        self.assertEqual(len(school_event_inserts), 0)
        pipeline_run.assert_called_once()
        gemini_factory.assert_called_once()

    async def test_translate_notice_uses_cached_translation_even_when_validation_failed(self):
        supabase = FakeSupabase()
        supabase.notice = {
            "id": "notice-1",
            "school_id": "school-1",
            "title": "가정통신문",
            "original_text": "원문",
            "source_hard_facts": {
                "hard_facts": {"deadlines": [{"normalized": "2026-06-21"}]},
            },
            "due_date": "2026-06-21",
            "event_dates": ["2026-06-21"],
            "event_location": None,
            "extracted_content": {},
            "status": "done",
            "detail_url": None,
            "source_post_uid": None,
            "crawl_result": None,
        }
        supabase.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "vi",
                "translated_text": "검증 경고가 있는 번역",
                "validation_status": "failed",
                "target_hard_facts": {
                    "hard_facts": {"deadlines": [{"normalized": "2026-06-21"}]},
                },
                "ingredient_identity_map": {},
                "validation": {},
                "metadata": {},
                "raw_pipeline": {},
            },
        ]
        settings = Mock(supabase_configured=True, gemini_configured=True)

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
            patch("app.services.notice_service.build_json_client") as gemini_factory,
        ):
            result = await NoticeService().translate_notice(
                notice_id="notice-1",
                target_language="vi",
            )

        self.assertEqual(result["translation"], "검증 경고가 있는 번역")
        self.assertTrue(result["saved"]["cached"])
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["admin_review"]["required"])
        gemini_factory.assert_not_called()

    def test_same_language_retranslation_removes_stale_card_content(self):
        supabase = FakeSupabase()
        supabase.notice_cards = [
            {
                "id": "card-1",
                "notice_id": "notice-1",
                "type": "action",
                "order": 0,
                "content": {"ko": {"items": [{"text": "기존 한국어 카드"}]}},
            },
        ]
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "동의서 제출",
            "final_translation": "Nộp giấy đồng ý",
            "source_hard_facts": {
                "hard_facts": {"actions_required": ["동의서 제출"]},
            },
            "target_hard_facts": {},
            "metadata": {
                "card_sections": {
                    "action": {
                        "items": [{"text": "Nộp giấy đồng ý"}],
                    },
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1"},
            notice_id="notice-1",
            target_language="vi",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        deleted_card_ids = [
            op[3]
            for op in supabase.operations
            if op[0] == "notice_cards" and op[1] == "eq" and op[2] == "id"
        ]
        self.assertEqual(deleted_card_ids, [])
        self.assertEqual(saved["cards"], [])
        card_translation_upserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_card_translations" and op[1] == "upsert"
        ]
        self.assertEqual(
            card_translation_upserts[-1]["translated_content"]["items"],
            [{"text": "Nộp giấy đồng ý"}],
        )

    def test_same_language_retranslation_with_no_cards_clears_stale_content(self):
        supabase = FakeSupabase()
        supabase.notice_cards = [
            {
                "id": "card-1",
                "notice_id": "notice-1",
                "type": "supplies",
                "order": 0,
                "content": {"ko": {"items": [{"text": "기존 한국어 카드"}]}},
            },
        ]
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "안내문",
            "final_translation": "Thông báo",
            "source_hard_facts": {"hard_facts": {}},
            "target_hard_facts": {"hard_facts": {}},
            "metadata": {},
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1"},
            notice_id="notice-1",
            target_language="vi",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        deleted_card_ids = [
            op[3]
            for op in supabase.operations
            if op[0] == "notice_cards" and op[1] == "eq" and op[2] == "id"
        ]
        self.assertEqual(deleted_card_ids, [])
        self.assertEqual(saved["cards"], [])

    def test_non_ko_translation_backfills_notice_cards_before_card_translations(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "준비물을 챙기고 신청서를 제출하세요.",
            "final_translation": "Bring supplies and submit the form.",
            "source_hard_facts": {"hard_facts": {}},
            "target_hard_facts": {"hard_facts": {}},
            "metadata": {
                "target_language": "en",
                "summary_ko": "준비물과 신청 안내",
                "deadlines": ["2026-10-05"],
                "card_sections_ko": {
                    "action": {"items": [{"text": "신청서 제출", "hint": "2026-10-05"}]},
                },
                "card_sections_target_language": {
                    "action": {"items": [{"text": "Submit the application form", "hint": "2026-10-05"}]},
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="en",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        card_inserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_cards" and op[1] == "insert"
        ]
        self.assertTrue(card_inserts)
        translation_upserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_card_translations" and op[1] == "upsert"
        ]
        self.assertEqual(
            translation_upserts[-1]["translated_content"]["items"],
            [{"text": "Submit the application form", "hint": "2026-10-05"}],
        )
        self.assertEqual(saved["card_translations"][-1]["target_language"], "en")

    def test_non_ko_save_without_translated_card_sections_keeps_existing_card_translations(self):
        supabase = FakeSupabase()
        supabase.notice_cards = [
            {
                "id": "card-1",
                "notice_id": "notice-1",
                "type": "action",
                "order": 0,
                "content": {"ko": {"items": [{"text": "신청서 제출"}]}},
            },
        ]
        supabase.notice_card_translations = [
            {
                "id": "translation-1",
                "notice_card_id": "card-1",
                "target_language": "en",
                "translated_content": {"items": [{"text": "Submit the form"}]},
            },
        ]
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "신청서 제출",
            "final_translation": "Submit the form",
            "source_hard_facts": {"hard_facts": {"actions_required": ["신청서 제출"]}},
            "target_hard_facts": {},
            "metadata": {
                "target_language": "en",
                "title": "신청 안내",
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="en",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        translation_deletes = [
            op
            for op in supabase.operations
            if op[0] == "notice_card_translations" and op[1] == "delete"
        ]
        self.assertEqual(translation_deletes, [])
        self.assertEqual(saved["card_translations"], [])


class OptionalSingleCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    class NoMaybeSingleQuery:
        def __init__(self, table_name: str, client: "OptionalSingleCompatibilityTests.NoMaybeSingleSupabase"):
            self.table_name = table_name
            self.client = client
            self.filters: dict[str, str] = {}

        def select(self, _columns):
            return self

        def eq(self, column, value):
            self.filters[column] = value
            return self

        def execute(self):
            if self.table_name == "notice_ai_translations":
                rows = [
                    row
                    for row in self.client.translations
                    if row.get("notice_id") == self.filters.get("notice_id")
                    and row.get("target_language") == self.filters.get("target_language")
                ]
                return SimpleNamespace(data=rows)
            if self.table_name == "notice_cards":
                rows = [
                    row
                    for row in self.client.notice_cards
                    if row.get("notice_id") == self.filters.get("notice_id")
                ]
                return SimpleNamespace(data=rows)
            if self.table_name == "notice_card_translations":
                rows = [
                    row
                    for row in self.client.notice_card_translations
                    if row.get("notice_card_id") == self.filters.get("notice_card_id")
                    and row.get("target_language") == self.filters.get("target_language")
                ]
                return SimpleNamespace(data=rows)
            return SimpleNamespace(data=[])

    class NoMaybeSingleSupabase:
        def __init__(self):
            self.translations = []
            self.notice_cards = []
            self.notice_card_translations = []

        def table(self, name):
            return OptionalSingleCompatibilityTests.NoMaybeSingleQuery(name, self)

    def test_execute_optional_single_handles_list_response_without_maybe_single(self):
        query = SimpleNamespace(execute=lambda: SimpleNamespace(data=[{"id": "row-1"}]))
        self.assertEqual(_execute_optional_single(query), {"id": "row-1"})

    def test_usable_cached_translation_supports_python_client_without_maybe_single(self):
        supabase = self.NoMaybeSingleSupabase()
        supabase.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "en",
                "translated_text": "Translated",
                "validation_status": "passed",
            },
        ]

        row = _usable_cached_translation(
            supabase=supabase,
            notice_id="notice-1",
            target_language="en",
        )

        self.assertEqual(row["translated_text"], "Translated")

    def test_has_complete_card_translation_cache_supports_python_client_without_maybe_single(self):
        supabase = self.NoMaybeSingleSupabase()
        supabase.notice_cards = [
            {"id": "card-1", "notice_id": "notice-1"},
            {"id": "card-2", "notice_id": "notice-1"},
        ]
        supabase.notice_card_translations = [
            {"id": "translation-1", "notice_card_id": "card-1", "target_language": "en"},
            {"id": "translation-2", "notice_card_id": "card-2", "target_language": "en"},
        ]

        complete = _has_complete_card_translation_cache(
            supabase=supabase,
            notice_id="notice-1",
            target_language="en",
        )

        self.assertTrue(complete)

    async def test_translate_notice_retranslates_when_card_translation_cache_is_missing(self):
        supabase = FakeSupabase()
        supabase.notice = {
            "id": "notice-1",
            "school_id": "school-1",
            "title": "가정통신문",
            "original_text": "원문",
            "source_hard_facts": {
                "hard_facts": {"actions_required": ["동의서 제출"]},
            },
            "due_date": None,
            "event_dates": [],
            "event_location": None,
            "extracted_content": {},
            "status": "done",
            "detail_url": None,
            "source_post_uid": None,
            "crawl_result": None,
        }
        supabase.notice_cards = [
            {
                "id": "card-1",
                "notice_id": "notice-1",
                "type": "action",
                "order": 0,
                "content": {"ko": {"items": [{"text": "동의서 제출"}]}},
            },
        ]
        supabase.translations = [
            {
                "notice_id": "notice-1",
                "target_language": "vi",
                "translated_text": "Old cached translation",
                "validation_status": "passed",
            },
        ]
        settings = Mock(supabase_configured=True, gemini_configured=True)
        pipeline_run = AsyncMock(
            return_value={
                "status": "ready_to_save",
                "admin_review": {"required": False, "reason": None},
                "final_translation": "Fresh translation",
                "source_text": "원문",
                "source_hard_facts": {
                    "hard_facts": {"actions_required": ["동의서 제출"]},
                },
                "target_hard_facts": {},
                "validation_status": "passed",
                "metadata": {
                    "card_sections": {
                        "action": {
                            "items": [{"text": "Nộp giấy đồng ý"}],
                        },
                    },
                },
                "raw_steps": {},
            }
        )
        pipeline_instance = SimpleNamespace(run=pipeline_run)

        with (
            patch("app.services.notice_service.get_settings", return_value=settings),
            patch("app.services.notice_service.get_supabase_client", return_value=supabase),
            patch("app.services.notice_service.build_json_client", return_value=object()),
            patch("app.services.notice_service.TranslationPipeline", return_value=pipeline_instance),
        ):
            result = await NoticeService().translate_notice(
                notice_id="notice-1",
                target_language="vi",
            )

        self.assertEqual(result["translation"], "Fresh translation")
        self.assertNotIn("cached", result["saved"])
        pipeline_run.assert_called_once()

    def test_save_translation_creates_school_events(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "현장체험학습은 2026-06-12에 진행됩니다.",
            "final_translation": "Chuyến tham quan sẽ diễn ra vào ngày 2026-06-12.",
            "source_hard_facts": {
                "hard_facts": {
                    "dates": [{"raw_text": "2026년 6월 12일", "normalized": "2026-06-12"}],
                    "deadlines": [{"raw_text": "2026년 6월 12일까지", "normalized": "2026-06-12"}],
                    "locations": [{"raw_text": "서울숲", "normalized": "서울숲"}],
                },
            },
            "target_hard_facts": {},
            "metadata": {
                "title": "현장체험학습 안내",
                "summary_target_language": "행사 일정 안내",
                "card_sections": {
                    "schedule": {
                        "items": [
                            {"text": "Ngày tham quan: 2026-06-12", "hint": "09:00 - 16:00"},
                            {"text": "Địa điểm: Seoul Forest"},
                        ],
                    },
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        school_event_inserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "school_events" and op[1] == "upsert"
        ]
        self.assertEqual(len(school_event_inserts), 1)
        self.assertEqual(len(school_event_inserts[0]), 1)
        self.assertEqual(school_event_inserts[0][0]["school_id"], "school-1")
        self.assertEqual(school_event_inserts[0][0]["event_date"], "2026-06-12")
        self.assertEqual(school_event_inserts[0][0]["location"], "서울숲")
        self.assertEqual(saved["school_events"][0]["title"], "현장체험학습 안내")
        self.assertEqual(saved["school_events"][0]["event_kinds"], ["deadline", "event"])
        self.assertEqual(saved["cards"], [])

        notice_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notices" and op[1] == "update"
        ]
        self.assertEqual(notice_updates[-1]["due_date"], "2026-06-12")
        self.assertEqual(notice_updates[-1]["event_dates"], ["2026-06-12"])
        self.assertEqual(notice_updates[-1]["event_location"], "서울숲")

    def test_failed_validation_translation_still_creates_school_events(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "설문 기간은 2026.5.18.~05.22. 입니다.",
            "final_translation": "Thời gian khảo sát là từ ngày 18/5/2026 đến 22/5/2026.",
            "source_hard_facts": {
                "hard_facts": {
                    "dates": [
                        {"raw_text": "2026.5.18.~05.22.", "normalized": "2026-05-18 ~ 2026-05-22"},
                        {"raw_text": "2026.5.20.", "normalized": "2026-05-20"},
                    ],
                    "deadlines": [
                        {"raw_text": "05.22.", "normalized": "2026-05-22"},
                    ],
                },
            },
            "target_hard_facts": {},
            "metadata": {
                "title": "설문 조사 안내",
                "summary_target_language": "설문 일정 안내",
                "validation_status": "failed",
                "validation_failure_reason": "hard_fact_validation_failed",
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        translation_upserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_ai_translations" and op[1] == "upsert"
        ]
        self.assertEqual(translation_upserts[-1]["validation_status"], "passed")
        self.assertNotIn("source_text", translation_upserts[-1])
        self.assertNotIn("ingredient_identity_map", translation_upserts[-1])
        self.assertNotIn("validation", translation_upserts[-1])
        self.assertNotIn("raw_pipeline", translation_upserts[-1])
        self.assertEqual({row["event_date"] for row in saved["school_events"]}, {"2026-05-18", "2026-05-20", "2026-05-22"})
        by_date = {row["event_date"]: row["event_kinds"] for row in saved["school_events"]}
        self.assertEqual(by_date["2026-05-18"], ["event"])
        self.assertEqual(by_date["2026-05-20"], ["event"])
        self.assertEqual(by_date["2026-05-22"], ["deadline"])
        notice_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notices" and op[1] == "update"
        ]
        self.assertEqual(notice_updates[-1]["event_dates"], ["2026-05-18", "2026-05-20", "2026-05-22"])

    def test_yearless_dates_fall_back_to_2026_for_school_events(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "준비물은 6월 10일에 가져오고, 신청서는 05.22.까지 제출하세요.",
            "final_translation": "Bring supplies on June 10 and submit the form by May 22.",
            "source_hard_facts": {
                "hard_facts": {
                    "dates": [
                        {"raw_text": "6월 10일", "normalized": None, "inferred_year_required": True},
                    ],
                    "deadlines": [
                        {"raw_text": "05.22.", "normalized": None, "inferred_year_required": True},
                    ],
                },
            },
            "target_hard_facts": {},
            "metadata": {"title": "준비물 안내"},
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        self.assertEqual(
            {row["event_date"] for row in saved["school_events"]},
            {"2026-05-22", "2026-06-10"},
        )
        by_date = {row["event_date"]: row["event_kinds"] for row in saved["school_events"]}
        self.assertEqual(by_date["2026-06-10"], ["event"])
        self.assertEqual(by_date["2026-05-22"], ["deadline"])
        notice_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notices" and op[1] == "update"
        ]
        self.assertEqual(notice_updates[-1]["due_date"], "2026-05-22")
        self.assertEqual(notice_updates[-1]["event_dates"], ["2026-06-10", "2026-05-22"])

    def test_metadata_fallback_creates_cards_and_event_dates_without_source_hard_facts(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "안내문",
            "final_translation": "Notice",
            "source_hard_facts": {"hard_facts": {}},
            "target_hard_facts": {"hard_facts": {}},
            "metadata": {
                "summary_ko": "운동회 안내",
                "important_dates": ["2026-10-12"],
                "deadlines": ["2026-10-05"],
                "target_language": "en",
                "card_sections_ko": {
                    "supplies": {
                        "items": [{"text": "운동화"}, {"text": "물"}],
                    },
                    "action": {
                        "items": [{"text": "참가 신청서 제출", "hint": "2026-10-05"}],
                    },
                    "schedule": {
                        "items": [{"text": "운동회: 2026-10-12"}, {"text": "장소: 운동장"}],
                    },
                },
                "card_sections_target_language": {
                    "supplies": {
                        "items": [{"text": "Sneakers"}, {"text": "Water"}],
                    },
                    "action": {
                        "items": [{"text": "Submit the participation form", "hint": "2026-10-05"}],
                    },
                    "schedule": {
                        "items": [{"text": "Sports day: 2026-10-12"}, {"text": "Location: Playground"}],
                    },
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        self.assertEqual([card["type"] for card in saved["cards"]], ["action"])
        self.assertEqual(
            saved["cards"][0]["content"]["ko"]["items"],
            [{"text": "참가 신청서 제출", "hint": "2026-10-05"}],
        )
        notice_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notices" and op[1] == "update"
        ]
        self.assertEqual(notice_updates[-1]["due_date"], "2026-10-05")
        self.assertEqual(notice_updates[-1]["event_dates"], ["2026-10-12", "2026-10-05"])
        self.assertEqual(notice_updates[-1]["event_location"], "운동장")

    def test_non_ko_card_sections_do_not_overwrite_ko_canonical_cards(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "신청 안내",
            "final_translation": "Application guide",
            "source_hard_facts": {"hard_facts": {}},
            "target_hard_facts": {"hard_facts": {}},
            "target_language": "en",
            "metadata": {
                "target_language": "en",
                "summary_ko": "신청 안내",
                "actions_required": ["Submit the application form"],
                "card_sections": {
                    "action": {
                        "items": [{"text": "Submit the application form"}],
                    },
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="en",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        self.assertEqual(saved["cards"], [])
        card_translation_inserts = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_card_translations" and op[1] == "insert"
        ]
        self.assertEqual(card_translation_inserts, [])

    def test_english_card_sections_ko_are_filtered_from_canonical_notice_cards(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "신청서를 제출하세요.",
            "final_translation": "Submit the application form.",
            "source_hard_facts": {
                "hard_facts": {"actions_required": ["신청서 제출"]},
            },
            "target_hard_facts": {},
            "metadata": {
                "target_language": "en",
                "summary_ko": "Application guide",
                "actions_required": ["Submit the application form"],
                "card_sections_ko": {
                    "action": {
                        "items": [{"text": "Submit the application form", "hint": "2026-10-05"}],
                    },
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        self.assertEqual(
            saved["cards"][0]["content"]["ko"]["items"],
            [{"text": "신청서 제출"}],
        )

    def test_sanitize_metadata_drops_english_summary_ko_and_actions_required(self):
        metadata = {
            "target_language": "en",
            "summary_ko": "Application guide",
            "actions_required": ["Submit the application form"],
            "card_sections_ko": {
                "action": {
                    "items": [{"text": "Submit the application form"}],
                },
            },
        }

        pipeline_result = {
            "source_text": "신청서를 제출하세요.",
            "metadata": metadata,
        }

        next_result = _with_sanitized_metadata(pipeline_result)
        next_metadata = next_result["metadata"]
        self.assertIsNone(next_metadata["summary_ko"])
        self.assertEqual(next_metadata["actions_required"], [])
        self.assertEqual(next_metadata["card_sections_ko"]["action"]["items"], [])

    def test_save_translation_filters_english_source_actions_from_canonical_notice_cards(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "신청서를 제출하세요.",
            "final_translation": "Submit the application form.",
            "source_hard_facts": {
                "hard_facts": {
                    "actions_required": [
                        {"raw_text": "Submit the application form", "normalized": "Submit the application form"},
                    ],
                    "submissions": [
                        {"raw_text": "Application form", "normalized": "Application form"},
                    ],
                },
            },
            "target_hard_facts": {},
            "metadata": {
                "target_language": "en",
                "summary_ko": "신청 안내",
                "actions_required": ["Submit the application form"],
                "card_sections_ko": {
                    "action": {
                        "items": [{"text": "Submit the application form", "hint": "2026-10-05"}],
                    },
                },
            },
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        self.assertEqual(saved["cards"], [])

    def test_save_translation_filters_footer_dates_from_event_dates(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "홈페이지 가입 안내\n\n가입 절차를 확인하세요.\n\n2026 3. 4.\n부천부흥초등학교장",
            "final_translation": "홈페이지 가입 안내\n\n가입 절차를 확인하세요.",
            "source_hard_facts": {
                "hard_facts": {
                    "dates": [
                        {"raw_text": "2026 3. 4.", "normalized": "2026-03-04"},
                    ],
                },
            },
            "target_hard_facts": {},
            "metadata": {"title": "홈페이지 가입 안내"},
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        notice_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notices" and op[1] == "update"
        ]
        self.assertEqual(notice_updates[-1]["event_dates"], [])
        self.assertEqual(saved["school_events"], [])
        self.assertEqual(
            saved["notice_patch"]["source_hard_facts"]["hard_facts"]["dates"],
            [],
        )

    def test_save_translation_keeps_real_event_date_when_same_date_also_appears_in_admin_meta(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": (
                "현장체험학습 안내\n"
                "체험학습일: 2026년 5월 22일\n"
                "장소: 과천과학관\n\n"
                "작성일 2026.05.22\n"
                "부천부흥초등학교"
            ),
            "final_translation": "현장체험학습 안내",
            "source_hard_facts": {
                "hard_facts": {
                    "dates": [
                        {"raw_text": "2026년 5월 22일", "normalized": "2026-05-22"},
                    ],
                    "locations": [
                        {"raw_text": "과천과학관", "normalized": "과천과학관"},
                    ],
                },
            },
            "target_hard_facts": {},
            "metadata": {"title": "현장체험학습 안내"},
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        notice_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notices" and op[1] == "update"
        ]
        self.assertEqual(notice_updates[-1]["event_dates"], ["2026-05-22"])
        self.assertEqual(saved["school_events"][0]["event_date"], "2026-05-22")
        self.assertEqual(saved["school_events"][0]["event_kinds"], ["event"])

    def test_save_translation_upserts_school_events_and_cleans_stale_dates(self):
        supabase = FakeSupabase()
        supabase.school_events = [
            {
                "id": "event-1",
                "notice_id": "notice-1",
                "school_id": "school-1",
                "event_date": "2026-05-20",
                "title": "기존 일정",
                "event_kinds": ["event"],
            },
            {
                "id": "event-2",
                "notice_id": "notice-1",
                "school_id": "school-1",
                "event_date": "2026-05-21",
                "title": "사라질 일정",
                "event_kinds": ["event"],
            },
        ]
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "행사일은 2026년 5월 20일입니다.",
            "final_translation": "행사일은 2026년 5월 20일입니다.",
            "source_hard_facts": {
                "hard_facts": {
                    "dates": [{"raw_text": "2026년 5월 20일", "normalized": "2026-05-20"}],
                },
            },
            "target_hard_facts": {},
            "metadata": {"title": "새 일정 제목"},
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        self.assertEqual(len(saved["school_events"]), 1)
        self.assertEqual(saved["school_events"][0]["event_date"], "2026-05-20")
        self.assertEqual(saved["school_events"][0]["title"], "새 일정 제목")
        self.assertEqual(
            {row["event_date"] for row in supabase.school_events if row.get("notice_id") == "notice-1"},
            {"2026-05-20"},
        )

    def test_save_translation_filters_prohibited_materials(self):
        supabase = FakeSupabase()
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "위험 물품 및 학생 소지 금지 물품 안내\n- 장난감 칼, 라이터 등은 반입금지입니다.",
            "final_translation": "위험 물품 및 학생 소지 금지 물품 안내",
            "source_hard_facts": {
                "hard_facts": {
                    "materials": [
                        {"raw_text": "장난감 칼", "normalized": "장난감 칼"},
                        {"raw_text": "라이터", "normalized": "라이터"},
                    ],
                    "warnings": [
                        {"raw_text": "장난감 칼, 라이터 등은 반입금지입니다.", "normalized": "prohibited"},
                    ],
                },
            },
            "target_hard_facts": {},
            "metadata": {"title": "위험 물품 안내"},
            "admin_review": {"required": False, "reason": None},
            "validation": {},
            "raw_steps": {},
        }

        saved = NoticeService()._save_translation_result(
            supabase=supabase,
            notice={"school_id": "school-1", "title": "원본 제목"},
            notice_id="notice-1",
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata={"school_id": "school-1"},
        )

        self.assertEqual(
            saved["notice_patch"]["source_hard_facts"]["hard_facts"]["materials"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
