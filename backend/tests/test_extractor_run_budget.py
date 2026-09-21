"""런 예산 캡(EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN)의 두 가지 의미를 고정한다.

0 = 상한 없음(_cap_reached 가 항상 False), 그리고 그 값일 때만 공지 동시성이
강제 직렬화(batch_size=1)에서 풀린다. 이 두 성질이 같은 env 한 줄에 묶여 있다는
사실이 배포값의 근거이므로 테스트로 못 박는다.
"""
import unittest

from app.services.content_extraction_service import _cap_reached


class RunGeminiCallCapTest(unittest.TestCase):
    def test_zero_cap_disables_the_limit(self) -> None:
        self.assertFalse(_cap_reached(0, 0))
        self.assertFalse(_cap_reached(10_000, 0))

    def test_positive_cap_still_stops_at_the_limit(self) -> None:
        self.assertFalse(_cap_reached(79, 80))
        self.assertTrue(_cap_reached(80, 80))
        self.assertTrue(_cap_reached(81, 80))

    def test_batch_size_is_serialized_only_when_cap_is_positive(self) -> None:
        """content_extraction_service.py:107-109 / :185-187 의 분기와 같은 식."""
        for cap, expected in ((80, 1), (1, 1), (0, 3)):
            with self.subTest(cap=cap):
                batch_size = min(3, 30)
                if cap > 0:
                    batch_size = 1
                self.assertEqual(batch_size, expected)


class DeployedExtractorJobEnvTest(unittest.TestCase):
    """배포 워크플로에 실제로 값이 박혀 있는지 본다. 코드 기본값에 의존하지 않는다.

    '기본값이 마침 맞다' 와 '배포가 그 값을 보장한다' 는 다른 얘기다.
    이 Job 들은 env 를 --set-env-vars 로 통째로 덮으므로 빠진 값은 코드 기본값이 된다.
    """

    def _workflow_text(self) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return (root / ".github" / "workflows" / "deploy-api-cloud-run.yml").read_text(
            encoding="utf-8"
        )

    def test_extractor_job_disables_run_gemini_call_cap(self) -> None:
        self.assertIn("EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0", self._workflow_text())

    def test_extractor_job_pins_gemini_concurrency(self) -> None:
        text = self._workflow_text()
        self.assertEqual(text.count("GEMINI_MAX_CONCURRENCY=32"), 2)  # 번역 워커 + 추출 Job

    def test_crawler_worker_job_pins_batch_size(self) -> None:
        # --플래그=값 형태다. gcloud 가 --args 목록에 같은 값이 두 번 나오면 거부하고,
        # 여기는 --idle-grace-seconds 3 과 --batch-size 3 의 "3" 이 겹쳤다.
        self.assertIn(
            "app.jobs.crawler_worker,--max-jobs=0,--idle-grace-seconds=3,--batch-size=3",
            self._workflow_text(),
        )

    def test_extractor_job_has_two_gigs(self) -> None:
        text = self._workflow_text()
        extractor_block = text.split("Deploy scheduled content extractor Job")[1]
        self.assertIn("app.jobs.scheduled_content_extractor,--max-notices,30", extractor_block)
        self.assertIn("--memory=2Gi", extractor_block)


if __name__ == "__main__":
    unittest.main()
