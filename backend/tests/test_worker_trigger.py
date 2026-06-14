import asyncio
import unittest
from unittest.mock import MagicMock, patch

import app.services.worker_trigger as wt


def _settings(**over):
    base = dict(
        worker_trigger_enabled=True,
        worker_trigger_debounce_seconds=0.0,
        gcp_project_id="proj",
        gcp_region="reg",
        translation_worker_job_name="tjob",
        crawler_worker_job_name="cjob",
    )
    base.update(over)
    return type("S", (), base)()


class WorkerTriggerTest(unittest.TestCase):
    def setUp(self) -> None:
        wt._last_triggered_monotonic.clear()

    def test_disabled_does_nothing(self) -> None:
        with (
            patch.object(wt, "get_settings", return_value=_settings(worker_trigger_enabled=False)),
            patch.object(wt, "_post_run_job") as post,
        ):
            self.assertFalse(wt.trigger_worker_for_job_type("notice_translation"))
        post.assert_not_called()

    def test_unknown_job_type_does_nothing(self) -> None:
        with (
            patch.object(wt, "get_settings", return_value=_settings()),
            patch.object(wt, "_post_run_job") as post,
        ):
            self.assertFalse(wt.trigger_worker_for_job_type("something_else"))
        post.assert_not_called()

    def test_translation_maps_to_translation_job(self) -> None:
        with (
            patch.object(wt, "get_settings", return_value=_settings()),
            patch.object(wt, "_post_run_job") as post,
        ):
            self.assertTrue(wt.trigger_worker_for_job_type("notice_translation"))
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "tjob")

    def test_crawler_types_map_to_crawler_job(self) -> None:
        with (
            patch.object(wt, "get_settings", return_value=_settings()),
            patch.object(wt, "_post_run_job") as post,
        ):
            wt.trigger_worker_for_job_type("school_board_discovery")
            wt.trigger_worker_for_job_type("school_notice_extraction")
        self.assertEqual([c.args[0] for c in post.call_args_list], ["cjob", "cjob"])

    def test_missing_project_skips(self) -> None:
        with (
            patch.object(wt, "get_settings", return_value=_settings(gcp_project_id="")),
            patch.object(wt, "_post_run_job") as post,
        ):
            self.assertFalse(wt.trigger_worker_for_job_type("notice_translation"))
        post.assert_not_called()

    def test_debounce_skips_second_within_window(self) -> None:
        with (
            patch.object(wt, "get_settings", return_value=_settings(worker_trigger_debounce_seconds=100.0)),
            patch.object(wt, "_post_run_job") as post,
        ):
            self.assertTrue(wt.trigger_worker_for_job_type("notice_translation"))
            self.assertFalse(wt.trigger_worker_for_job_type("notice_translation"))
        post.assert_called_once()

    def test_best_effort_swallows_errors(self) -> None:
        with (
            patch.object(wt, "get_settings", return_value=_settings()),
            patch.object(wt, "_post_run_job", side_effect=RuntimeError("403 forbidden")),
        ):
            self.assertFalse(wt.trigger_worker_for_job_type("notice_translation"))  # 예외 없이 False

    def test_post_run_job_builds_expected_url(self) -> None:
        creds = MagicMock()
        creds.token = "tok"
        resp = MagicMock()
        resp.status_code = 200
        with (
            patch("google.auth.default", return_value=(creds, "proj")),
            patch("google.auth.transport.requests.Request"),
            patch("httpx.post", return_value=resp) as post,
        ):
            wt._post_run_job("tjob", _settings())
        url = post.call_args.args[0]
        self.assertIn("projects/proj/locations/reg/jobs/tjob:run", url)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer tok")


class ScheduleWorkerTriggerTest(unittest.IsolatedAsyncioTestCase):
    """API가 실제로 쓰는 fire-and-forget 진입점."""

    def setUp(self) -> None:
        wt._pending_tasks.clear()
        wt._last_triggered_monotonic.clear()

    async def test_disabled_creates_no_task(self) -> None:
        called: list[str] = []
        with (
            patch.object(wt, "get_settings", return_value=_settings(worker_trigger_enabled=False)),
            patch.object(wt, "trigger_worker_for_job_type", side_effect=lambda jt: called.append(jt)),
        ):
            wt.schedule_worker_trigger("notice_translation")
            await asyncio.sleep(0.02)
        self.assertEqual(called, [])
        self.assertEqual(len(wt._pending_tasks), 0)

    async def test_enabled_runs_trigger_off_the_event_loop(self) -> None:
        called: list[str] = []
        with (
            patch.object(wt, "get_settings", return_value=_settings(worker_trigger_enabled=True)),
            patch.object(wt, "trigger_worker_for_job_type", side_effect=lambda jt: called.append(jt)),
        ):
            wt.schedule_worker_trigger("notice_translation")
            for _ in range(100):  # to_thread 완료 + done-callback 정리 대기
                if called and not wt._pending_tasks:
                    break
                await asyncio.sleep(0.01)
        self.assertEqual(called, ["notice_translation"])
        self.assertEqual(len(wt._pending_tasks), 0)  # GC 보호용 참조가 done 후 정리됨


if __name__ == "__main__":
    unittest.main()
