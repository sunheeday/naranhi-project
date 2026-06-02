from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from extractor.extractors.hwpx_extractor import _extract_hwpx_structured_text


_TABLE_SECTION = (
    "<sec>"
    "<p><run><t>안내문 제목</t></run></p>"
    "<tbl>"
    "<tr>"
    "<tc><subList><p><run><t>항목</t></run></p></subList></tc>"
    "<tc><subList><p><run><t>값</t></run></p></subList></tc>"
    "</tr>"
    "<tr>"
    "<tc><subList><p><run><t>날짜</t></run></p></subList></tc>"
    "<tc><subList><p><run><t>4월 15일</t></run></p></subList></tc>"
    "</tr>"
    "</tbl>"
    "</sec>"
)


def _make_hwpx(section_xml: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix="hwpx-test-")) / "t.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", section_xml)
    return path


class HwpxTableTests(unittest.TestCase):
    def test_table_is_extracted_as_markdown(self) -> None:
        out = _extract_hwpx_structured_text(_make_hwpx(_TABLE_SECTION))
        self.assertIn("안내문 제목", out)
        self.assertIn("| 항목 | 값 |", out)
        self.assertIn("| --- | --- |", out)
        self.assertIn("| 날짜 | 4월 15일 |", out)

    def test_table_cells_are_not_duplicated_as_body(self) -> None:
        # 표 셀 안 <p>(항목/값/...)가 본문으로 또 추출되면 안 된다(중복 0).
        out = _extract_hwpx_structured_text(_make_hwpx(_TABLE_SECTION))
        self.assertEqual(out.count("항목"), 1)
        self.assertEqual(out.count("4월 15일"), 1)

    def test_plain_paragraphs_without_table(self) -> None:
        section = "<sec><p><run><t>첫 문장</t></run></p><p><run><t>둘째 문장</t></run></p></sec>"
        out = _extract_hwpx_structured_text(_make_hwpx(section))
        self.assertEqual(out, "첫 문장\n둘째 문장")


if __name__ == "__main__":
    unittest.main()
