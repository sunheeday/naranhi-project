import unittest

from app.crawler.bell_schedule_finder import (
    bell_link_candidates,
    content_image_urls,
    looks_like_bell_table,
    normalize_bell_periods,
    parse_bell_text,
    visible_text,
)


class NormalizeBellPeriodsTest(unittest.TestCase):
    """말이 안 되는 표는 통째로 버린다. 반쯤 맞는 일과표가 제일 위험하다 —
    틀린 하교 시각으로 알림이 나가면 아무 알림도 없느니만 못하다."""

    def test_accepts_pcbuheung_real_table(self):
        # 부천부흥중 2026학년도 시정표 실측(2026-08-30 홈페이지 이미지 판독)
        items = [
            {"period": 1, "start_time": "09:10", "end_time": "09:55"},
            {"period": 2, "start_time": "10:05", "end_time": "10:50"},
            {"period": 3, "start_time": "11:00", "end_time": "11:45"},
            {"period": 4, "start_time": "11:55", "end_time": "12:40"},
            {"period": 5, "start_time": "13:30", "end_time": "14:15"},
            {"period": 6, "start_time": "14:25", "end_time": "15:10"},
            {"period": 7, "start_time": "15:20", "end_time": "16:05"},
        ]
        out = normalize_bell_periods(items)
        self.assertEqual(len(out), 7)
        self.assertEqual(out[0]["start_time"], "09:10")
        self.assertEqual(out[6]["end_time"], "16:05")

    def test_点심_직후_쉬는시간_0분을_허용한다(self):
        """4교시 12:40 종료 → 5교시 13:30 시작처럼 점심을 사이에 둔 간격은 정상이다."""
        out = normalize_bell_periods([
            {"period": 4, "start_time": "11:55", "end_time": "12:40"},
            {"period": 5, "start_time": "12:40", "end_time": "13:25"},
        ])
        self.assertEqual(len(out), 2)

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            normalize_bell_periods([])

    def test_rejects_start_after_end(self):
        with self.assertRaises(ValueError):
            normalize_bell_periods([{"period": 1, "start_time": "10:00", "end_time": "09:00"}])

    def test_rejects_overlap(self):
        with self.assertRaises(ValueError):
            normalize_bell_periods([
                {"period": 1, "start_time": "09:10", "end_time": "09:55"},
                {"period": 2, "start_time": "09:30", "end_time": "10:15"},
            ])

    def test_rejects_out_of_range_period(self):
        with self.assertRaises(ValueError):
            normalize_bell_periods([{"period": 0, "start_time": "09:00", "end_time": "09:40"}])
        with self.assertRaises(ValueError):
            normalize_bell_periods([{"period": 13, "start_time": "09:00", "end_time": "09:40"}])

    def test_rejects_absurd_clock(self):
        """새벽 3시 1교시는 판독 실패다."""
        with self.assertRaises(ValueError):
            normalize_bell_periods([{"period": 1, "start_time": "03:00", "end_time": "03:40"}])

    def test_rejects_duplicate_period(self):
        with self.assertRaises(ValueError):
            normalize_bell_periods([
                {"period": 1, "start_time": "09:00", "end_time": "09:40"},
                {"period": 1, "start_time": "09:50", "end_time": "10:30"},
            ])

    def test_rejects_absurd_lesson_length(self):
        """3분짜리 혹은 4시간짜리 «교시»는 표를 잘못 읽은 것이다."""
        with self.assertRaises(ValueError):
            normalize_bell_periods([{"period": 1, "start_time": "09:00", "end_time": "09:03"}])
        with self.assertRaises(ValueError):
            normalize_bell_periods([{"period": 1, "start_time": "09:00", "end_time": "13:00"}])

    def test_sorts_by_period(self):
        out = normalize_bell_periods([
            {"period": 2, "start_time": "09:50", "end_time": "10:30"},
            {"period": 1, "start_time": "09:00", "end_time": "09:40"},
        ])
        self.assertEqual([p["period"] for p in out], [1, 2])

    def test_normalizes_seconds_and_str_period(self):
        out = normalize_bell_periods([
            {"period": "1", "start_time": "09:00:00", "end_time": "09:40:00"},
        ])
        self.assertEqual(out[0], {"period": 1, "start_time": "09:00", "end_time": "09:40"})


class ParseBellTextTest(unittest.TestCase):
    def test_parses_pipe_lines(self):
        out = parse_bell_text("1|09:10|09:55\n2|10:05|10:50\n")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[1]["start_time"], "10:05")

    def test_parses_korean_table_text(self):
        """가정통신문·홈페이지 본문에 흔한 «1교시 09:10~09:55» 형태."""
        out = parse_bell_text("1교시 09:10~09:55 (45분)  2교시 10:05 ~ 10:50")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], {"period": 1, "start_time": "09:10", "end_time": "09:55"})

    def test_parses_en_dash(self):
        out = parse_bell_text("3교시 11:00–11:45")
        self.assertEqual(out[0]["end_time"], "11:45")

    def test_ignores_unrelated_times(self):
        """교무실 운영시간(08:40~16:40)만 있는 페이지는 0건이어야 한다 —
        부천부흥중 일과표 «페이지»의 글자 본문이 실제로 이랬다."""
        text = "교무실 070-7099-0874 (08:40~16:40) 행정실 070-7099-0854 (08:40~16:40)"
        self.assertEqual(parse_bell_text(text), [])

    def test_single_digit_hour(self):
        out = parse_bell_text("1교시 9:10~9:55")
        self.assertEqual(out[0]["start_time"], "09:10")


class LooksLikeBellTableTest(unittest.TestCase):
    def test_true_when_enough_periods(self):
        self.assertTrue(looks_like_bell_table("1교시 09:10~09:55 2교시 10:05~10:50 3교시 11:00~11:45"))

    def test_false_for_footer_only(self):
        self.assertFalse(looks_like_bell_table("교무실 070-7099-0874 (08:40~16:40)"))

    def test_false_for_two_periods(self):
        """두 줄만으로는 일과표라 보지 않는다 — 시험 안내문 등이 걸린다."""
        self.assertFalse(looks_like_bell_table("1교시 09:10~09:55 2교시 10:05~10:50"))


class ContentImageUrlsTest(unittest.TestCase):
    def test_picks_content_image_and_skips_decoration(self):
        """실측에서 장식 이미지는 logo/icon/btn/banner/menuImg 등으로 구분됐다."""
        html = """
        <img src="/images/template/sub/s_visual.png" alt="배너">
        <img src="/images/common/icoHome.gif" alt="메인페이지">
        <img src="/upload/x/subImg/img_abc.png" alt="sub_02.png">
        <img src="/upload/x/cntntsFile/2026/03/ABC.png" alt="일과표 이미지">
        """
        urls = content_image_urls(html, "https://school.example.kr/page.do")
        self.assertIn("https://school.example.kr/upload/x/cntntsFile/2026/03/ABC.png", urls)
        self.assertNotIn("https://school.example.kr/images/common/icoHome.gif", urls)

    def test_alt_hint_ranks_first(self):
        html = """
        <img src="/upload/a.png" alt="학교 전경">
        <img src="/upload/b.png" alt="2026 일과표">
        """
        urls = content_image_urls(html, "https://s.kr/p")
        self.assertEqual(urls[0], "https://s.kr/upload/b.png")

    def test_empty_when_no_images(self):
        self.assertEqual(content_image_urls("<p>없음</p>", "https://s.kr/p"), [])


class BellLinkCandidatesTest(unittest.TestCase):
    """extract_links 를 쓰지 않는 이유가 여기 있다. 그쪽은 같은 URL 을 합치면서
    «첫» 앵커 텍스트만 남기는데, 실측 부천부흥중에서 일과표 링크가 상위 메뉴 이름인
    '학생마당' 으로 붙어 나왔다. 그 라벨로는 사람도 AI도 일과표인 줄 알 수 없다."""

    def test_keeps_every_anchor_text_for_same_url(self):
        html = """
        <a href="/p.do?mi=8442">학생마당</a>
        <a href="/p.do?mi=8442">일과표</a>
        """
        cands = bell_link_candidates(html, "https://s.kr/")
        texts = [c.text for c in cands]
        self.assertIn("일과표", texts)

    def test_ranks_exact_bell_wording_first(self):
        html = """
        <a href="/a.do">학교소개</a>
        <a href="/b.do">일과표</a>
        """
        cands = bell_link_candidates(html, "https://s.kr/")
        self.assertEqual(cands[0].text, "일과표")

    def test_excludes_carousel_pause_button(self):
        """실측에서 «시정» 매칭 둘이 전부 캐러셀 일시정지 버튼이었다."""
        html = '<a href="#stop">일시정지</a><a href="javascript:;">일시정지</a>'
        self.assertEqual(bell_link_candidates(html, "https://s.kr/"), [])

    def test_excludes_academic_calendar_and_class_timetable(self):
        html = '<a href="/a.do">학사일정</a><a href="/b.do">시간표</a>'
        matched = [c for c in bell_link_candidates(html, "https://s.kr/") if c.is_bell_wording]
        self.assertEqual(matched, [])

    def test_skips_javascript_and_anchor_hrefs(self):
        html = '<a href="javascript:void(0)">일과표</a><a href="#x">일과표</a>'
        self.assertEqual(bell_link_candidates(html, "https://s.kr/"), [])

    def test_returns_non_bell_links_too_for_ai_fallback(self):
        """키워드로 못 찾으면 AI 가 훑을 수 있게 일반 링크도 담아 둔다."""
        html = '<a href="/a.do">학교현황</a>'
        cands = bell_link_candidates(html, "https://s.kr/")
        self.assertEqual(len(cands), 1)
        self.assertFalse(cands[0].is_bell_wording)


class VisibleTextTest(unittest.TestCase):
    def test_strips_script_and_style(self):
        html = "<style>a{}</style><script>var x=1</script><p>1교시 09:10~09:55</p>"
        self.assertEqual(visible_text(html), "1교시 09:10~09:55")


if __name__ == "__main__":
    unittest.main()
