import asyncio
import json
import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from app.api.notices import (
    NoticeTranslateRequest,
    translate_notice,
)


class NoticeApiBackgroundTest(unittest.IsolatedAsyncioTestCase):
    async def test_translate_notice_foreground_schedules_followup_without_waiting(self):
        service = type("FakeService", (), {"translate_notice": AsyncMock(return_value={"ok": True})})()
        created_coroutines: list[object] = []

        def fake_create_task(coro):
            created_coroutines.append(coro)
            return type("FakeTask", (), {})()

        with (
            patch("app.api.notices.asyncio.create_task", side_effect=fake_create_task) as create_task_mock,
            patch("app.api.notices._translate_sources_for_locale_background", new_callable=AsyncMock) as followup_mock,
        ):
            result = await translate_notice(
                "notice-1",
                NoticeTranslateRequest(target_language="en", background=False),
                service,
            )

        self.assertEqual(result, {"ok": True})
        service.translate_notice.assert_awaited_once()
        create_task_mock.assert_called_once()
        followup_mock.assert_not_awaited()
        self.assertEqual(len(created_coroutines), 1)
        for coro in created_coroutines:
            if asyncio.iscoroutine(coro):
                coro.close()

    async def test_translate_notice_background_returns_accepted_immediately(self):
        service = type("FakeService", (), {"translate_notice": AsyncMock()})()
        enqueue = type("FakeEnqueue", (), {"accepted": True, "already_running": False, "job_id": "job-1"})()
        with (
            patch("app.api.notices.JobQueueService.completed_recently", return_value=False),
            patch("app.api.notices.JobQueueService.enqueue", return_value=enqueue),
        ):
            response = await translate_notice(
                "notice-1",
                NoticeTranslateRequest(target_language="en", background=True),
                service,
            )

        self.assertEqual(response.status_code, 202)
        body = json.loads(response.body)
        self.assertTrue(body["accepted"])
        self.assertFalse(body["already_running"])
        self.assertEqual(body["job_id"], "job-1")
        service.translate_notice.assert_not_awaited()

    async def test_translate_notice_background_dedupes_inflight_task(self):
        service = type("FakeService", (), {"translate_notice": AsyncMock()})()
        enqueue = type("FakeEnqueue", (), {"accepted": True, "already_running": True, "job_id": "job-1"})()
        with (
            patch("app.api.notices.JobQueueService.completed_recently", return_value=False),
            patch("app.api.notices.JobQueueService.enqueue", return_value=enqueue),
        ):
            response = await translate_notice(
                "notice-1",
                NoticeTranslateRequest(target_language="en", background=True),
                service,
            )

        self.assertEqual(response.status_code, 202)
        body = json.loads(response.body)
        self.assertTrue(body["accepted"])
        self.assertTrue(body["already_running"])
        service.translate_notice.assert_not_awaited()

    async def test_translate_notice_background_blocked_by_cooldown(self):
        service = type("FakeService", (), {"translate_notice": AsyncMock()})()
        with (
            patch("app.api.notices.JobQueueService.completed_recently", return_value=True),
            patch("app.api.notices.JobQueueService.enqueue") as enqueue_mock,
        ):
            response = await translate_notice(
                "notice-1",
                NoticeTranslateRequest(target_language="en", background=True),
                service,
            )

        self.assertEqual(response.status_code, 202)
        body = json.loads(response.body)
        self.assertFalse(body["accepted"])
        self.assertTrue(body["cooldown"])
        enqueue_mock.assert_not_called()
        service.translate_notice.assert_not_awaited()

    async def test_translate_notice_background_explicit_source_text_bypasses_cooldown(self):
        service = type("FakeService", (), {"translate_notice": AsyncMock()})()
        enqueue = type("FakeEnqueue", (), {"accepted": True, "already_running": False, "job_id": "job-2"})()
        with (
            patch("app.api.notices.JobQueueService.completed_recently", return_value=True) as recent_mock,
            patch("app.api.notices.JobQueueService.enqueue", return_value=enqueue),
        ):
            response = await translate_notice(
                "notice-1",
                NoticeTranslateRequest(target_language="en", background=True, source_text="원문"),
                service,
            )

        self.assertEqual(response.status_code, 202)
        body = json.loads(response.body)
        self.assertTrue(body["accepted"])
        recent_mock.assert_not_called()

    async def test_translate_notice_background_ko_does_not_enqueue(self):
        service = type("FakeService", (), {"translate_notice": AsyncMock(return_value={"ok": True, "target_language": "ko"})})()
        with patch("app.api.notices.JobQueueService.enqueue") as enqueue_mock:
            response = await translate_notice(
                "notice-1",
                NoticeTranslateRequest(target_language="ko", background=True),
                service,
            )

        self.assertEqual(response, {"ok": True, "target_language": "ko"})
        service.translate_notice.assert_awaited_once()
        enqueue_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
