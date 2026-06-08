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
    async def test_translation_worker_skips_ko_jobs_without_calling_translation(self) -> None:
        job = {"id": "job-1", "payload": {"notice_id": "n1", "target_language": "ko"}}
        with patch("app.jobs.translation_worker.NoticeService") as service_cls:
            from app.jobs.translation_worker import _run_job

            result = await _run_job(job)

        service_cls.assert_not_called()
        self.assertEqual(result["target_language"], "ko")
        self.assertTrue(result["saved"]["skipped"])

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

    async def test_crawler_worker_processes_claimed_jobs_concurrently(self) -> None:
        class _ConcurrentQueue:
            def __init__(self) -> None:
                self._first = True
                self.completed: list[str] = []

            def claim(self, *, job_types, limit):  # noqa: ANN001, ARG002
                if not self._first:
                    return []
                self._first = False
                return [
                    {"id": "job-1", "job_type": "school_notice_extraction", "payload": {"school_id": "s1"}},
                    {"id": "job-2", "job_type": "school_notice_extraction", "payload": {"school_id": "s2"}},
                ][:limit]

            def fail(self, job, *, error: str, retry_delay_seconds: int) -> None:  # noqa: ANN001, ARG002
                raise AssertionError(f"fail should not be called: {job} {error}")

            def complete(self, job_id: str, *, result=None) -> None:  # noqa: ARG002
                self.completed.append(job_id)

        queue = _ConcurrentQueue()
        both_started = asyncio.Event()
        release = asyncio.Event()
        started = 0
        max_running = 0
        running = 0

        async def fake_run(_job):  # noqa: ANN001
            nonlocal started, max_running, running
            started += 1
            running += 1
            max_running = max(max_running, running)
            if started >= 2:
                both_started.set()
            await both_started.wait()
            await release.wait()
            running -= 1
            return {}

        with (
            patch("app.jobs.crawler_worker.JobQueueService", return_value=queue),
            patch("app.jobs.crawler_worker._run_extraction_job", side_effect=fake_run),
        ):
            task = asyncio.create_task(process_crawler_jobs(max_jobs=2, batch_size=2, retry_delay_seconds=120))
            await asyncio.wait_for(both_started.wait(), timeout=1.0)
            release.set()
            processed = await asyncio.wait_for(task, timeout=1.0)

        self.assertEqual(processed, 2)
        self.assertEqual(max_running, 2)
        self.assertEqual(sorted(queue.completed), ["job-1", "job-2"])


if __name__ == "__main__":
    unittest.main()
