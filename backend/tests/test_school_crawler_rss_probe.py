import unittest
from unittest.mock import patch

from app.crawler.rss_feed import RssFeedState
from app.services.school_crawler_service import (
    DiscoveredPostPreview,
    SchoolBoardDiscoveryResult,
    _probe_and_save_rss_feed,
    _read_rss_feed,
    _write_rss_feed,
)

MISSING_COLUMN_ERROR = Exception(
    "column school_crawl_state.rss_feed does not exist (42703)"
)


def _post(post_id="1", *, board_key="mi=1|bbsId=2", status="success"):
    return DiscoveredPostPreview(
        title=f"title-{post_id}",
        post_id=post_id,
        post_uid=f"cms:{board_key}:{post_id}",
        board_key=board_key,
        detail_url=f"https://x/{post_id}",
        status=status,
        method="href",
        source="href query",
        cms_key="cms",
        parser_family="select_ntt_like",
        reason="",
    )


def _result(**overrides):
    base = dict(
        school_id="school-1",
        school_name="테스트초",
        office_code="J10",
        school_code="1234",
        homepage_url="https://school.gyo6.net",
        status="ok",
        board_url="https://school.gyo6.net/gacheon/na/ntt/selectNttList.do?mi=1&bbsId=2",
        board_kind="notice",
        fallback_used=False,
        cms_key="gyo6",
        cms_name="gyo6",
        cms_confidence=0.9,
        cms_signals=[],
        verified=True,
        board_verified=True,
        posts_extracted=True,
        verification_score=90,
        verification_title="t",
        verification_error=None,
        parser_family="select_ntt_like",
        total_candidates=1,
        success_count=1,
        sample_posts=[_post()],
        error_code=None,
        error_message=None,
    )
    base.update(overrides)
    return SchoolBoardDiscoveryResult(**base)


class RssFeedColumnMissingTest(unittest.TestCase):
    """0040_school_crawl_state_rss_feed.sql 이 운영에 미적용인 상황을 흉내낸다.
    컬럼이 없으면 select/update 가 예외를 던진다 — read/write 헬퍼가 그 예외를
    삼키고 크롤 결과에 영향을 주지 않는지 확인한다."""

    def test_read_returns_empty_dict_when_column_missing(self):
        with patch(
            "app.services.school_crawler_service.get_supabase_client",
            side_effect=MISSING_COLUMN_ERROR,
        ):
            self.assertEqual(_read_rss_feed("school-1"), {})

    def test_write_does_not_raise_when_column_missing(self):
        with patch(
            "app.services.school_crawler_service.get_supabase_client",
            side_effect=MISSING_COLUMN_ERROR,
        ):
            _write_rss_feed("school-1", {"status": "ok"})  # 예외가 새면 이 테스트가 실패한다


class ProbeAndSaveRssFeedTest(unittest.IsolatedAsyncioTestCase):
    async def test_survives_missing_column_without_raising(self):
        """읽기·쓰기 모두 컬럼 부재로 실패해도 프로브 전체가 예외를 던지지 않는다
        — 크롤 파이프라인(discover_and_save_school_board)이 죽지 않는다는 근거."""
        result = _result()
        with patch(
            "app.services.school_crawler_service.get_supabase_client",
            side_effect=MISSING_COLUMN_ERROR,
        ), patch(
            "app.services.school_crawler_service.probe_rss_feed",
            return_value=RssFeedState(
                status="ok",
                flavor="gyo6_rss2",
                url="https://school.gyo6.net/.../selectRssFeed.do?mi=1&bbsId=2",
                board_key="mi=1|bbsId=2",
                item_count=3,
                checked_at="2026-08-29T00:00:00+00:00",
                error=None,
            ),
        ):
            await _probe_and_save_rss_feed(result)  # 예외가 새면 이 테스트가 실패한다

    async def test_skips_when_flag_disabled(self):
        result = _result()
        with patch(
            "app.services.school_crawler_service.get_settings"
        ) as mock_settings, patch(
            "app.services.school_crawler_service.probe_rss_feed"
        ) as mock_probe:
            mock_settings.return_value.crawler_rss_probe_enabled = False
            await _probe_and_save_rss_feed(result)
            mock_probe.assert_not_called()

    async def test_skips_when_no_board_url(self):
        result = _result(board_url=None)
        with patch("app.services.school_crawler_service.probe_rss_feed") as mock_probe:
            await _probe_and_save_rss_feed(result)
            mock_probe.assert_not_called()

    async def test_skips_when_no_valid_posts(self):
        result = _result(sample_posts=[_post(status="access_denied")])
        with patch("app.services.school_crawler_service.probe_rss_feed") as mock_probe:
            await _probe_and_save_rss_feed(result)
            mock_probe.assert_not_called()

    async def test_probe_exception_does_not_propagate(self):
        """probe_rss_feed 자체가 터져도(가령 예상 못한 파싱 예외) 크롤에 영향을 주지 않는다."""
        result = _result()
        with patch(
            "app.services.school_crawler_service.probe_rss_feed",
            side_effect=RuntimeError("boom"),
        ):
            await _probe_and_save_rss_feed(result)  # 예외가 새면 이 테스트가 실패한다


if __name__ == "__main__":
    unittest.main()
