import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api.crawler import discover_school_board, extract_pending_school_notices


class CrawlerApiQueueTest(unittest.IsolatedAsyncioTestCase):
    async def test_discover_school_board_enqueues_job(self):
        enqueue = type("FakeEnqueue", (), {"accepted": True, "already_running": False, "job_id": "job-discovery"})()
        settings = type("Settings", (), {"supabase_configured": True, "crawler_initial_notice_count": 5})()
        with (
            patch("app.api.crawler.get_settings", return_value=settings),
            patch("app.api.crawler._fetch_school_row", return_value={"id": "school-1"}),
            patch("app.api.crawler.JobQueueService.enqueue", return_value=enqueue) as enqueue_mock,
        ):
            response = await discover_school_board("school-1")

        self.assertEqual(response.status_code, 202)
        body = json.loads(response.body)
        self.assertTrue(body["accepted"])
        self.assertFalse(body["already_running"])
        self.assertEqual(body["job_id"], "job-discovery")

        enqueue_mock.assert_called_once()
        kwargs = enqueue_mock.call_args.kwargs
        self.assertEqual(kwargs["job_type"], "school_board_discovery")
        self.assertEqual(kwargs["job_key"], "school-discovery:school-1")
        self.assertEqual(kwargs["payload"]["school_id"], "school-1")

    async def test_extract_pending_school_notices_enqueues_job(self):
        enqueue = type("FakeEnqueue", (), {"accepted": True, "already_running": True, "job_id": "job-extraction"})()
        settings = type(
            "Settings",
            (),
            {"supabase_configured": True, "crawler_initial_notice_count": 5, "extractor_max_notices_per_run": 5},
        )()
        with (
            patch("app.api.crawler.get_settings", return_value=settings),
            patch("app.api.crawler._fetch_school_row", return_value={"id": "school-2"}),
            patch("app.api.crawler.JobQueueService.enqueue", return_value=enqueue) as enqueue_mock,
        ):
            response = await extract_pending_school_notices("school-2", max_notices=7)

        self.assertEqual(response.status_code, 202)
        body = json.loads(response.body)
        self.assertTrue(body["accepted"])
        self.assertTrue(body["already_running"])
        self.assertEqual(body["job_id"], "job-extraction")
        self.assertEqual(body["extraction"]["max_notices"], 7)

        enqueue_mock.assert_called_once()
        kwargs = enqueue_mock.call_args.kwargs
        self.assertEqual(kwargs["job_type"], "school_notice_extraction")
        self.assertEqual(kwargs["job_key"], "school-extraction:school-2")
        self.assertEqual(kwargs["payload"], {"school_id": "school-2", "max_notices": 7})

    async def test_discover_school_board_raises_404_for_missing_school(self):
        settings = type("Settings", (), {"supabase_configured": True, "crawler_initial_notice_count": 5})()
        with (
            patch("app.api.crawler.get_settings", return_value=settings),
            patch("app.api.crawler._fetch_school_row", return_value=None),
        ):
            with self.assertRaises(HTTPException) as error:
                await discover_school_board("missing-school")

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "School row was not found.")

    async def test_discover_school_board_raises_503_when_supabase_not_configured(self):
        settings = type("Settings", (), {"supabase_configured": False, "crawler_initial_notice_count": 5})()
        with patch("app.api.crawler.get_settings", return_value=settings):
            with self.assertRaises(HTTPException) as error:
                await discover_school_board("school-3")

        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.detail, "Supabase is not configured.")

    async def test_extract_pending_school_notices_raises_404_for_missing_school(self):
        settings = type(
            "Settings",
            (),
            {"supabase_configured": True, "crawler_initial_notice_count": 5, "extractor_max_notices_per_run": 5},
        )()
        with (
            patch("app.api.crawler.get_settings", return_value=settings),
            patch("app.api.crawler._fetch_school_row", return_value=None),
        ):
            with self.assertRaises(HTTPException) as error:
                await extract_pending_school_notices("missing-school")

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "School row was not found.")

    async def test_extract_pending_school_notices_raises_503_when_supabase_not_configured(self):
        settings = type(
            "Settings",
            (),
            {"supabase_configured": False, "crawler_initial_notice_count": 5, "extractor_max_notices_per_run": 5},
        )()
        with patch("app.api.crawler.get_settings", return_value=settings):
            with self.assertRaises(HTTPException) as error:
                await extract_pending_school_notices("school-4")

        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.detail, "Supabase is not configured.")


if __name__ == "__main__":
    unittest.main()
