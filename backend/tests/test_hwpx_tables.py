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


class HwpxMergedCellTests(unittest.TestCase):
    # 1회차(rowSpan=2)가 두 행을 차지 → 둘째 행엔 <tc>가 1개뿐(김미숙). cellAddr 로 위치를 잡아
    # 김미숙이 2번째 열(해설사)에 와야 한다(옛 순차 방식은 1번째 열로 밀려 어긋났음).
    _MERGED = (
        "<sec><tbl>"
        "<tr>"
        '<tc><cellAddr colAddr="0" rowAddr="0"/><cellSpan colSpan="1" rowSpan="2"/>'
        "<subList><p><run><t>1회차</t></run></p></subList></tc>"
        '<tc><cellAddr colAddr="1" rowAddr="0"/><cellSpan colSpan="1" rowSpan="1"/>'
        "<subList><p><run><t>김향란</t></run></p></subList></tc>"
        "</tr>"
        "<tr>"
        '<tc><cellAddr colAddr="1" rowAddr="1"/><cellSpan colSpan="1" rowSpan="1"/>'
        "<subList><p><run><t>김미숙</t></run></p></subList></tc>"
        "</tr>"
        "</tbl></sec>"
    )

    def test_rowspan_keeps_columns_aligned(self) -> None:
        out = _extract_hwpx_structured_text(_make_hwpx(self._MERGED))
        self.assertIn("| 1회차 | 김향란 |", out)
        self.assertIn("|  | 김미숙 |", out)        # 2번째 열(병합셀 아래 1열은 빈칸)
        self.assertNotIn("| 김미숙 |  |", out)      # 1번째 열로 밀리면 안 됨(옛 버그)


class HwpxWrapperTableTests(unittest.TestCase):
    # 문서 전체를 표 한 칸(<tbl>)으로 감싸고 그 안에 진짜 표가 중첩된 흔한 레이아웃.
    # 래퍼는 투명 처리 → 안쪽 문단=본문, 안쪽 표=markdown 표로 뽑혀야 한다(벽글 방지).
    _WRAP = (
        "<sec><tbl><tr><tc><subList>"
        "<p><run><t>제4기 활동 개요</t></run></p>"
        "<p><run>"
        "<tbl>"
        '<tr><tc><cellAddr colAddr="0" rowAddr="0"/><subList><p><run><t>인원</t></run></p></subList></tc>'
        '<tc><cellAddr colAddr="1" rowAddr="0"/><subList><p><run><t>기간</t></run></p></subList></tc></tr>'
        '<tr><tc><cellAddr colAddr="0" rowAddr="1"/><subList><p><run><t>15명</t></run></p></subList></tc>'
        '<tc><cellAddr colAddr="1" rowAddr="1"/><subList><p><run><t>2년</t></run></p></subList></tc></tr>'
        "</tbl>"
        "</run></p>"
        "</subList></tc></tr></tbl></sec>"
    )

    def test_wrapper_table_is_transparent(self) -> None:
        out = _extract_hwpx_structured_text(_make_hwpx(self._WRAP))
        self.assertIn("제4기 활동 개요", out)   # 안쪽 문단 = 본문
        self.assertIn("| 인원 | 기간 |", out)    # 안쪽 표 = markdown 표
        self.assertIn("| 15명 | 2년 |", out)
        self.assertIn("| --- | --- |", out)      # 벽글 아님(구분선 존재)


if __name__ == "__main__":
    unittest.main()
