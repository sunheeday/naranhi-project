from __future__ import annotations

from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from app.utils.korean_date_parser import parse_korean_deadline


KST = ZoneInfo("Asia/Seoul")


class KoreanDateParserTests(unittest.TestCase):
    def test_explicit_korean_date(self) -> None:
        parsed = parse_korean_deadline("2024년 3월 15일까지", reference=datetime(2026, 5, 18, tzinfo=KST))

        self.assertEqual(parsed, datetime(2024, 3, 15, tzinfo=KST))

    def test_explicit_dash_date(self) -> None:
        parsed = parse_korean_deadline("2024-03-15", reference=datetime(2026, 5, 18, tzinfo=KST))

        self.assertEqual(parsed, datetime(2024, 3, 15, tzinfo=KST))

    def test_month_day_next_occurrence_same_year(self) -> None:
        parsed = parse_korean_deadline("5월 20일까지", reference=datetime(2026, 5, 18, tzinfo=KST))

        self.assertEqual(parsed, datetime(2026, 5, 20, tzinfo=KST))

    def test_month_day_next_occurrence_next_year(self) -> None:
        parsed = parse_korean_deadline("3월 15일까지", reference=datetime(2026, 5, 18, tzinfo=KST))

        self.assertEqual(parsed, datetime(2027, 3, 15, tzinfo=KST))

    def test_slash_and_dot_month_day(self) -> None:
        reference = datetime(2026, 1, 1, tzinfo=KST)

        self.assertEqual(parse_korean_deadline("3/15", reference=reference), datetime(2026, 3, 15, tzinfo=KST))
        self.assertEqual(parse_korean_deadline("3.15", reference=reference), datetime(2026, 3, 15, tzinfo=KST))

    def test_time_with_pm(self) -> None:
        parsed = parse_korean_deadline("3월 15일 오후 3시까지", reference=datetime(2026, 1, 1, tzinfo=KST))

        self.assertEqual(parsed, datetime(2026, 3, 15, 15, 0, tzinfo=KST))

    def test_date_range_uses_later_date(self) -> None:
        parsed = parse_korean_deadline("3월 15일 ~ 3월 20일", reference=datetime(2026, 1, 1, tzinfo=KST))

        self.assertEqual(parsed, datetime(2026, 3, 20, tzinfo=KST))

    def test_relative_days(self) -> None:
        reference = datetime(2026, 5, 18, 10, 0, tzinfo=KST)

        self.assertEqual(parse_korean_deadline("오늘까지", reference=reference), datetime(2026, 5, 18, tzinfo=KST))
        self.assertEqual(parse_korean_deadline("내일까지", reference=reference), datetime(2026, 5, 19, tzinfo=KST))
        self.assertEqual(parse_korean_deadline("모레까지", reference=reference), datetime(2026, 5, 20, tzinfo=KST))

    def test_weekday_phrases(self) -> None:
        reference = datetime(2026, 5, 18, tzinfo=KST)  # Monday

        self.assertEqual(parse_korean_deadline("이번 주 금요일까지", reference=reference), datetime(2026, 5, 22, tzinfo=KST))
        self.assertEqual(parse_korean_deadline("다음 주 금요일까지", reference=reference), datetime(2026, 5, 29, tzinfo=KST))

    def test_unparseable_contextual_dates_return_none(self) -> None:
        self.assertIsNone(parse_korean_deadline("학기말까지"))
        self.assertIsNone(parse_korean_deadline("추후 안내"))


if __name__ == "__main__":
    unittest.main()
