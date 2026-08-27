from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from app.services.scheduled_crawler_service import (
    ScheduledSchoolResult,
    ScheduledSchoolTarget,
    _build_summary,
    _target_sort_key,
    should_crawl_school,
)


class ScheduledCrawlerTargetTests(unittest.TestCase):
    def test_null_checked_at_sorts_first(self) -> None:
        now = datetime(2026, 5, 17, tzinfo=UTC)
        never_checked = ScheduledSchoolTarget(
            school_id="new",
            school_name="new school",
            crawl_status="pending",
            crawl_last_checked_at=None,
        )
        old_checked = ScheduledSchoolTarget(
            school_id="old",
            school_name="old school",
            crawl_status="success",
            crawl_last_checked_at=now - timedelta(days=1),
        )

        ordered = sorted([old_checked, never_checked], key=_target_sort_key)

        self.assertEqual([item.school_id for item in ordered], ["new", "old"])

    def test_unsupported_recent_school_is_skipped(self) -> None:
        now = datetime(2026, 5, 17, tzinfo=UTC)
        target = ScheduledSchoolTarget(
            school_id="blocked",
            school_name="blocked school",
            crawl_status="unsupported_login_required",
            crawl_last_checked_at=now - timedelta(hours=12),
        )

        self.assertFalse(
            should_crawl_school(
                target,
                now=now,
                force=False,
                unsupported_recheck_hours=168,
            ),
        )

    def test_unsupported_old_school_is_selected(self) -> None:
        now = datetime(2026, 5, 17, tzinfo=UTC)
        target = ScheduledSchoolTarget(
            school_id="blocked",
            school_name="blocked school",
            crawl_status="unsupported_external_dynamic",
            crawl_last_checked_at=now - timedelta(days=8),
        )

        self.assertTrue(
            should_crawl_school(
                target,
                now=now,
                force=False,
                unsupported_recheck_hours=168,
            ),
        )

    def test_force_ignores_unsupported_cooldown(self) -> None:
        now = datetime(2026, 5, 17, tzinfo=UTC)
        target = ScheduledSchoolTarget(
            school_id="blocked",
            school_name="blocked school",
            crawl_status="unsupported_forbidden",
            crawl_last_checked_at=now,
        )

        self.assertTrue(
            should_crawl_school(
                target,
                now=now,
                force=True,
                unsupported_recheck_hours=168,
            ),
        )


class BoardFallbackCountTest(unittest.TestCase):
    """게시판 오선택(announcement_fallback)이 성공률을 흐리지 않으면서 세어져야 한다."""

    def _result(self, name: str, board_kind: str) -> ScheduledSchoolResult:
        return ScheduledSchoolResult(
            school_id=f"id-{name}",
            school_name=name,
            status="success",
            success_count=3,
            error_message=None,
            board_kind=board_kind,
        )

    def test_fallback_is_counted_but_still_success(self) -> None:
        results = [
            self._result("문남초", "announcement_fallback"),
            self._result("가람초", "family_notice"),
        ]
        summary = _build_summary(
            started_at=datetime(2026, 8, 27, tzinfo=UTC),
            dry_run=False,
            force=False,
            total_registered=2,
            selected=[],
            skipped=[],
            results=results,
            fail_rate_threshold=0.5,
        )

        self.assertEqual(summary.fallback_count, 1)
        self.assertEqual(summary.success_count, 2)  # 성공률 정의는 바뀌지 않는다
        self.assertFalse(summary.alarm)
        self.assertEqual(summary.to_dict()["fallback_count"], 1)

    def test_zero_fallback_when_all_boards_are_correct(self) -> None:
        summary = _build_summary(
            started_at=datetime(2026, 8, 27, tzinfo=UTC),
            dry_run=False,
            force=False,
            total_registered=1,
            selected=[],
            skipped=[],
            results=[self._result("가람초", "family_notice")],
            fail_rate_threshold=0.5,
        )
        self.assertEqual(summary.fallback_count, 0)


if __name__ == "__main__":
    unittest.main()
