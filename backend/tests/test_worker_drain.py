import unittest
from unittest.mock import AsyncMock, patch

from app.jobs.crawler_worker import process_jobs as process_crawler_jobs
from app.jobs.translation_worker import process_jobs as process_translation_jobs


class _DrainQueue:
    """claim()이 미리 준 배치들을 순서대로 내보내고, 소진되면 빈 리스트를 준다."""

    def __init__(self, claim_batches):
        self._batches = [list(b) for b in claim_batches]
        self.completed: list[str] = []
        self.reclaim_calls = 0

    def reclaim_stale_jobs(self, *, job_types, stale_seconds):  # noqa: ANN001, ANN201, ARG002
        self.reclaim_calls += 1
        return 0

    def claim(self, *, job_types, limit):  # noqa: ANN001, ARG002
        if self._batches:
            return self._batches.pop(0)
        return []

    def complete(self, job_id, *, result=None):  # noqa: ANN001, ARG002
        self.completed.append(str(job_id))

    def fail(self, job, *, error, retry_delay_seconds):  # noqa: ANN001, ARG002
        raise AssertionError(f"fail should not be called: {error}")


def _tjob(job_id, notice="n"):
    return {"id": job_id, "payload": {"notice_id": notice, "target_language": "en"}}


class TranslationDrainTest(unittest.IsolatedAsyncioTestCase):
    async def test_drains_until_empty_across_rounds(self) -> None:
        # max_jobs=0 → 상한 없이 큐가 빌 때까지. 여러 claim 라운드 전부 처리.
        queue = _DrainQueue([[_tjob("j1")], [_tjob("j2")], [_tjob("j3")]])
        with (
            patch("app.jobs.translation_worker.JobQueueService", return_value=queue),
            patch("app.jobs.translation_worker._run_job", new=AsyncMock(return_value={})),
        ):
            processed = await process_translation_jobs(
                max_jobs=0, batch_size=3, retry_delay_seconds=120, stale_seconds=3600
            )
        self.assertEqual(processed, 3)
        self.assertEqual(queue.completed, ["j1", "j2", "j3"])
        self.assertEqual(queue.reclaim_calls, 1)

    async def test_idle_grace_repoll_catches_late_job(self) -> None:
        # 첫 빈 claim 뒤 grace 재폴링이 막 들어온 잡을 잡는다.
        queue = _DrainQueue([[_tjob("j1")], [], [_tjob("j2")]])
        with (
            patch("app.jobs.translation_worker.JobQueueService", return_value=queue),
            patch("app.jobs.translation_worker._run_job", new=AsyncMock(return_value={})),
        ):
            processed = await process_translation_jobs(
                max_jobs=0,
                batch_size=3,
                retry_delay_seconds=120,
                stale_seconds=3600,
                idle_grace_seconds=0.01,
            )
        self.assertEqual(queue.completed, ["j1", "j2"])
        self.assertEqual(processed, 2)

    async def test_no_grace_stops_at_first_empty(self) -> None:
        # idle_grace_seconds=0이면 첫 빈 claim에서 즉시 종료(늦게 온 j2 안 잡음).
        queue = _DrainQueue([[_tjob("j1")], [], [_tjob("j2")]])
        with (
            patch("app.jobs.translation_worker.JobQueueService", return_value=queue),
            patch("app.jobs.translation_worker._run_job", new=AsyncMock(return_value={})),
        ):
            processed = await process_translation_jobs(
                max_jobs=0, batch_size=3, retry_delay_seconds=120, stale_seconds=3600, idle_grace_seconds=0
            )
        self.assertEqual(queue.completed, ["j1"])
        self.assertEqual(processed, 1)


class CrawlerDrainTest(unittest.IsolatedAsyncioTestCase):
    async def test_drains_until_empty(self) -> None:
        queue = _DrainQueue(
            [
                [{"id": "c1", "job_type": "school_notice_extraction", "payload": {"school_id": "s1"}}],
                [{"id": "c2", "job_type": "school_notice_extraction", "payload": {"school_id": "s2"}}],
            ]
        )
        with (
            patch("app.jobs.crawler_worker.JobQueueService", return_value=queue),
            patch("app.jobs.crawler_worker._run_extraction_job", new=AsyncMock(return_value={})),
        ):
            processed = await process_crawler_jobs(
                max_jobs=0, batch_size=3, retry_delay_seconds=120, stale_seconds=3600
            )
        self.assertEqual(processed, 2)
        self.assertEqual(sorted(queue.completed), ["c1", "c2"])


if __name__ == "__main__":
    unittest.main()
