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


if __name__ == "__main__":
    unittest.main()
