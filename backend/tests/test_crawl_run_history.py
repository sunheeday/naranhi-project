import unittest
from unittest.mock import MagicMock, patch

from app.services import crawl_run_history_service as service


class OutcomeTest(unittest.TestCase):
    def test_zero_processed_is_idle_not_ok(self):
        """processed_count == 0 이면 scheduled_crawler_service.py:340-341 이
        success_rate 를 1.0, alarm 을 False 로 만든다. 그대로 쌓으면 화면이
        «아무것도 안 돌았음» 을 «성공» 으로 보여준다."""
        summary = {"processed_count": 0, "success_rate": 1.0, "alarm": False}
        self.assertEqual(service.outcome_for(summary), "idle")

    def test_alarm_beats_ok(self):
        summary = {"processed_count": 5, "success_rate": 0.2, "alarm": True}
        self.assertEqual(service.outcome_for(summary), "alarm")

    def test_normal_run_is_ok(self):
        summary = {"processed_count": 5, "success_rate": 1.0, "alarm": False}
        self.assertEqual(service.outcome_for(summary), "ok")


class RecordCrawlRunTest(unittest.TestCase):
    def test_inserts_all_summary_keys(self):
        client = MagicMock()
        summary = {
            "started_at": "2026-08-27T00:00:00+00:00",
            "finished_at": "2026-08-27T00:05:00+00:00",
            "dry_run": False,
            "force": False,
            "total_registered": 8,
            "selected_count": 6,
            "skipped_count": 2,
            "processed_count": 6,
            "success_count": 5,
            "failure_count": 1,
            "fallback_count": 1,
            "success_rate": 0.8333,
            "alarm": False,
            "targets": [{"school_id": "s-1"}],
            "results": [{"school_id": "s-1", "status": "success"}],
        }
        with patch.object(service, "get_supabase_client", return_value=client):
            self.assertTrue(service.record_crawl_run(summary, outcome="ok"))
        row = client.table.return_value.insert.call_args.args[0]
        self.assertEqual(row["outcome"], "ok")
        self.assertEqual(row["processed_count"], 6)
        self.assertEqual(row["success_count"], 5)
        self.assertEqual(row["fallback_count"], 1)
        self.assertEqual(row["targets"], [{"school_id": "s-1"}])
        self.assertIsNone(row["error_message"])

    def test_missing_fallback_count_defaults_to_zero(self):
        """구형 summary dict(fallback_count 없음)도 KeyError 없이 적재돼야 한다."""
        client = MagicMock()
        summary = {"processed_count": 0}
        with patch.object(service, "get_supabase_client", return_value=client):
            self.assertTrue(service.record_crawl_run(summary, outcome="idle"))
        row = client.table.return_value.insert.call_args.args[0]
        self.assertEqual(row["fallback_count"], 0)

    def test_insert_failure_does_not_raise(self):
        """이력 적재 실패가 크롤 결과를 바꾸면 안 된다."""
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = RuntimeError("boom")
        with patch.object(service, "get_supabase_client", return_value=client):
            self.assertFalse(service.record_crawl_run({"processed_count": 0}, outcome="idle"))

    def test_insert_failure_does_not_raise_when_client_unavailable(self):
        """0041 이 운영에 없으면 get_supabase_client() 호출 이후 첫 쿼리에서 테이블
        없음 예외가 나는 것과 별개로, get_supabase_client() 자체가 예외를 던지는
        경로(설정 누락 등)도 크롤을 죽이면 안 된다."""
        with patch.object(service, "get_supabase_client", side_effect=RuntimeError("no client")):
            self.assertFalse(service.record_crawl_run({"processed_count": 0}, outcome="idle"))


if __name__ == "__main__":
    unittest.main()
