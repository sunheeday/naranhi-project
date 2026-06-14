import unittest

from app.services.school_crawler_service import (
    DiscoveredPostPreview,
    _apply_watermark_filter,
    _watermark_post_value,
)


def _post(post_id, *, board_key="b1", method="href", source="href query"):
    return DiscoveredPostPreview(
        title="t",
        post_id=post_id,
        post_uid=f"cms:{board_key}:{post_id}",
        board_key=board_key,
        detail_url=f"https://x/{post_id}",
        status="success",
        method=method,
        source=source,
        cms_key="cms",
        parser_family="generic",
        reason="",
    )


class WatermarkPostValueTest(unittest.TestCase):
    def test_numeric_sequence_sources_are_eligible(self):
        self.assertEqual(_watermark_post_value(_post("1218492", source="href query")), 1218492)
        self.assertEqual(_watermark_post_value(_post("33823300", source="href query boardSeq")), 33823300)
        self.assertEqual(_watermark_post_value(_post("12345", source="path /view/")), 12345)
        self.assertEqual(_watermark_post_value(_post("999", method="onclick", source="onclick goView arg 3")), 999)
        self.assertEqual(_watermark_post_value(_post("777", method="ajax_get", source="onclick fnView arg 2")), 777)

    def test_generated_and_file_download_methods_excluded(self):
        # Gemini/해시 생성 글번호, 첨부 파일번호는 시간순 보장 안 됨 → 워터마크 비대상
        self.assertIsNone(_watermark_post_value(_post("a3f9c1b2", method="generated", source="derived detail_url hash")))
        self.assertIsNone(_watermark_post_value(_post("555", method="file_download", source="onclick hno")))

    def test_risky_sources_excluded(self):
        self.assertIsNone(_watermark_post_value(_post("2026", source="path numeric segment")))
        self.assertIsNone(_watermark_post_value(_post("7", source="href query id")))

    def test_non_numeric_excluded(self):
        self.assertIsNone(_watermark_post_value(_post("abc", source="href query")))
        self.assertIsNone(_watermark_post_value(_post("", source="href query")))


class ApplyWatermarkFilterTest(unittest.TestCase):
    def test_first_crawl_keeps_all_and_sets_baseline(self):
        posts = [_post("100"), _post("105"), _post("103")]
        kept, updated = _apply_watermark_filter(posts, {})
        self.assertEqual([p.post_id for p in kept], ["100", "105", "103"])
        self.assertEqual(updated, {"b1": 105})

    def test_baseline_drops_old_keeps_new(self):
        posts = [_post("105"), _post("103"), _post("100"), _post("110")]
        kept, updated = _apply_watermark_filter(posts, {"b1": 103})
        self.assertEqual([p.post_id for p in kept], ["105", "110"])  # 103(==), 100(<) 제외
        self.assertEqual(updated, {"b1": 110})

    def test_integer_comparison_not_string(self):
        # 문자열 비교였다면 "9">"99"=True(잘못 유지), "100"<"99"=True(잘못 제외)
        posts = [_post("100"), _post("9")]
        kept, updated = _apply_watermark_filter(posts, {"b1": 99})
        self.assertEqual([p.post_id for p in kept], ["100"])  # 100>99 유지, 9<99 제외
        self.assertEqual(updated, {"b1": 100})

    def test_ineligible_posts_always_kept_and_dont_move_watermark(self):
        posts = [_post("50", method="generated", source="derived detail_url hash")]
        kept, updated = _apply_watermark_filter(posts, {"b1": 999})
        self.assertEqual([p.post_id for p in kept], ["50"])  # 비대상 → 기준선 무시하고 유지
        self.assertEqual(updated, {"b1": 999})  # 변동 없음

    def test_watermark_is_per_board_key(self):
        posts = [_post("100", board_key="b1"), _post("5", board_key="b2"), _post("40", board_key="b1")]
        kept, updated = _apply_watermark_filter(posts, {"b1": 50, "b2": 3})
        self.assertEqual([(p.board_key, p.post_id) for p in kept], [("b1", "100"), ("b2", "5")])  # b1 40<50 제외
        self.assertEqual(updated, {"b1": 100, "b2": 5})


if __name__ == "__main__":
    unittest.main()
