import asyncio
import json
import unittest
from unittest.mock import AsyncMock

from app.api.notices import (
    NoticeTranslateRequest,
    _BACKGROUND_TRANSLATION_TASKS,
    translate_notice,
)


class _FakeTask:
    def __init__(self, *, done: bool = False) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


class NoticeApiBackgroundTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        _BACKGROUND_TRANSLATION_TASKS.clear()

    async def test_translate_notice_background_returns_accepted_immediately(self):
        service = type("FakeService", (), {"translate_notice": AsyncMock()})()
        created_coroutines: list[object] = []

        def fake_create_task(coro):
            created_coroutines.append(coro)
            return _FakeTask(done=False)

        try:
            original_create_task = asyncio.create_task
            asyncio.create_task = fake_create_task  # type: ignore[assignment]
            response = await translate_notice(
                "notice-1",
                NoticeTranslateRequest(target_language="en", background=True),
                service,
            )
        finally:
            asyncio.create_task = original_create_task  # type: ignore[assignment]
            for coro in created_coroutines:
                coro.close()

        self.assertEqual(response.status_code, 202)
        body = json.loads(response.body)
        self.assertTrue(body["accepted"])
        self.assertFalse(body["already_running"])
        service.translate_notice.assert_not_awaited()

    async def test_translate_notice_background_dedupes_inflight_task(self):
        service = type("FakeService", (), {"translate_notice": AsyncMock()})()
        _BACKGROUND_TRANSLATION_TASKS["notice-1:en"] = _FakeTask(done=False)  # type: ignore[assignment]

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


if __name__ == "__main__":
    unittest.main()
