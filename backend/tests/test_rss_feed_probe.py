import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.crawler.rss_feed import (
    FLAVOR_GYO6_RSS2,
    FLAVOR_JBEDU_JSON,
    RssItem,
    derive_feed_url,
    probe_rss_feed,
    should_probe,
    titles_intersect,
)


class DeriveFeedUrlTest(unittest.TestCase):
    def test_select_ntt_builds_rss_feed_path(self):
        derived = derive_feed_url(
            board_url="https://school.gyo6.net/gacheon/na/ntt/selectNttList.do?mi=119615&bbsId=39051",
            parser_family="select_ntt_like",
            board_key="mi=119615|bbsId=39051",
        )
        self.assertEqual(
            derived,
            ("https://school.gyo6.net/gacheon/na/ntt/selectRssFeed.do?mi=119615&bbsId=39051", FLAVOR_GYO6_RSS2),
        )

    def test_jbedu_rule_is_host_pinned(self):
        """slash_view_like 는 울산·충북에서도 잡힌다. 호스트 검사 없이 적용하면
        매 크롤마다 404 를 한 번씩 때린다."""
        self.assertEqual(
            derive_feed_url(
                board_url="https://school.jbedu.kr/kacheon/M010401/index.do",
                parser_family="slash_view_like",
                board_key="/kacheon/M010401/",
            ),
            ("https://school.jbedu.kr/rss/kacheon/M010401.do", FLAVOR_JBEDU_JSON),
        )
        self.assertIsNone(
            derive_feed_url(
                board_url="https://school.use.go.kr/abc/M010401/index.do",
                parser_family="slash_view_like",
                board_key="/abc/M010401/",
            )
        )
        self.assertIsNone(
            derive_feed_url(
                board_url="https://school.cbe.go.kr/abc/M010401/index.do",
                parser_family="slash_view_like",
                board_key="/abc/M010401/",
            )
        )

    def test_other_families_have_no_rule(self):
        for family in ("boardcnts_like", "sen_like", "xboard_like", "generic", "gen_c2z_home_like"):
            self.assertIsNone(
                derive_feed_url(board_url="https://x.kr/list.do", parser_family=family, board_key="k")
            )

    def test_select_ntt_needs_both_params(self):
        self.assertIsNone(
            derive_feed_url(
                board_url="https://school.gyo6.net/gacheon/na/ntt/selectNttList.do?mi=1",
                parser_family="select_ntt_like",
                board_key="mi=1|bbsId=None",
            )
        )


class ShouldProbeTest(unittest.TestCase):
    NOW = datetime(2026, 8, 27, tzinfo=UTC)

    def test_empty_state_probes(self):
        self.assertTrue(should_probe({}, board_key="k", now=self.NOW))
        self.assertTrue(should_probe(None, board_key="k", now=self.NOW))

    def test_ok_does_not_reprobe(self):
        state = {"status": "ok", "board_key": "k", "checked_at": self.NOW.isoformat()}
        self.assertFalse(should_probe(state, board_key="k", now=self.NOW))

    def test_board_key_change_invalidates_ok(self):
        state = {"status": "ok", "board_key": "old", "checked_at": self.NOW.isoformat()}
        self.assertTrue(should_probe(state, board_key="new", now=self.NOW))

    def test_unsupported_is_locked_for_30_days(self):
        recent = {"status": "unsupported", "board_key": "k",
                  "checked_at": (self.NOW - timedelta(days=29)).isoformat()}
        stale = {"status": "unsupported", "board_key": "k",
                 "checked_at": (self.NOW - timedelta(days=31)).isoformat()}
        self.assertFalse(should_probe(recent, board_key="k", now=self.NOW))
        self.assertTrue(should_probe(stale, board_key="k", now=self.NOW))

    def test_unknown_reprobes_next_crawl(self):
        state = {"status": "unknown", "board_key": "k", "checked_at": self.NOW.isoformat()}
        self.assertTrue(should_probe(state, board_key="k", now=self.NOW))


class TitlesIntersectTest(unittest.TestCase):
    def test_matches_by_substring_ignoring_noise(self):
        self.assertTrue(
            titles_intersect(
                ["2026학년도 2학기 가정통신문"],
                ["[가정통신문] 2026학년도 2학기 가정통신문 NEW 첨부"],
            )
        )

    def test_no_match_returns_false(self):
        self.assertFalse(titles_intersect(["급식 식단표"], ["운동회 안내"]))


class ProbeRssFeedTest(unittest.IsolatedAsyncioTestCase):
    """probe_rss_feed 의 4단 게이트. parse_feed 는 Task 11 전까지 항상
    NotImplementedError 를 던지므로(게이트 2), 게이트 3/4 는 parse_feed 를
    몽키패치해서 검증한다 — 실제 학교 서버 응답 형태를 흉내낸 값을 넣는다.
    """

    BOARD_URL = "https://school.gyo6.net/gacheon/na/ntt/selectNttList.do?mi=119615&bbsId=39051"
    BOARD_KEY = "mi=119615|bbsId=39051"

    async def test_no_feed_rule_is_unsupported(self):
        state = await probe_rss_feed(
            board_url="https://x.kr/list.do",
            parser_family="generic",
            board_key="k",
            sample_titles=[],
            timeout=1.0,
        )
        self.assertEqual(state.status, "unsupported")
        self.assertEqual(state.error, "no_feed_rule")

    async def test_gate1_non_200_is_unsupported(self):
        """경북 외 select_ntt_like 호스트가 맞는 404 — 게이트 1이 잠근다."""
        with patch("app.crawler.rss_feed.fetch_feed", return_value=(404, b"")):
            state = await probe_rss_feed(
                board_url=self.BOARD_URL,
                parser_family="select_ntt_like",
                board_key=self.BOARD_KEY,
                sample_titles=[],
                timeout=1.0,
            )
        self.assertEqual(state.status, "unsupported")
        self.assertEqual(state.error, "http_404")

    async def test_gate1_fetch_exception_is_unknown(self):
        with patch("app.crawler.rss_feed.fetch_feed", side_effect=TimeoutError("boom")):
            state = await probe_rss_feed(
                board_url=self.BOARD_URL,
                parser_family="select_ntt_like",
                board_key=self.BOARD_KEY,
                sample_titles=[],
                timeout=1.0,
            )
        self.assertEqual(state.status, "unknown")
        self.assertEqual(state.error, "fetch_TimeoutError")

    async def test_gate2_parse_not_implemented_yet_is_unsupported_not_ok(self):
        """gyo6 실측 응답(200, 357바이트)을 흉내낸다. parse_feed 가 아직 Task 11
        미구현 상태(NotImplementedError)이므로 게이트 2에서 걸려야 한다 —
        어떤 경우에도 이 상태에서 'ok'가 나오면 안 된다."""
        tiny_gyo6_body = b'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"></rss>'
        self.assertEqual(len(tiny_gyo6_body), 63)  # 실측 357B와 자릿수만 다른 대표값
        with patch("app.crawler.rss_feed.fetch_feed", return_value=(200, tiny_gyo6_body)):
            state = await probe_rss_feed(
                board_url=self.BOARD_URL,
                parser_family="select_ntt_like",
                board_key=self.BOARD_KEY,
                sample_titles=["가정통신문"],
                timeout=1.0,
            )
        self.assertNotEqual(state.status, "ok")
        self.assertEqual(state.status, "unsupported")
        self.assertEqual(state.error, "parse_failed")
        self.assertEqual(state.item_count, 0)

    async def test_gate3_zero_items_is_unknown_not_ok(self):
        """item==0 은 unknown 이다 — 방학 중 빈 게시판과 죽은 엔드포인트를
        구분할 수 없다는 스펙 제약(§4.3 게이트 3)."""
        with patch("app.crawler.rss_feed.fetch_feed", return_value=(200, b"...")), patch(
            "app.crawler.rss_feed.parse_feed", return_value=[]
        ):
            state = await probe_rss_feed(
                board_url=self.BOARD_URL,
                parser_family="select_ntt_like",
                board_key=self.BOARD_KEY,
                sample_titles=["가정통신문"],
                timeout=1.0,
            )
        self.assertEqual(state.status, "unknown")
        self.assertEqual(state.error, "empty_feed")

    async def test_gate4_title_mismatch_is_unknown(self):
        """mi/bbsId 가 다른 게시판(급식·앨범)을 가리키는 경우를 시뮬레이션."""
        items = [RssItem(title="2026 급식 식단표", link="https://school.gyo6.net/meal/1")]
        with patch("app.crawler.rss_feed.fetch_feed", return_value=(200, b"...")), patch(
            "app.crawler.rss_feed.parse_feed", return_value=items
        ):
            state = await probe_rss_feed(
                board_url=self.BOARD_URL,
                parser_family="select_ntt_like",
                board_key=self.BOARD_KEY,
                sample_titles=["가정통신문 배부 안내"],
                timeout=1.0,
            )
        self.assertEqual(state.status, "unknown")
        self.assertEqual(state.error, "title_mismatch")

    async def test_all_gates_pass_is_ok(self):
        items = [RssItem(title="[가정통신문] 2학기 방과후 안내", link="https://school.gyo6.net/n/1")]
        with patch("app.crawler.rss_feed.fetch_feed", return_value=(200, b"...")), patch(
            "app.crawler.rss_feed.parse_feed", return_value=items
        ):
            state = await probe_rss_feed(
                board_url=self.BOARD_URL,
                parser_family="select_ntt_like",
                board_key=self.BOARD_KEY,
                sample_titles=["2학기 방과후 안내"],
                timeout=1.0,
            )
        self.assertEqual(state.status, "ok")
        self.assertEqual(state.item_count, 1)
        self.assertIsNone(state.error)


if __name__ == "__main__":
    unittest.main()
