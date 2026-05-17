from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from app.services.scheduled_crawler_service import (
    ScheduledSchoolTarget,
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


if __name__ == "__main__":
    unittest.main()
