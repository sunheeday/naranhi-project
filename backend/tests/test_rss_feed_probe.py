import unittest
from datetime import UTC, datetime, timedelta

from app.crawler.rss_feed import (
    FLAVOR_GYO6_RSS2,
    FLAVOR_JBEDU_JSON,
    derive_feed_url,
    should_probe,
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


if __name__ == "__main__":
    unittest.main()
