import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

import app.api.admin as admin_api
import app.services.gcp_admin_service as gcp


def _settings(**over):
    base = dict(
        admin_api_token="secret-token",
        environment="local",
        gcp_project_id="proj",
        gcp_region="asia-northeast3",
        scheduler_location="asia-northeast3",
    )
    base.update(over)
    return type("S", (), base)()


class RequireAdminTokenTest(unittest.TestCase):
    def test_missing_token_is_503_even_in_local(self):
        """crawler.py:24-26 은 토큰 미설정 + local 이면 통과시킨다.
        스케줄러 정지에는 그 fail-open 이 허용될 수 없다."""
        with patch.object(admin_api, "get_settings", return_value=_settings(admin_api_token=None)):
            with self.assertRaises(HTTPException) as ctx:
                admin_api._require_admin_token(x_admin_token="anything")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_absent_header_is_401(self):
        with patch.object(admin_api, "get_settings", return_value=_settings()):
            with self.assertRaises(HTTPException) as ctx:
                admin_api._require_admin_token(x_admin_token=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_is_401(self):
        with patch.object(admin_api, "get_settings", return_value=_settings()):
            with self.assertRaises(HTTPException) as ctx:
                admin_api._require_admin_token(x_admin_token="wrong")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_matching_token_passes(self):
        with patch.object(admin_api, "get_settings", return_value=_settings()):
            self.assertIsNone(admin_api._require_admin_token(x_admin_token="secret-token"))


class RunJobWithArgsTest(unittest.TestCase):
    def test_overrides_are_filled(self):
        """worker_trigger.py:87-108 은 리터럴 json={} 이라 args 를 못 넘긴다.
        그래서 공지 1건 재추출이 수동 gcloud 밖에 방법이 없었다."""
        response = MagicMock(status_code=200)
        response.json.return_value = {"name": "operations/abc"}
        with (
            patch.object(gcp, "get_settings", return_value=_settings()),
            patch.object(gcp, "_authed_headers", return_value={"Authorization": "Bearer x"}),
            patch.object(gcp.httpx, "post", return_value=response) as post,
        ):
            result = gcp.run_job_with_args(
                "naranhi-content-extractor",
                ["--notice-id=n-1", "--force", "--max-notices=1"],
            )
        body = post.call_args.kwargs["json"]
        self.assertEqual(
            body["overrides"]["containerOverrides"][0]["args"],
            ["--notice-id=n-1", "--force", "--max-notices=1"],
        )
        self.assertEqual(result.operation, "operations/abc")

    def test_unlisted_job_is_refused(self):
        with patch.object(gcp, "get_settings", return_value=_settings()):
            with self.assertRaises(PermissionError):
                gcp.run_job_with_args("some-other-job", [])

    def test_failure_propagates_instead_of_returning_false(self):
        """trigger_worker_for_job_type 은 모든 실패를 삼키고 False 를 돌려준다.
        관리자에게는 사유가 그대로 보여야 한다."""
        response = MagicMock(status_code=403, text="permission denied")
        with (
            patch.object(gcp, "get_settings", return_value=_settings()),
            patch.object(gcp, "_authed_headers", return_value={}),
            patch.object(gcp.httpx, "post", return_value=response),
        ):
            with self.assertRaises(RuntimeError):
                gcp.run_job_with_args("naranhi-content-extractor", [])


class SchedulerWhitelistTest(unittest.TestCase):
    def test_unlisted_scheduler_is_refused(self):
        with patch.object(gcp, "get_settings", return_value=_settings()):
            with self.assertRaises(PermissionError):
                gcp.pause_scheduler("someone-elses-job")

    def test_listed_scheduler_calls_pause_endpoint(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"state": "PAUSED", "schedule": "0 6 * * *"}
        name = sorted(gcp.CONTROLLABLE_SCHEDULERS)[0]
        with (
            patch.object(gcp, "get_settings", return_value=_settings()),
            patch.object(gcp, "_authed_headers", return_value={}),
            patch.object(gcp.httpx, "post", return_value=response) as post,
        ):
            result = gcp.pause_scheduler(name)
        self.assertIn(f"jobs/{name}:pause", post.call_args.args[0])
        self.assertEqual(result["state"], "PAUSED")

    def test_actual_operations_names_are_whitelisted(self):
        """gcloud scheduler jobs list --location=asia-northeast3 (읽기 전용,
        2026-08-29)로 확인한 실운영 이름. 브리프 초안은 school-crawler를 "-1800",
        content-extractor를 "-1900"으로 잘못 짐작했었다 — 실제는 "-1900"/"-2000"."""
        self.assertEqual(
            gcp.CONTROLLABLE_SCHEDULERS,
            frozenset(
                {
                    "naranhi-school-crawler-0600",
                    "naranhi-school-crawler-1900",
                    "naranhi-content-extractor-0700",
                    "naranhi-content-extractor-2000",
                }
            ),
        )

    def test_actual_job_names_are_whitelisted(self):
        """gcloud run jobs list --region=asia-northeast3 (읽기 전용)로 확인 — 브리프의
        추정과 실제 이름이 이미 일치했다(수정 불필요)."""
        self.assertEqual(
            gcp.RUNNABLE_JOBS,
            frozenset({"naranhi-content-extractor", "naranhi-school-crawler"}),
        )


class ParseAdminActorTest(unittest.TestCase):
    def test_valid_uuid_is_kept(self):
        actor = "8f14e45f-ceea-467e-bd47-2f79b5b0a0c1"
        self.assertEqual(gcp.parse_admin_actor(actor), actor)

    def test_missing_header_is_none(self):
        self.assertIsNone(gcp.parse_admin_actor(None))

    def test_garbage_header_is_dropped_not_stored(self):
        """신뢰되지 않는 자유서식 문자열을 admin_user_id(uuid 컬럼)에 넣지 않는다."""
        self.assertIsNone(gcp.parse_admin_actor("'; drop table admin_users; --"))


class RecordAdminActionTest(unittest.TestCase):
    def test_insert_failure_does_not_raise(self):
        """Task 8 패턴: 0038/admin_audit_log 가 없거나 insert 가 실패해도
        방금 수행한 GCP 조작 응답을 막지 않는다."""
        with patch("app.core.supabase.get_supabase_client", side_effect=RuntimeError("no table")):
            gcp.record_admin_action(
                admin_user_id=None, action="scheduler_pause", target="x", detail={}
            )  # 예외가 밖으로 안 나오면 통과

    def test_insert_success_uses_admin_audit_log_table(self):
        table = MagicMock()
        client = MagicMock()
        client.table.return_value = table
        with patch("app.core.supabase.get_supabase_client", return_value=client):
            gcp.record_admin_action(
                admin_user_id="8f14e45f-ceea-467e-bd47-2f79b5b0a0c1",
                action="job_run",
                target="naranhi-content-extractor",
                detail={"operation": "operations/abc"},
            )
        client.table.assert_called_once_with("admin_audit_log")
        row = table.insert.call_args.args[0]
        self.assertEqual(row["action"], "job_run")
        self.assertEqual(row["target"], "naranhi-content-extractor")
        self.assertEqual(row["admin_user_id"], "8f14e45f-ceea-467e-bd47-2f79b5b0a0c1")


class AdminRouterAuditWiringTest(unittest.TestCase):
    """POST 핸들러가 성공 시 record_admin_action 을 부르는지, GET 은 절대 안 부르는지."""

    def test_get_schedulers_never_records_audit(self):
        with (
            patch.object(admin_api, "list_schedulers", return_value=[]),
            patch.object(admin_api, "record_admin_action") as record,
        ):
            import asyncio

            asyncio.run(admin_api.get_schedulers())
        record.assert_not_called()

    def test_pause_records_audit_with_actor(self):
        import asyncio

        with (
            patch.object(admin_api, "pause_scheduler", return_value={"name": "x", "state": "PAUSED"}),
            patch.object(admin_api, "record_admin_action") as record,
        ):
            asyncio.run(
                admin_api.post_scheduler_pause(
                    "naranhi-school-crawler-0600",
                    x_admin_actor="8f14e45f-ceea-467e-bd47-2f79b5b0a0c1",
                )
            )
        record.assert_called_once()
        self.assertEqual(record.call_args.kwargs["action"], "scheduler_pause")
        self.assertEqual(record.call_args.kwargs["target"], "naranhi-school-crawler-0600")
        self.assertEqual(
            record.call_args.kwargs["admin_user_id"], "8f14e45f-ceea-467e-bd47-2f79b5b0a0c1"
        )

    def test_pause_failure_never_reaches_audit_call(self):
        """PermissionError/RuntimeError 는 _wrap 에서 HTTPException 으로 바뀌어 던져진다
        — record_admin_action 줄에 도달하지 못한다(성공한 조작만 기록한다)."""
        import asyncio

        with (
            patch.object(
                admin_api, "pause_scheduler", side_effect=PermissionError("not allowed")
            ),
            patch.object(admin_api, "record_admin_action") as record,
        ):
            with self.assertRaises(HTTPException):
                asyncio.run(admin_api.post_scheduler_pause("someone-elses-job", x_admin_actor=None))
        record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
