from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from extractor.extractors.hwp_extractor import (
    _expand_table_spans,
    _hwp_to_markdown,
    _unwrap_nested_tables,
)
from extractor.markdown_tables import collapse_layout_tables, fix_table_structure, is_separator


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


class FixTableStructureSeparatorTests(unittest.TestCase):
    def test_inserts_separator_when_table_has_none(self) -> None:
        # markdownify 가 <thead> 없이 만든 구분선 없는 표(평촌중 '경조사 일수')도 GFM 유효화.
        md = (
            "| 구분 | 대상 | 일수 |\n"
            "| 결혼 | 형제, 자매, 부, 모 | 1 |\n"
            "| 사망 | 부모, 조부모 | 5 |"
        )
        out = fix_table_structure(md)
        lines = out.split("\n")
        self.assertRegex(lines[1].strip(), r"^\|[\s\-:|]+\|$")  # 2번째 줄 = 구분선
        self.assertIn("---", lines[1])
        self.assertEqual(lines[0].count("|"), lines[1].count("|"))  # 헤더/구분선 열수 일치
        # 데이터 행은 그대로 보존
        self.assertIn("| 결혼 | 형제, 자매, 부, 모 | 1 |", out)
        self.assertIn("| 사망 | 부모, 조부모 | 5 |", out)

    def test_existing_separator_not_duplicated(self) -> None:
        # 이미 구분선이 있는 정상 표는 구분선이 하나만 유지된다(중복 삽입 없음).
        md = "| a | b |\n| --- | --- |\n| 1 | 2 |"
        out = fix_table_structure(md)
        self.assertEqual(sum(1 for ln in out.split("\n") if is_separator(ln)), 1)

    def test_single_pipe_line_not_made_into_table(self) -> None:
        # 한 줄짜리 `|` 는 표로 취급하지 않는다(구분선 안 끼움).
        md = "| 그냥 한 줄 |"
        out = fix_table_structure(md)
        self.assertNotIn("---", out)


class HwpTableSpanExpansionTests(unittest.TestCase):
    def test_rowspan_expanded_to_full_grid(self) -> None:
        from bs4 import BeautifulSoup

        html = '<table><tr><th rowspan="2">유형</th><th>자료</th></tr><tr><td>진단서</td></tr></table>'
        soup = BeautifulSoup(_expand_table_spans(html), "html.parser")
        rows = soup.find_all("tr")
        self.assertEqual(len(rows), 2)
        for r in rows:  # 모든 행이 2칸으로 정규화
            self.assertEqual(len(r.find_all(["td", "th"])), 2)
        r1 = [c.get_text() for c in rows[1].find_all(["td", "th"])]
        self.assertEqual(r1[1], "진단서")  # rowspan 아래칸은 빈칸, 진단서는 2번째 칸

    def test_colspan_expanded(self) -> None:
        from bs4 import BeautifulSoup

        html = '<table><tr><td colspan="3">머리</td></tr><tr><td>a</td><td>b</td><td>c</td></tr></table>'
        soup = BeautifulSoup(_expand_table_spans(html), "html.parser")
        rows = soup.find_all("tr")
        self.assertEqual(len(rows[0].find_all(["td", "th"])), 3)  # colspan 3 -> 3칸

    def test_table_without_spans_keeps_content(self) -> None:
        html = "<table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table>"
        out = _expand_table_spans(html)
        for token in ("a", "b", "1", "2"):
            self.assertIn(token, out)

    def test_merged_table_renders_as_valid_gfm_table(self) -> None:
        import markdownify

        html = '<table><tr><th rowspan="2">유형</th><th>자료</th></tr><tr><td>진단서</td></tr></table>'
        md = markdownify.markdownify(_expand_table_spans(html), heading_style="ATX")
        md = fix_table_structure(collapse_layout_tables(md.strip())).strip()
        self.assertTrue(any(is_separator(ln) for ln in md.split("\n")))  # 구분선 = 유효 GFM
        self.assertIn("진단서", md)


class HwpFirstTierSilentExitTest(unittest.IsolatedAsyncioTestCase):
    """1순위(hwp5html)가 실패했으면 이유가 반드시 warnings 에 남아야 한다.

    운영 6건이 2순위로 떨어졌는데 이유가 하나도 기록되지 않았다. 침묵 이탈이
    남아 있으면 Task 5(임계값 완화)가 먹혔는지 검증할 수단이 없다.
    """

    async def test_short_markdown_records_reason(self) -> None:
        from unittest.mock import patch

        from extractor.extractors import hwp_extractor

        with patch.object(hwp_extractor, "_hwp_to_markdown", return_value="짧음"), patch.object(
            hwp_extractor, "_try_hwp_ole_bodytext", return_value="본문 텍스트가 충분히 길게 들어 있는 문단입니다."
        ):
            result = await hwp_extractor.extract_hwp_text(
                Path("dummy.hwp"), source_name="dummy.hwp", gemini=None, work_dir=Path(".")
            )

        self.assertEqual(result.method, "hwp_ole_bodytext_filtered")
        self.assertTrue(
            any(w.startswith("hwp5html_too_short:") for w in result.warnings),
            f"이유가 기록되지 않았다: {result.warnings}",
        )

    async def test_missing_command_records_reason(self) -> None:
        from unittest.mock import patch

        from extractor.extractors import hwp_extractor

        warnings: list[str] = []
        with patch.object(hwp_extractor, "_hwp5html_command", return_value=None):
            markdown = hwp_extractor._hwp_to_markdown(Path("dummy.hwp"), warnings)

        self.assertEqual(markdown, "")
        self.assertIn("hwp5html_skip_no_command", warnings)


if __name__ == "__main__":
    unittest.main()
