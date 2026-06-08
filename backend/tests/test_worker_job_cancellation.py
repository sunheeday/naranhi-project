import asyncio
import unittest
from unittest.mock import patch

from app.jobs.crawler_worker import process_jobs as process_crawler_jobs
from app.jobs.translation_worker import process_jobs as process_translation_jobs


class _FakeQueue:
    def __init__(self, jobs):
        self.jobs = jobs
        self.failed: list[tuple[dict[str, object], str, int]] = []

    def claim(self, *, job_types, limit):  # noqa: ANN001
        return self.jobs[:limit]

    def fail(self, job, *, error: str, retry_delay_seconds: int) -> None:  # noqa: ANN001
        self.failed.append((job, error, retry_delay_seconds))

    def complete(self, job_id: str, *, result=None) -> None:  # noqa: ARG002
        raise AssertionError("complete should not be called on cancellation")


class WorkerCancellationTest(unittest.IsolatedAsyncioTestCase):
    async def test_translation_worker_marks_job_failed_on_cancellation(self) -> None:
        queue = _FakeQueue([{"id": "job-1", "payload": {"notice_id": "n1", "target_language": "en"}}])
        with (
            patch("app.jobs.translation_worker.JobQueueService", return_value=queue),
            patch("app.jobs.translation_worker._run_job", side_effect=asyncio.CancelledError()),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await process_translation_jobs(max_jobs=1, batch_size=1, retry_delay_seconds=120)

        self.assertEqual(len(queue.failed), 1)
        self.assertEqual(queue.failed[0][0]["id"], "job-1")

    async def test_crawler_worker_marks_job_failed_on_cancellation(self) -> None:
        queue = _FakeQueue([{"id": "job-2", "job_type": "school_notice_extraction", "payload": {"school_id": "s1"}}])
        with (
            patch("app.jobs.crawler_worker.JobQueueService", return_value=queue),
            patch("app.jobs.crawler_worker._run_extraction_job", side_effect=asyncio.CancelledError()),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await process_crawler_jobs(max_jobs=1, batch_size=1, retry_delay_seconds=120)

        self.assertEqual(len(queue.failed), 1)
        self.assertEqual(queue.failed[0][0]["id"], "job-2")


if __name__ == "__main__":
    unittest.main()
