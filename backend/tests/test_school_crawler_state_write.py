import unittest
from types import SimpleNamespace

from app.services import school_crawler_service


class SchoolBackfillPayloadTest(unittest.TestCase):
    """schools 에 남기는 백필은 homepage_url 하나뿐이어야 한다.

    크롤 상태의 정본은 school_crawl_state 다(0013). schools 의 crawl_* 6컬럼은
    다음 단계에서 삭제되므로, 그 전에 쓰기가 끊겨 있어야 한다.
    homepage_url 만은 schools 에만 있고 크롤 대상 URL 의 유일한 소스라 남긴다.
    """

    def test_only_homepage_url_is_written_back(self):
        payload = school_crawler_service._school_backfill_payload(
            SimpleNamespace(homepage_url="https://school.example.kr")
        )
        self.assertEqual(payload, {"homepage_url": "https://school.example.kr"})

    def test_no_crawl_columns_in_payload(self):
        payload = school_crawler_service._school_backfill_payload(
            SimpleNamespace(homepage_url="https://school.example.kr")
        )
        for key in (
            "crawl_status",
            "crawl_error_message",
            "crawl_result",
            "crawl_board_url",
            "crawl_board_kind",
            "crawl_last_checked_at",
        ):
            self.assertNotIn(key, payload)

    def test_empty_payload_when_homepage_missing(self):
        """빈 dict 로 update 를 치면 PostgREST 가 400 을 낸다. 호출 자체를 건너뛴다."""
        self.assertEqual(
            school_crawler_service._school_backfill_payload(SimpleNamespace(homepage_url=None)),
            {},
        )

    def test_school_row_select_excludes_crawl_columns(self):
        """select('*') 는 죽은 컬럼까지 긁어와 우연한 폴백을 만든다. 명시 목록으로 좁힌다."""
        cols = school_crawler_service._SCHOOL_ROW_COLUMNS
        self.assertNotIn("crawl_", cols)
        for expected in ("id", "name", "homepage_url", "neis_office_code", "neis_school_code"):
            self.assertIn(expected, cols)


if __name__ == "__main__":
    unittest.main()
