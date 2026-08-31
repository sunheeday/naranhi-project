import unittest

from app.crawler.neis_client import (
    NeisApiError,
    NeisQuotaExceeded,
    _extract_rows,
)


class NeisResultCodeTest(unittest.TestCase):
    def test_quota_exceeded_raises(self):
        """ERROR-337(일일 한도)은 빈 배열이 아니라 예외여야 한다.

        지금은 화면에 '급식 정보 없음'으로 뜬다 — 서울 AJAX의 '조용한 0건'과 같은 구조다.
        """
        payload = {"RESULT": {"CODE": "ERROR-337", "MESSAGE": "일일 트래픽 제한을 넘었습니다."}}
        with self.assertRaises(NeisQuotaExceeded) as ctx:
            _extract_rows(payload, "mealServiceDietInfo")
        self.assertEqual(ctx.exception.code, "ERROR-337")

    def test_no_data_is_empty_not_error(self):
        """INFO-200(데이터 없음)은 정상이다. 휴일 급식이 여기 해당한다."""
        payload = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
        self.assertEqual(_extract_rows(payload, "mealServiceDietInfo"), [])

    def test_unknown_service_raises(self):
        payload = {"RESULT": {"CODE": "ERROR-310", "MESSAGE": "해당하는 서비스를 찾을 수 없습니다."}}
        with self.assertRaises(NeisApiError):
            _extract_rows(payload, "schoolNotice")

    def test_result_inside_head_block_is_checked(self):
        payload = {
            "schoolInfo": [
                {"head": [{"list_total_count": 0}, {"RESULT": {"CODE": "ERROR-336", "MESSAGE": "필수 값이 없습니다."}}]},
            ]
        }
        with self.assertRaises(NeisApiError):
            _extract_rows(payload, "schoolInfo")

    def test_normal_payload_returns_rows(self):
        payload = {
            "schoolInfo": [
                {"head": [{"list_total_count": 1}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."}}]},
                {"row": [{"SCHUL_NM": "가천초등학교"}]},
            ]
        }
        self.assertEqual(_extract_rows(payload, "schoolInfo"), [{"SCHUL_NM": "가천초등학교"}])

    def test_missing_result_block_is_tolerated(self):
        payload = {"schoolInfo": [{"row": [{"SCHUL_NM": "가천초등학교"}]}]}
        self.assertEqual(_extract_rows(payload, "schoolInfo"), [{"SCHUL_NM": "가천초등학교"}])


if __name__ == "__main__":
    unittest.main()
