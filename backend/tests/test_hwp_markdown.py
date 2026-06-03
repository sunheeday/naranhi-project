from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from extractor.extractors.hwp_extractor import _hwp_to_markdown, _unwrap_nested_tables
from extractor.markdown_tables import collapse_layout_tables, fix_table_structure


# 바깥 3칸 레이아웃표가 안쪽 데이터표를 감싼 HWP 전형(평촌중 '출결 관리 기준' 케이스).
_NESTED_LAYOUT_XHTML = """<html><body>
<table>
  <tr>
    <td>전화 : 381-0050</td><td>가 정 통 신 문</td><td>http://x.ms.kr</td>
  </tr>
  <tr>
    <td>
      <p>질병결석 안내입니다.</p>
      <table>
        <tr><td>결석유형</td><td>제출서류</td><td>제출일</td></tr>
        <tr><td>질병</td><td>진단서</td><td>5일 이내</td></tr>
      </table>
    </td>
    <td></td>
    <td></td>
  </tr>
</table>
</body></html>"""


class HwpMarkdownFallbackTests(unittest.TestCase):
    def test_skips_gracefully_when_hwp5html_unavailable(self) -> None:
        # hwp5html(콘솔 스크립트)이 없으면 빈 문자열 -> 호출부가 기존 OLE 체인으로 폴백한다.
        with patch("extractor.extractors.hwp_extractor._hwp5html_command", return_value=None):
            out = _hwp_to_markdown(Path("does-not-exist.hwp"), [])
        self.assertEqual(out, "")


class HwpNestedTableUnwrapTests(unittest.TestCase):
    def test_unwrap_lifts_inner_table_to_top_level(self) -> None:
        # 바깥 래퍼 표가 풀려 표 중첩이 사라지고 안쪽 데이터표만 최상위로 남아야 한다.
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(_unwrap_nested_tables(_NESTED_LAYOUT_XHTML), "html.parser")
        tables = soup.find_all("table")
        self.assertEqual(len(tables), 1)
        self.assertIsNone(tables[0].find("table"))

    def test_markdown_has_no_inline_separator_soup(self) -> None:
        # 펼친 뒤 markdown 변환하면 콘텐츠 행 안에 `| --- |` 가 끼는 직선화(파이프 떡칠)가 없어야 한다.
        import markdownify

        md = markdownify.markdownify(_unwrap_nested_tables(_NESTED_LAYOUT_XHTML), heading_style="ATX")
        md = fix_table_structure(collapse_layout_tables(md.strip())).strip()
        inline_sep = re.compile(r"\|\s*:?-{3,}:?\s*\|")
        for line in md.split("\n"):
            stripped = line.strip()
            is_separator_line = bool(re.match(r"^\|[\s\-:|]+\|$", stripped))
            if stripped.startswith("|") and not is_separator_line:
                self.assertIsNone(inline_sep.search(stripped), f"inline separator in: {stripped!r}")
        # 안쪽 데이터표 내용은 보존돼야 한다.
        self.assertIn("결석유형", md)
        self.assertIn("진단서", md)


if __name__ == "__main__":
    unittest.main()
