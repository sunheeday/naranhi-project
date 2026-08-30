import unittest

from app.translation.validators import validate_output_by_code


KO = "# 안내\n\n행사는 6월 1일에 합니다.\n\n- 준비물: 필기구\n- 장소: 강당\n\n문의 070-1234-5678"


class HangulLeftoverTest(unittest.TestCase):
    """실측 결함(2026-08-30): 베트남어 번역본에 「일회용」이 한글 그대로 남았다.
    학부모가 못 읽는 글자가 본문에 박히는 것이라 사실 오류만큼 나쁘다.
    AI 검증자를 붙일 자리가 아니다 — 정규식이면 0원·0초·100% 다."""

    def test_flags_korean_left_in_vietnamese(self):
        out = validate_output_by_code(
            source_text=KO,
            translated_text="Sự kiện vào ngày 1 tháng 6. sản phẩm일회용 không dùng.",
            target_language="vi",
        )
        self.assertEqual(out["status"], "failed")
        codes = [i["code"] for i in out["issues"]]
        self.assertIn("hangul_leftover", codes)
        issue = next(i for i in out["issues"] if i["code"] == "hangul_leftover")
        self.assertIn("일회용", issue["detail"])

    def test_korean_target_is_never_flagged(self):
        out = validate_output_by_code(
            source_text=KO, translated_text=KO, target_language="ko",
        )
        self.assertNotIn("hangul_leftover", [i["code"] for i in out["issues"]])

    def test_clean_vietnamese_passes(self):
        out = validate_output_by_code(
            source_text=KO,
            translated_text="# Thông báo\n\nSự kiện vào ngày 1 tháng 6.\n\n- Dụng cụ: bút\n- Địa điểm: hội trường\n\nLiên hệ 070-1234-5678",
            target_language="vi",
        )
        self.assertEqual(out["status"], "passed", out["issues"])

    def test_single_stray_syllable_is_ignored(self):
        """따옴표 안 고유명사 한 글자까지 잡으면 오탐이 된다. 2자 이상만 본다."""
        out = validate_output_by_code(
            source_text=KO,
            translated_text="# Thong bao\n\nSu kien ngay 1 thang 6.\n\n- A: b\n- C: d\n\nLien he 070-1234-5678 (해)",
            target_language="vi",
        )
        self.assertNotIn("hangul_leftover", [i["code"] for i in out["issues"]])


class TruncationTest(unittest.TestCase):
    def test_flags_severe_truncation(self):
        # 길이 검사는 원문 200자 이상일 때만 돈다 — 짧은 공지에서 오탐이 나지 않게.
        long_ko = KO + "\n\n" + ("자세한 내용은 첨부된 가정통신문을 확인해 주시기 바랍니다. " * 5)
        self.assertGreaterEqual(len(long_ko.strip()), 200)
        out = validate_output_by_code(
            source_text=long_ko, translated_text="Thong bao.", target_language="vi",
        )
        self.assertIn("too_short", [i["code"] for i in out["issues"]])
        self.assertEqual(out["status"], "failed")

    def test_does_not_flag_normal_length(self):
        out = validate_output_by_code(
            source_text=KO,
            translated_text="# Thong bao\n\nSu kien vao ngay 1 thang 6.\n\n- Dung cu: but\n- Dia diem: hoi truong\n\nLien he 070-1234-5678",
            target_language="vi",
        )
        self.assertNotIn("too_short", [i["code"] for i in out["issues"]])

    def test_empty_output_is_failed(self):
        out = validate_output_by_code(source_text=KO, translated_text="", target_language="vi")
        self.assertEqual(out["status"], "failed")
        self.assertIn("empty_output", [i["code"] for i in out["issues"]])


class StructureTest(unittest.TestCase):
    def test_flags_missing_list_items(self):
        """원문 목록 2개 중 1개가 사라졌다 = 항목 누락."""
        out = validate_output_by_code(
            source_text=KO,
            translated_text="# Thong bao\n\nSu kien vao ngay 1 thang 6 nam nay.\n\n- Dung cu: but muc\n\nLien he 070-1234-5678",
            target_language="vi",
        )
        self.assertIn("list_items_lost", [i["code"] for i in out["issues"]])

    def test_flags_missing_headings(self):
        out = validate_output_by_code(
            source_text="# A\n\n## B\n\n본문입니다 그리고 더 긴 본문 내용이 이어집니다.",
            translated_text="Noi dung va noi dung dai hon tiep theo o day nhe.",
            target_language="vi",
        )
        self.assertIn("headings_lost", [i["code"] for i in out["issues"]])

    def test_same_structure_passes(self):
        out = validate_output_by_code(
            source_text=KO,
            translated_text="# Thong bao\n\nSu kien vao ngay 1 thang 6.\n\n- Dung cu: but\n- Dia diem: hoi truong\n\nLien he 070-1234-5678",
            target_language="vi",
        )
        self.assertEqual(out["status"], "passed", out["issues"])


class RepetitionTest(unittest.TestCase):
    def test_flags_looping_model(self):
        """모델이 같은 문장을 반복하며 도는 실패 양상."""
        line = "Vui long tham gia phan loai rac thai tai nha."
        out = validate_output_by_code(
            source_text=KO,
            translated_text="# T\n\n" + "\n".join([line] * 5),
            target_language="vi",
        )
        self.assertIn("repeated_line", [i["code"] for i in out["issues"]])

    def test_short_repeats_are_ignored(self):
        """목록의 '- 예' 같은 짧은 반복은 정상이다."""
        out = validate_output_by_code(
            source_text=KO,
            translated_text="# Thong bao\n\nSu kien ngay 1 thang 6.\n\n- Co\n- Co\n- Co\n\nLien he 070-1234-5678",
            target_language="vi",
        )
        self.assertNotIn("repeated_line", [i["code"] for i in out["issues"]])


class SeverityTest(unittest.TestCase):
    """관점마다 무게가 다르다. 사실·가독성은 재시도, 나머지는 경고다 —
    사소한 지적으로 재번역을 돌리면 돈만 나가고 하드팩트가 깨질 수 있다."""

    def test_hangul_leftover_is_blocking(self):
        out = validate_output_by_code(
            source_text=KO, translated_text="abc 일회용 def ghi jkl mno pqr stu vwx", target_language="vi",
        )
        self.assertEqual(out["status"], "failed")

    def test_structure_only_is_warning_not_failure(self):
        out = validate_output_by_code(
            source_text=KO,
            translated_text="Su kien vao ngay 1 thang 6. Dung cu la but. Dia diem hoi truong. Lien he 070-1234-5678",
            target_language="vi",
        )
        self.assertEqual(out["status"], "warned")
        self.assertTrue(out["issues"])


if __name__ == "__main__":
    unittest.main()
