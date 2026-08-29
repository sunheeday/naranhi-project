import unittest

from app.crawler.neis_client import SchoolScheduleEntry, _schedule_entry_from_row


class ScheduleRowMappingTest(unittest.TestCase):
    def test_maps_ymd_and_event_name(self):
        row = {"AA_YMD": "20260302", "EVENT_NM": "1학기 개학일", "EVENT_CNTNT": "전교생 등교"}
        self.assertEqual(
            _schedule_entry_from_row(row),
            SchoolScheduleEntry(event_date="2026-03-02", title="1학기 개학일", description="전교생 등교"),
        )

    def test_blank_content_becomes_none(self):
        row = {"AA_YMD": "20260715", "EVENT_NM": "여름방학", "EVENT_CNTNT": "   "}
        entry = _schedule_entry_from_row(row)
        assert entry is not None
        self.assertIsNone(entry.description)

    def test_rejects_bad_date_or_missing_title(self):
        self.assertIsNone(_schedule_entry_from_row({"AA_YMD": "2026-03-02", "EVENT_NM": "개학"}))
        self.assertIsNone(_schedule_entry_from_row({"AA_YMD": "20260302", "EVENT_NM": "  "}))
        self.assertIsNone(_schedule_entry_from_row({}))


if __name__ == "__main__":
    unittest.main()
