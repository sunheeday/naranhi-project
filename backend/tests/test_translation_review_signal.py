import unittest

from postgrest.exceptions import APIError

from app.services.notice_service import _needs_review_from_pipeline


class NeedsReviewTest(unittest.TestCase):
    def test_clean_translation_does_not_need_review(self):
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": "안녕하세요", "admin_review": {"required": False, "reason": None}},
            {"validation_status": "passed", "validation_failure_reason": None},
        )
        self.assertFalse(needs)
        self.assertIsNone(reason)

    def test_validation_failure_reason_raises_the_flag(self):
        """검증이 실패해도 번역문이 있으면 validation_status 가 'passed' 로 덮어써진다
        (notice_service.py 의 _save_translation_result). 사유는 평문 로그로만 남아 있었다."""
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": "안녕하세요"},
            {"validation_failure_reason": "hard_fact_mismatch: 날짜 3건"},
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "hard_fact_mismatch: 날짜 3건")

    def test_quota_fallback_raises_the_flag(self):
        """notice_service.py 의 best-effort 폴백(quota_best_effort_fallback)도 검토 대상이다."""
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": "안녕하세요"},
            {"validation_failure_reason": "quota_best_effort_fallback"},
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "quota_best_effort_fallback")

    def test_admin_review_required_is_also_honoured(self):
        """지금은 orchestrator 가 항상 False 를 넣지만, 살아나면 자동으로 큐에 오른다."""
        needs, reason = _needs_review_from_pipeline(
            {
                "final_translation": "안녕하세요",
                "admin_review": {"required": True, "reason": "manual_hold"},
            },
            {"validation_failure_reason": None},
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "manual_hold")

    def test_reason_is_truncated(self):
        """last_error 가 1000자로 잘리는 것(job_queue_service.py)과 같은 상한."""
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": "x"},
            {"validation_failure_reason": "가" * 2000},
        )
        self.assertTrue(needs)
        self.assertEqual(len(reason), 1000)

    def test_no_translation_means_no_review_queue_entry(self):
        """번역문 자체가 없으면 저장 경로를 타지 않는다 — 검토 큐가 아니라 실패다."""
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": None},
            {"validation_failure_reason": "whatever"},
        )
        self.assertFalse(needs)
        self.assertIsNone(reason)


class _RecordingTable:
    """notice_ai_translations 하나만 흉내내는 최소 페이크.

    첫 upsert 는 needs_review/review_reason 컬럼이 없는 운영 스키마를 흉내내
    PGRST204 로 거부하고, 재시도(해당 두 키를 뺀 payload)는 성공시킨다.
    """

    def __init__(self):
        self.calls: list[dict] = []

    def table(self, name):
        assert name == "notice_ai_translations"
        return self

    def upsert(self, payload, on_conflict=None):
        self.calls.append(dict(payload))
        self._last_payload = payload
        return self

    def execute(self):
        if len(self.calls) == 1:
            raise APIError(
                {
                    "message": "Could not find the 'needs_review' column of "
                    "'notice_ai_translations' in the schema cache",
                    "code": "PGRST204",
                    "hint": None,
                    "details": None,
                }
            )
        return _FakeResult([self._last_payload])


class _FakeResult:
    def __init__(self, data):
        self.data = data


class UpsertTranslationRowColumnMissingTest(unittest.TestCase):
    def test_falls_back_and_still_saves_translation_when_review_columns_missing(self):
        """🔴 0041 미적용 운영(needs_review/review_reason 컬럼 없음)을 흉내낸다.

        번역 저장(translated_text/validation_status)은 컬럼 부재와 무관하게
        성공해야 한다 — 크롤·번역이 지금도 돌고 있다."""
        from app.services.notice_service import _upsert_translation_row

        supabase = _RecordingTable()
        row = {
            "notice_id": "notice-1",
            "target_language": "vi",
            "translated_text": "Xin chào",
            "validation_status": "passed",
            "needs_review": True,
            "review_reason": "hard_fact_validation_failed",
        }

        result = _upsert_translation_row(
            supabase=supabase,
            row=row,
            notice_id="notice-1",
            target_language="vi",
        )

        self.assertEqual(len(supabase.calls), 2)
        # 첫 시도는 원본 그대로(신호 포함)였다.
        self.assertIn("needs_review", supabase.calls[0])
        # 재시도는 두 컬럼을 뺐다.
        self.assertNotIn("needs_review", supabase.calls[1])
        self.assertNotIn("review_reason", supabase.calls[1])
        # 번역문/검증 상태는 재시도에도 그대로 남아 저장이 성공했다.
        self.assertEqual(supabase.calls[1]["translated_text"], "Xin chào")
        self.assertEqual(supabase.calls[1]["validation_status"], "passed")
        self.assertEqual(result.data[0]["translated_text"], "Xin chào")

    def test_unrelated_api_error_is_not_swallowed(self):
        """PGRST204 라도 needs_review/review_reason 과 무관한 컬럼 문제면 그대로 전파한다."""
        from app.services.notice_service import _upsert_translation_row

        class _AlwaysFailingTable:
            def table(self, name):
                return self

            def upsert(self, payload, on_conflict=None):
                return self

            def execute(self):
                raise APIError(
                    {
                        "message": "Could not find the 'translated_text' column of "
                        "'notice_ai_translations' in the schema cache",
                        "code": "PGRST204",
                        "hint": None,
                        "details": None,
                    }
                )

        with self.assertRaises(APIError):
            _upsert_translation_row(
                supabase=_AlwaysFailingTable(),
                row={"notice_id": "notice-1", "target_language": "vi"},
                notice_id="notice-1",
                target_language="vi",
            )


if __name__ == "__main__":
    unittest.main()
