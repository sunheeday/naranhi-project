"""429 백오프가 한 벌만 존재하는지. 두 벌이 되면 한쪽만 고치는 사고가 난다.

extractor 는 app 을 임포트하지 않는 단방향 경계이므로, 공용 함수는 extractor 쪽에
두고 app 이 재임포트한다. 방향이 뒤집혀도 extractor 는 여전히 app 을 모른다.
"""
import unittest


class QuotaBackoffSingleImplementationTest(unittest.TestCase):
    def test_extractor_owns_the_implementation(self) -> None:
        from extractor.gemini_backoff import (
            QUOTA_BACKOFF_DELAYS_SECONDS,
            call_with_quota_backoff,
            is_quota_exhausted_error,
        )

        self.assertEqual(QUOTA_BACKOFF_DELAYS_SECONDS, (5.0, 10.0, 20.0, 40.0))
        self.assertTrue(callable(call_with_quota_backoff))
        self.assertTrue(callable(is_quota_exhausted_error))

    def test_translation_reexports_the_same_objects(self) -> None:
        from app.translation import gemini_client
        from extractor import gemini_backoff

        self.assertIs(gemini_client.call_with_quota_backoff, gemini_backoff.call_with_quota_backoff)
        self.assertIs(gemini_client.is_quota_exhausted_error, gemini_backoff.is_quota_exhausted_error)

    def test_extractor_does_not_import_app(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "extractor" / "gemini_backoff.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from app.", source)
        self.assertNotIn("import app", source)


class DocumentExtractorUsesSharedBackoffTest(unittest.TestCase):
    def test_vertex_paths_call_the_shared_helper(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "extractor"
            / "extractors"
            / "gemini_document_extractor.py"
        ).read_text(encoding="utf-8")

        self.assertIn("from extractor.gemini_backoff import", source)
        # Vertex 경로 둘(_generate_content_vertex, _generate_text_vertex) 다 공용 백오프를 탄다.
        self.assertEqual(source.count("await call_with_quota_backoff("), 2)
        # 429 를 짧은 2**attempt 재시도로 다시 돌리면 긴 백오프가 3배로 겹친다.
        # retryable_tokens 에서 문자열 토큰이 사라져야 한다(18행의 HTTP 상태코드 집합은 별개).
        self.assertEqual(source.count('"429"'), 0)
        self.assertEqual(source.count('"resource_exhausted"'), 0)


if __name__ == "__main__":
    unittest.main()
