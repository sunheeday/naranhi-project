import unittest

from app.translation.gemini_client import (
    call_with_quota_backoff,
    is_quota_exhausted_error,
)


class IsQuotaExhaustedErrorTest(unittest.TestCase):
    def test_detects_429_client_error_message(self) -> None:
        error = RuntimeError(
            "ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, "
            "'message': 'Resource exhausted. Please try again later.'}}"
        )
        self.assertTrue(is_quota_exhausted_error(error))

    def test_detects_resource_exhausted_without_status_code(self) -> None:
        self.assertTrue(is_quota_exhausted_error(RuntimeError("RESOURCE_EXHAUSTED")))

    def test_detects_quota_keyword(self) -> None:
        self.assertTrue(is_quota_exhausted_error(RuntimeError("Quota exceeded for model")))

    def test_ignores_unrelated_errors(self) -> None:
        self.assertFalse(is_quota_exhausted_error(ValueError("invalid json")))
        self.assertFalse(is_quota_exhausted_error(RuntimeError("500 internal error")))


class CallWithQuotaBackoffTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_result_on_first_success(self) -> None:
        calls = []

        async def factory():
            calls.append(1)
            return {"ok": True}

        result = await call_with_quota_backoff(factory, delays_seconds=(0.0, 0.0))

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 1)

    async def test_retries_quota_error_then_succeeds(self) -> None:
        attempts = []

        async def factory():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return "done"

        result = await call_with_quota_backoff(factory, delays_seconds=(0.0, 0.0, 0.0))

        self.assertEqual(result, "done")
        self.assertEqual(len(attempts), 3)

    async def test_raises_non_quota_error_immediately(self) -> None:
        attempts = []

        async def factory():
            attempts.append(1)
            raise ValueError("invalid json")

        with self.assertRaises(ValueError):
            await call_with_quota_backoff(factory, delays_seconds=(0.0, 0.0))

        self.assertEqual(len(attempts), 1)

    async def test_raises_quota_error_after_exhausting_retries(self) -> None:
        attempts = []

        async def factory():
            attempts.append(1)
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

        with self.assertRaises(RuntimeError):
            await call_with_quota_backoff(factory, delays_seconds=(0.0, 0.0))

        # 대기 목록 2개 + 마지막 1회 = 총 3회 시도 후 원본 예외 전파.
        self.assertEqual(len(attempts), 3)


if __name__ == "__main__":
    unittest.main()
