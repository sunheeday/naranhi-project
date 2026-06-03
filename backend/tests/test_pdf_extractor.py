from __future__ import annotations

import unittest

from extractor.extractors.pdf_extractor import _looks_flattened


class PdfFlattenedDetectionTests(unittest.TestCase):
    def test_flattened_table_columns_detected(self) -> None:
        # 다단/표가 세로로 깨진 PyMuPDF 출력(짧은 파편 줄 다수) → OCR 폴백 대상.
        flat = "\n".join([
            "구분", "비고", "1명", "2명", "3명", "4명",
            "유학경비", "60만원", "80만원", "100만원", "120만원",
            "대상", "유형", "신청서제출", "사전방문",
        ])
        self.assertTrue(_looks_flattened(flat))

    def test_normal_prose_not_flattened(self) -> None:
        prose = (
            "# 2026 청소년 역사·평화 캠프 안내\n\n"
            "인천광역시교육청에서 학생들의 역사 의식 고취를 위해 참가 학생을 공모합니다.\n"
            "- 장소: 중국 상하이 및 난징 일원입니다.\n"
            "- 대상: 중학교 1~3학년 학생 5명을 선발할 예정입니다.\n"
            "- 신청 기간: 2026년 6월 8일까지 신청서를 제출해 주시기 바랍니다.\n"
        )
        self.assertFalse(_looks_flattened(prose))

    def test_short_text_not_flattened(self) -> None:
        self.assertFalse(_looks_flattened("구분\n1명\n2명"))


if __name__ == "__main__":
    unittest.main()
