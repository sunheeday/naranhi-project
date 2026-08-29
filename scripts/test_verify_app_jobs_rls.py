"""verify_app_jobs_rls.classify 판정 표. 네트워크 없이 돈다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_app_jobs_rls import BLOCKED, EXPOSED, INDETERMINATE, classify


class ClassifyTest(unittest.TestCase):
    def test_zero_rows_is_blocked(self):
        self.assertEqual(classify(0, "*/0")[0], BLOCKED)

    def test_rows_present_is_exposed(self):
        self.assertEqual(classify(1, "0-0/230")[0], EXPOSED)

    def test_body_rows_without_count_is_exposed(self):
        """전체가 0 이라도 본문에 행이 오면 노출이다."""
        self.assertEqual(classify(1, "*/0")[0], EXPOSED)

    def test_unknown_count_is_indeterminate(self):
        """PostgREST 의 * 는 «카운트 미확정» 이지 «0행» 이 아니다."""
        self.assertEqual(classify(0, "*/*")[0], INDETERMINATE)

    def test_missing_header_is_indeterminate(self):
        self.assertEqual(classify(0, None)[0], INDETERMINATE)

    def test_malformed_header_is_indeterminate(self):
        self.assertEqual(classify(0, "garbage")[0], INDETERMINATE)


if __name__ == "__main__":
    unittest.main()
