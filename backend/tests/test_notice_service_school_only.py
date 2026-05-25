import unittest
from unittest.mock import Mock, patch

from app.services.notice_service import NoticeService


class FakeResult:
    def __init__(self, data=None):
        self.data = data or []


class FakeTable:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.action = None
        self.payload = None

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
        self.client.operations.append((self.name, "eq", column, value))
        return self

    def execute(self):
        if self.name == "notice_cards" and self.action == "select":
            return FakeResult(self.client.notice_cards)
        if self.name == "notice_cards" and self.action == "update":
            row = {"id": "card-1", **self.payload}
            return FakeResult([row])
        if self.name == "notice_cards" and self.action == "delete":
            return FakeResult([])
        if self.name == "notice_cards" and self.action == "insert":
            return FakeResult(self.payload if isinstance(self.payload, list) else [self.payload])
        if self.action in {"insert", "update", "upsert"}:
            return FakeResult([self.payload])
        return FakeResult([])


class FakeSupabase:
    def __init__(self):
        self.operations = []
        self.notice_cards = []

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
                "type": "action",
                "order": 0,
                "content": {"en": {"title": "To-do", "items": ["Bring form"]}},
            },
        ]
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "동의서 제출",
            "final_translation": "Nộp giấy đồng ý",
            "source_hard_facts": {
                "hard_facts": {"actions_required": ["동의서 제출"]},
            },
            "target_hard_facts": {
                "hard_facts": {"actions_required": ["Nộp giấy đồng ý"]},
            },
            "metadata": {"title": "동의서 안내"},
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
        self.assertNotIn("status", notice_updates[-1])
        self.assertNotIn("summary_translations", notice_updates[-1])
        self.assertNotIn("child_id", str(supabase.operations))
        self.assertEqual(saved["schedules"], [])

        card_updates = [
            op[2]
            for op in supabase.operations
            if op[0] == "notice_cards" and op[1] == "update"
        ]
        self.assertIn("en", card_updates[-1]["content"])
        self.assertIn("vi", card_updates[-1]["content"])

    def test_same_language_retranslation_removes_stale_card_content(self):
        supabase = FakeSupabase()
        supabase.notice_cards = [
            {
                "id": "card-1",
                "type": "supplies",
                "order": 0,
                "content": {"vi": {"title": "Old supplies"}},
            },
        ]
        pipeline_result = {
            "status": "ready_to_save",
            "source_text": "동의서 제출",
            "final_translation": "Nộp giấy đồng ý",
            "source_hard_facts": {
                "hard_facts": {"actions_required": ["동의서 제출"]},
            },
            "target_hard_facts": {
                "hard_facts": {"actions_required": ["Nộp giấy đồng ý"]},
            },
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
        self.assertIn("card-1", deleted_card_ids)
        self.assertEqual(saved["cards"][0]["type"], "action")

    def test_same_language_retranslation_with_no_cards_clears_stale_content(self):
        supabase = FakeSupabase()
        supabase.notice_cards = [
            {
                "id": "card-1",
                "type": "supplies",
                "order": 0,
                "content": {"vi": {"title": "Old supplies"}},
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
        self.assertIn("card-1", deleted_card_ids)
        self.assertEqual(saved["cards"], [])


if __name__ == "__main__":
    unittest.main()
