from __future__ import annotations

import unittest

from extractor.html_text_extractor import extract_html_text


class HtmlContentBoxFallbackTests(unittest.TestCase):
    def test_uses_content_box_not_whole_page_when_precise_is_empty(self) -> None:
        # 정밀 selector(div.conts)가 이미지뿐이라 비면, 페이지 전체(메뉴 포함)가 아니라
        # 본문 박스(.subContent_body)에서 텍스트를 가져와야 한다(메뉴가 본문으로 새지 않음).
        html = """
        <html><body>
          <div class="snb">메뉴닫기 홈페이지 검색 알림마당 학교일정 급식안내 방과후학교</div>
          <div class="subContent_body">
            <div class="conts"><img src="notice.png" alt=""></div>
            <p>실제 공지 본문 내용입니다.</p>
          </div>
        </body></html>
        """
        out = extract_html_text(html)
        self.assertIn("실제 공지 본문 내용입니다.", out)
        self.assertNotIn("학교일정", out)
        self.assertNotIn("방과후학교", out)

    def test_precise_selector_with_text_still_wins(self) -> None:
        html = (
            '<html><body><div class="conts">정밀 본문 텍스트</div>'
            '<div class="subContent_body">박스 텍스트</div></body></html>'
        )
        self.assertEqual(extract_html_text(html), "정밀 본문 텍스트")


if __name__ == "__main__":
    unittest.main()
