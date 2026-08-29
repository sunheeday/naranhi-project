import unittest
from datetime import date

from app.services.school_schedule_sync_service import (
    NEIS_SOURCE,
    academic_year_range,
    build_neis_event_rows,
)
from app.crawler.neis_client import SchoolScheduleEntry


class AcademicYearRangeTest(unittest.TestCase):
    def test_march_starts_new_academic_year(self):
        self.assertEqual(academic_year_range(date(2026, 3, 1)), (2026, "20260301", "20270228"))

    def test_january_belongs_to_previous_academic_year(self):
        self.assertEqual(academic_year_range(date(2026, 1, 15)), (2025, "20250301", "20260228"))

    def test_leap_february_end(self):
        # 2027-08 → 학년도 2027, 끝은 2028-02-29 (윤년)
        self.assertEqual(academic_year_range(date(2027, 8, 27)), (2027, "20270301", "20280229"))


class BuildRowsTest(unittest.TestCase):
    def test_rows_carry_source_and_null_notice(self):
        entries = [SchoolScheduleEntry(event_date="2026-03-02", title="개학일", description="전교생 등교")]
        rows = build_neis_event_rows("s-1", entries)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source"], NEIS_SOURCE)
        self.assertIsNone(row["notice_id"])
        self.assertIsNone(row["end_date"])
        self.assertEqual(row["event_kinds"], ["event"])
        self.assertEqual(row["school_id"], "s-1")
        self.assertEqual(row["event_date"], "2026-03-02")

    def test_empty_entries_produce_no_rows(self):
        self.assertEqual(build_neis_event_rows("s-1", []), [])


if __name__ == "__main__":
    unittest.main()
