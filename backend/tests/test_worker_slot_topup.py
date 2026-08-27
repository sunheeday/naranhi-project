import asyncio
import unittest
from unittest.mock import patch

from app.jobs.translation_worker import process_jobs


class _SlowFastQueue:
    """느린 잡 1개 + 빠른 잡 1개를 준 뒤, 이후 claim 에는 추가 잡을 계속 내준다.

    배치 대기 구조라면 느린 잡이 끝날 때까지 두 번째 claim 이 오지 않는다.
    top-up 구조라면 빠른 잡이 끝난 직후 claim 이 한 번 더 온다.
    """

    def __init__(self) -> None:
        self.claims: list[int] = []
        self._served = 0

    def reclaim_stale_jobs(self, *, job_types, stale_seconds):  # noqa: ANN001, ANN201, ARG002
        return 0

    def claim(self, *, job_types, limit):  # noqa: ANN001, ARG002
        self.claims.append(limit)
        if self._served == 0:
            self._served = 2
            return [_job("slow"), _job("fast")]
        if self._served < 4:
            self._served += 1
            return [_job(f"extra-{self._served}")]
        return []

    def complete(self, job_id, *, result=None):  # noqa: ANN001, ARG002
        return None

    def fail(self, job, *, error, retry_delay_seconds):  # noqa: ANN001, ARG002
        raise AssertionError(f"fail should not be called: {error}")


def _job(job_id: str) -> dict[str, object]:
    return {"id": job_id, "payload": {"notice_id": job_id, "target_language": "en"}}


class SlotTopUpTest(unittest.IsolatedAsyncioTestCase):
    async def test_claims_again_before_slow_job_finishes(self) -> None:
        queue = _SlowFastQueue()
        slow_release = asyncio.Event()
        claims_when_slow_running: list[int] = []

        async def fake_run(job):  # noqa: ANN001
            if job["id"] == "slow":
                await slow_release.wait()
                return {}
            await asyncio.sleep(0)
            claims_when_slow_running.append(len(queue.claims))
            return {}

        with (
            patch("app.jobs.translation_worker.JobQueueService", return_value=queue),
            patch("app.jobs.translation_worker._run_job", side_effect=fake_run),
        ):
            task = asyncio.create_task(
                process_jobs(max_jobs=0, batch_size=2, retry_delay_seconds=120, stale_seconds=3600)
            )
            for _ in range(60):
                await asyncio.sleep(0)
                if len(queue.claims) >= 2:
                    break
            self.assertGreaterEqual(
                len(queue.claims), 2, "느린 잡이 끝나기 전에 두 번째 claim 이 와야 한다"
            )
            slow_release.set()
            processed = await asyncio.wait_for(task, timeout=2.0)

        self.assertEqual(processed, 4)


if __name__ == "__main__":
    unittest.main()
