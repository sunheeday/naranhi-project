import unittest

from app.crawler.rss_feed import (
    FLAVOR_GYO6_RSS2,
    FLAVOR_JBEDU_JSON,
    normalize_rss_link,
    parse_feed,
)

FEED_URL = "https://school.gyo6.net/gacheon/na/ntt/selectRssFeed.do?mi=119615&bbsId=39051"


class NormalizeRssLinkTest(unittest.TestCase):
    def test_adds_scheme_and_drops_duplicated_leading_segment(self):
        raw = "school.gyo6.net/gacheon/gacheon/na/ntt/selectNttInfo.do?nttSn=123&mi=119615"
        self.assertEqual(
            normalize_rss_link(raw, FEED_URL),
            "https://school.gyo6.net/gacheon/na/ntt/selectNttInfo.do?nttSn=123&mi=119615",
        )

    def test_path_only_link_is_joined_to_feed_host(self):
        self.assertEqual(
            normalize_rss_link("/gacheon/na/ntt/selectNttInfo.do?nttSn=9", FEED_URL),
            "https://school.gyo6.net/gacheon/na/ntt/selectNttInfo.do?nttSn=9",
        )

    def test_repetition_rule_is_leading_and_exactly_twice(self):
        # 중간 반복(/na/na/)과 3회 반복(/a/a/a/)은 건드리지 않는다
        self.assertEqual(
            normalize_rss_link("https://school.gyo6.net/g/na/na/x.do", FEED_URL),
            "https://school.gyo6.net/g/na/na/x.do",
        )
        self.assertEqual(
            normalize_rss_link("https://school.gyo6.net/a/a/a/x.do", FEED_URL),
            "https://school.gyo6.net/a/a/x.do",
        )

    def test_foreign_host_is_dropped(self):
        self.assertEqual(normalize_rss_link("https://evil.example.com/a", FEED_URL), "")
        self.assertEqual(normalize_rss_link("", FEED_URL), "")

    def test_trailing_slash_and_fragment_removed(self):
        self.assertEqual(
            normalize_rss_link("https://school.gyo6.net/gacheon/board/#top", FEED_URL),
            "https://school.gyo6.net/gacheon/board",
        )


class ParseFeedTest(unittest.TestCase):
    def test_rss2_reads_title_link_pubdate_and_file(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>\xea\xb0\x80\xec\xb2\x9c\xec\xb4\x88</title>
<item>
  <title>2\xed\x95\x99\xea\xb8\xb0 \xec\x95\x88\xeb\x82\xb4</title>
  <link>school.gyo6.net/gacheon/gacheon/na/ntt/selectNttInfo.do?nttSn=777&amp;mi=119615</link>
  <pubDate>Mon, 24 Aug 2026 06:13:47 +0900</pubDate>
  <guid>777</guid>
  <file><fileNm>\xeb\xa6\xac\xed\x94\x8c\xeb\xa6\xbf.pdf</fileNm>
  <dwldUrl>school.gyo6.net/gacheon/common/nttFileDownload.do?fileKey=e3dead</dwldUrl></file>
</item>
<item><title></title><link>school.gyo6.net/x</link></item>
</channel></rss>"""
        items = parse_feed(xml, flavor=FLAVOR_GYO6_RSS2, feed_url=FEED_URL)
        self.assertEqual(len(items), 1)  # 제목 빈 item 은 버린다
        item = items[0]
        self.assertEqual(item.link, "https://school.gyo6.net/gacheon/na/ntt/selectNttInfo.do?nttSn=777&mi=119615")
        self.assertEqual(item.guid, "777")
        self.assertEqual(len(item.attachments), 1)
        self.assertTrue(item.attachments[0]["url"].startswith("https://school.gyo6.net/"))

    def test_jbedu_json_reads_description_value_as_body(self):
        payload = (
            '{"items":[{"title":"\\uacf5\\uc9c0","link":'
            '"https://school.jbedu.kr/kacheon/M010401/view/6882610",'
            '"pubDate":"2026-08-24T06:13:47","guid":"6882610",'
            '"description":{"value":"<p>\\ubcf8\\ubb38</p>"}}]}'
        ).encode("utf-8")
        items = parse_feed(payload, flavor=FLAVOR_JBEDU_JSON,
                           feed_url="https://school.jbedu.kr/rss/kacheon/M010401.do")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].link, "https://school.jbedu.kr/kacheon/M010401/view/6882610")
        self.assertEqual(items[0].body_html, "<p>본문</p>")
        self.assertEqual(items[0].attachments, [])

    def test_html_error_page_raises(self):
        with self.assertRaises(Exception):
            parse_feed(b"<html><body>error</body></html>", flavor=FLAVOR_GYO6_RSS2, feed_url=FEED_URL)


if __name__ == "__main__":
    unittest.main()
