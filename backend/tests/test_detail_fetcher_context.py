from __future__ import annotations

import unittest

from extractor.fetch_variants.sen_ajax import sen_ajax_post_data


class DetailFetcherContextTests(unittest.TestCase):
    def test_builds_sen_ajax_post_data_from_crawl_result(self) -> None:
        context = {
            "crawl_result": {
                "board_url": "https://yeongdeungpo.sen.ms.kr/73623/subMenu.do",
                "post": {
                    "post_id": "27154649",
                    "board_key": "menuNo=73623|bbsId=BBSMSTR_000000010392",
                },
            }
        }

        data = sen_ajax_post_data(
            "https://yeongdeungpo.sen.ms.kr/dggb/module/board/selectBoardDetailAjax.do?nttId=27154649",
            context,
        )

        self.assertEqual(
            data,
            {
                "nttId": "27154649",
                "bbsId": "BBSMSTR_000000010392",
                "menuNo": "73623",
            },
        )

    def test_non_ajax_url_has_no_post_data(self) -> None:
        self.assertIsNone(sen_ajax_post_data("https://example.school/notice/1", {}))


if __name__ == "__main__":
    unittest.main()
