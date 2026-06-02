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

    def test_fallback_tag_is_always_flagged(self) -> None:
        # 구조가 좋아도 LLM 이 폴백했으면(=포기) 파일로 넘긴다.
        gate = assess(_NORMAL, "FALLBACK")
        self.assertTrue(gate["needs_file"])
        self.assertIn("폴백(LLM 정제 실패)", gate["reasons"])

    def test_garbage_is_flagged_low_quality(self) -> None:
        gate = assess("...", "ok")
        self.assertTrue(gate["needs_file"])
        self.assertIn("빈문서/저품질", gate["reasons"])


if __name__ == "__main__":
    unittest.main()
