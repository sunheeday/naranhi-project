import unittest
from unittest.mock import patch

import httpx

from app.crawler.notice_post_extractor import _rss_post_id

MISSING_COLUMN_ERROR = Exception(
    "column school_crawl_state.rss_feed does not exist (42703)"
)


class RssPostIdTest(unittest.TestCase):
    def test_select_ntt_uses_same_keys_and_source_as_html(self):
        """notice_post_extractor:306 과 같은 키·같은 순서, :315 와 같은 post_id_source."""
        link = "https://school.gyo6.net/gacheon/na/ntt/selectNttInfo.do?mi=119615&bbsId=39051&nttSn=777"
        self.assertEqual(_rss_post_id(link, "select_ntt_like"), ("777", "href query"))

    def test_select_ntt_falls_back_to_nttid_then_articleid(self):
        self.assertEqual(
            _rss_post_id("https://x.kr/a/na/ntt/selectNttInfo.do?nttId=88", "select_ntt_like"),
            ("88", "href query"),
        )
        self.assertEqual(
            _rss_post_id("https://x.kr/a/na/ntt/selectNttInfo.do?articleId=99", "select_ntt_like"),
            ("99", "href query"),
        )

    def test_slash_view_uses_same_regex_and_source_as_html(self):
        """notice_post_extractor:417,430 과 같은 정규식·같은 post_id_source."""
        self.assertEqual(
            _rss_post_id("https://school.jbedu.kr/kacheon/M010401/view/6882610", "slash_view_like"),
            ("6882610", "path /view/"),
        )

    def test_unknown_family_yields_nothing(self):
        self.assertEqual(_rss_post_id("https://x.kr/a", "boardcnts_like"), ("", ""))
        self.assertEqual(_rss_post_id("https://x.kr/a/na/ntt/selectNttInfo.do", "select_ntt_like"), ("", ""))

    def test_post_id_sources_are_watermark_eligible(self):
        """'rss' 같은 새 값을 만들면 워터마크 제외목록에는 안 걸리지만 HTML 경로와
        값이 달라져 crawl_result 진단이 갈라진다."""
        from app.services.school_crawler_service import (
            _WATERMARK_EXCLUDED_METHODS,
            _WATERMARK_EXCLUDED_SOURCES,
        )

        for source in ("href query", "path /view/"):
            self.assertNotIn(source, _WATERMARK_EXCLUDED_SOURCES)
        self.assertNotIn("href", _WATERMARK_EXCLUDED_METHODS)

    def test_default_https_port_does_not_survive_httpx_url_normalization(self):
        """🔴 jbedu 실측 링크는 :443 이 붙는다(school.jbedu.kr:443/...).

        _validate_candidate 의 detail_url 은 RSS 링크 문자열 자체가 아니라
        httpx.Response.url(요청이 실제로 나간 URL)이다. httpx.URL 은 생성 시점에
        기본 포트(https:443, http:80)를 정규화해 없앤다 - 그래서 HTML 경로가 만드는
        무포트 URL 과 RSS 경로가 만드는 URL 이 detail_url 단계에서 갈라지지 않는다.
        이 테스트는 그 정규화가 실제로 일어난다는 것 자체를 못박아 회귀를 막는다.
        """
        url_with_port = httpx.URL("https://school.jbedu.kr:443/kacheon/M010401/view/6882610")
        self.assertEqual(str(url_with_port), "https://school.jbedu.kr/kacheon/M010401/view/6882610")
        self.assertIsNone(url_with_port.port)


class RssFeedForSchoolColumnMissingTest(unittest.TestCase):
    """🔴 0040_school_crawl_state_rss_feed.sql 이 운영에 미적용인 상태(이번 Task 에서
    운영 PostgREST 를 직접 조회해 42703 을 실측 확인함)를 흉내낸다.

    `_rss_feed_for_school` 은 `_fetch_school_row`의 select 를 건드리지 않고
    별도의 `_read_rss_feed`(자체 try/except 보유)만 거치므로, 컬럼이 없어도
    예외 없이 None 을 돌려줘야 한다 - 그래야 크롤이 `internal_error` 로
    전면 중단되지 않는다."""

    def test_returns_none_without_raising_when_column_missing(self):
        with patch(
            "app.services.school_crawler_service.get_supabase_client",
            side_effect=MISSING_COLUMN_ERROR,
        ):
            from app.services.school_crawler_service import _rss_feed_for_school

            self.assertIsNone(_rss_feed_for_school("school-1"))  # 예외가 새면 이 테스트가 실패한다


if __name__ == "__main__":
    unittest.main()
