from __future__ import annotations

import unittest

from app.services.quality_gate import assess


_NORMAL = """# 봄 현장체험학습 안내

아래와 같이 현장체험학습을 실시합니다. 학부모님의 많은 참여 바랍니다.

| 항목 | 내용 |
| --- | --- |
| 일시 | 4월 15일 |
| 장소 | 국립과학관 |
"""

# 제목·표 없이 표가 평탄화된 세로 덤프(짧은 파편 줄만 가득)
_FLAT_DUMP = "\n".join(
    ["학교명", "공립", "유형별", "병설", "학급수", "12", "학생수", "240", "교원수", "18", "설립일", "1990"]
)

# 표 레이아웃 HWP 가 만든 중첩표 직선화 흔적(콘텐츠 행 안에 `| --- |` 가 끼어 있음)
_NESTED_TABLE_SOUP = (
    "| 전화 : 381-0050 | 가 정 통 신 문 | http://x.ms.kr |\n"
    "| --- | --- | --- |\n"
    "| 안녕하십니까 ◉ 질병결석 | | | | | --- | --- | --- | | 결석유형 | 제출서류 | 제출일 | "
    "| 질병 | 진단서 | 5일 이내 | |\n"
)


class QualityGateTests(unittest.TestCase):
    def test_normal_structured_doc_is_not_flagged(self) -> None:
        gate = assess(_NORMAL, "ok")
        self.assertFalse(gate["needs_file"])
        self.assertGreaterEqual(gate["signals"]["headings"], 1)
        self.assertGreaterEqual(gate["signals"]["tables"], 1)

    def test_flat_dump_is_flagged_as_flattened(self) -> None:
        gate = assess(_FLAT_DUMP, "ok")
        self.assertTrue(gate["needs_file"])
        self.assertTrue(any("평탄화" in reason for reason in gate["reasons"]))

    def test_fallback_with_good_content_is_not_flagged(self) -> None:
        # FALLBACK(LLM 정제 실패 → light_clean)이라도 내용이 멀쩡하면(예: 사진 OCR) 가리지 않는다.
        gate = assess(_NORMAL, "FALLBACK")
        self.assertFalse(gate["needs_file"])
        self.assertTrue(gate["signals"]["fallback"])  # 신호로는 남되 사유는 아님

    def test_fallback_with_flat_dump_is_still_flagged(self) -> None:
        # FALLBACK + 실제 깨진 세로덤프는 '평탄화' 신호로 여전히 걸린다(폴백 태그와 무관).
        gate = assess(_FLAT_DUMP, "FALLBACK")
        self.assertTrue(gate["needs_file"])
        self.assertTrue(any("평탄화" in reason for reason in gate["reasons"]))

    def test_garbage_is_flagged_low_quality(self) -> None:
        gate = assess("...", "ok")
        self.assertTrue(gate["needs_file"])
        self.assertIn("빈문서/저품질", gate["reasons"])

    def test_nested_table_soup_is_flagged(self) -> None:
        # 표 레이아웃 HWP 의 중첩표 직선화(파이프 떡칠)는 원본 파일로 우회시킨다.
        gate = assess(_NESTED_TABLE_SOUP, "ok")
        self.assertTrue(gate["needs_file"])
        self.assertTrue(any("중첩" in reason for reason in gate["reasons"]))
        self.assertTrue(gate["signals"]["nested_table"])

    def test_clean_table_is_not_flagged_as_nested(self) -> None:
        # 정상 표(구분선이 제 줄에만 있음)는 중첩 신호가 켜지지 않는다.
        gate = assess(_NORMAL, "ok")
        self.assertFalse(gate["signals"]["nested_table"])

    def test_repeated_legit_cells_are_not_flagged(self) -> None:
        # '자습 자습 자습 자습'(시험 4일) 같은 정상 반복은 가리지 않는다(과거 오탐 회귀 방지).
        md = (
            "# 시험 일정\n\n"
            "| 교시 | 화 | 수 | 목 | 금 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 2교시 | 자습 | 자습 | 자습 | 자습 |\n"
            "| 3교시 | 도덕 | 역사 | 기가 | 과학 |\n"
        )
        gate = assess(md, "ok")
        self.assertFalse(gate["needs_file"])
        self.assertTrue(gate["signals"]["repeat_junk"])  # 신호로는 잡되 needs_file 사유는 아님


if __name__ == "__main__":
    unittest.main()
