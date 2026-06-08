import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from app.worker_main import _normalize_job_groups, _run_worker_group


class WorkerMainTest(unittest.IsolatedAsyncioTestCase):
    def test_normalize_job_groups_dedupes_and_defaults(self) -> None:
        self.assertEqual(_normalize_job_groups([" translation ", "crawler", "translation"]), ["translation", "crawler"])
        self.assertEqual(_normalize_job_groups(["", "  "]), ["translation"])

    def test_normalize_job_groups_rejects_unknown_values(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_job_groups(["translatoin"])

    async def test_run_worker_group_dispatches_translation(self) -> None:
        settings = type(
            "Settings",
            (),
            {"worker_batch_size": 4, "worker_retry_delay_seconds": 90, "worker_job_groups": ["translation"]},
        )()
        with (
            patch("app.worker_main.get_settings", return_value=settings),
            patch("app.worker_main.process_translation_jobs", new=AsyncMock(return_value=2)) as process_mock,
        ):
            processed = await _run_worker_group("translation")

        self.assertEqual(processed, 2)
        process_mock.assert_awaited_once_with(
            max_jobs=4,
            batch_size=4,
            retry_delay_seconds=90,
        )

    async def test_run_worker_group_dispatches_crawler(self) -> None:
        settings = type(
            "Settings",
            (),
            {"worker_batch_size": 5, "worker_retry_delay_seconds": 75, "worker_job_groups": ["crawler"]},
        )()
        with (
            patch("app.worker_main.get_settings", return_value=settings),
            patch("app.worker_main.process_crawler_jobs", new=AsyncMock(return_value=3)) as process_mock,
        ):
            processed = await _run_worker_group("crawler")

        self.assertEqual(processed, 3)
        process_mock.assert_awaited_once_with(
            max_jobs=5,
            batch_size=5,
            retry_delay_seconds=75,
        )


if __name__ == "__main__":
    unittest.main()
