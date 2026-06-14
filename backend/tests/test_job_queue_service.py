import unittest
from unittest.mock import patch

import httpx

from app.services.job_queue_service import JobQueueService


class _FakeQuery:
    def __init__(self, *, data=None, error=None):
        self._data = data or []
        self._error = error

    def select(self, *_args, **_kwargs):
        return self

    def insert(self, *_args, **_kwargs):
        return self

    def update(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def lte(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._error is not None:
            raise self._error
        return type("Result", (), {"data": self._data})()


class _FakeClient:
    def __init__(self, query):
        self._query = query

    def table(self, _name):
        return self._query


class JobQueueServiceRetryTest(unittest.TestCase):
    def test_complete_retries_after_transient_write_error(self) -> None:
        service = JobQueueService()
        clients = [
            _FakeClient(_FakeQuery(error=httpx.WriteError("broken pipe"))),
            _FakeClient(_FakeQuery(data=[])),
        ]

        with (
            patch("app.services.job_queue_service.get_supabase_client", side_effect=clients),
            patch("app.services.job_queue_service.reset_supabase_client") as reset_mock,
        ):
            service.complete("job-1", result={"ok": True})

        reset_mock.assert_called_once()

    def test_fail_retries_after_transient_write_error(self) -> None:
        service = JobQueueService()
        clients = [
            _FakeClient(_FakeQuery(error=httpx.WriteError("broken pipe"))),
            _FakeClient(_FakeQuery(data=[])),
        ]
        job = {"id": "job-2", "attempts": 1, "max_attempts": 3}

        with (
            patch("app.services.job_queue_service.get_supabase_client", side_effect=clients),
            patch("app.services.job_queue_service.reset_supabase_client") as reset_mock,
        ):
            service.fail(job, error="boom", retry_delay_seconds=120)

        reset_mock.assert_called_once()


class JobQueueLatestJobTest(unittest.TestCase):
    def test_returns_latest_row(self) -> None:
        service = JobQueueService()
        client = _FakeClient(_FakeQuery(data=[{"id": "job-9", "status": "failed", "attempts": 5}]))

        with patch("app.services.job_queue_service.get_supabase_client", return_value=client):
            job = service.latest_job(job_key="notice-1:en")

        self.assertEqual(job["status"], "failed")

    def test_returns_none_when_no_job(self) -> None:
        service = JobQueueService()
        client = _FakeClient(_FakeQuery(data=[]))

        with patch("app.services.job_queue_service.get_supabase_client", return_value=client):
            self.assertIsNone(service.latest_job(job_key="notice-1:en"))


class JobQueueCompletedRecentlyTest(unittest.TestCase):
    def test_true_when_recent_completed_job_exists(self) -> None:
        service = JobQueueService()
        client = _FakeClient(_FakeQuery(data=[{"id": "job-1"}]))

        with patch("app.services.job_queue_service.get_supabase_client", return_value=client):
            result = service.completed_recently(job_key="notice-1:en", within_seconds=600)

        self.assertTrue(result)

    def test_false_when_no_recent_completed_job(self) -> None:
        service = JobQueueService()
        client = _FakeClient(_FakeQuery(data=[]))

        with patch("app.services.job_queue_service.get_supabase_client", return_value=client):
            result = service.completed_recently(job_key="notice-1:en", within_seconds=600)

        self.assertFalse(result)


class _ReclaimQuery:
    def __init__(self, select_rows, updates, update_data):
        self._select_rows = select_rows
        self._updates = updates
        self._update_data = update_data
        self._is_update = False
        self._payload = None

    def select(self, *_args, **_kwargs):
        self._is_update = False
        return self

    def update(self, payload, *_args, **_kwargs):
        self._is_update = True
        self._payload = payload
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def lt(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._is_update:
            self._updates.append(self._payload)
            return type("Result", (), {"data": list(self._update_data)})()
        return type("Result", (), {"data": self._select_rows})()


class _ReclaimClient:
    def __init__(self, select_rows, updates, update_data):
        self._select_rows = select_rows
        self._updates = updates
        self._update_data = update_data

    def table(self, _name):
        return _ReclaimQuery(self._select_rows, self._updates, self._update_data)


class JobQueueReclaimStaleTest(unittest.TestCase):
    def _run(self, select_rows, *, update_data=({"id": "updated"},)):
        updates: list[dict] = []
        client = _ReclaimClient(select_rows, updates, update_data)
        with patch("app.services.job_queue_service.get_supabase_client", return_value=client):
            reclaimed = JobQueueService().reclaim_stale_jobs(
                job_types=["notice_translation"], stale_seconds=3600
            )
        return reclaimed, updates

    def test_resets_stale_job_to_queued_when_attempts_remain(self) -> None:
        reclaimed, updates = self._run([{"id": "j1", "attempts": 1, "max_attempts": 5}])

        self.assertEqual(reclaimed, 1)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["status"], "queued")
        self.assertIn("available_at", updates[0])
        self.assertNotIn("finished_at", updates[0])
        self.assertIn("last_error", updates[0])

    def test_marks_failed_when_attempts_exhausted(self) -> None:
        reclaimed, updates = self._run([{"id": "j2", "attempts": 5, "max_attempts": 5}])

        self.assertEqual(reclaimed, 1)
        self.assertEqual(updates[0]["status"], "failed")
        self.assertIn("finished_at", updates[0])
        self.assertNotIn("available_at", updates[0])

    def test_returns_zero_when_no_stale_jobs(self) -> None:
        reclaimed, updates = self._run([])

        self.assertEqual(reclaimed, 0)
        self.assertEqual(updates, [])

    def test_does_not_count_when_conditional_update_matches_no_row(self) -> None:
        # 회수 시도와 업데이트 사이 원본 워커가 complete/fail시키면 status!='processing'이라
        # 조건부 업데이트(.eq status=processing)가 0행을 반환한다 → 회수 카운트에 넣지 않아야 한다.
        reclaimed, updates = self._run(
            [{"id": "j3", "attempts": 1, "max_attempts": 5}],
            update_data=(),
        )

        self.assertEqual(len(updates), 1)  # 업데이트는 시도됨
        self.assertEqual(reclaimed, 0)  # 그러나 0행 매칭이므로 회수로 세지 않음


if __name__ == "__main__":
    unittest.main()
