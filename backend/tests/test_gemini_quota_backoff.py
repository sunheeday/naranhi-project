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

    def test_detects_bedrock_throttling_exception(self) -> None:
        """Bedrock 스로틀 메시지에는 429·quota·rate limit 이 하나도 없다.

        그대로 두면 백오프가 한 번도 동작하지 않고 잡이 실패로 직행한다.
        """
        error = RuntimeError(
            "ClientError: An error occurred (ThrottlingException) when calling the "
            "Converse operation: Too many requests, please wait before trying again."
        )
        self.assertTrue(is_quota_exhausted_error(error))

    def test_detects_bedrock_service_unavailable(self) -> None:
        error = RuntimeError(
            "ClientError: An error occurred (ServiceUnavailableException) when calling "
            "the Converse operation: The model is temporarily unavailable."
        )
        self.assertTrue(is_quota_exhausted_error(error))

    def test_detects_bedrock_model_not_ready(self) -> None:
        error = RuntimeError(
            "ClientError: An error occurred (ModelNotReadyException) when calling "
            "the Converse operation: Model is not ready."
        )
        self.assertTrue(is_quota_exhausted_error(error))

    def test_ignores_unrelated_errors(self) -> None:
        self.assertFalse(is_quota_exhausted_error(ValueError("invalid json")))
        self.assertFalse(is_quota_exhausted_error(RuntimeError("500 internal error")))
        # 마커를 넓혔지만 Bedrock 의 비스로틀 예외는 여전히 즉시 전파돼야 한다.
        self.assertFalse(
            is_quota_exhausted_error(
                RuntimeError(
                    "ClientError: An error occurred (ValidationException) when calling "
                    "the Converse operation: Malformed input request."
                )
            )
        )
        self.assertFalse(
            is_quota_exhausted_error(
                RuntimeError(
                    "ClientError: An error occurred (AccessDeniedException) when calling "
                    "the Converse operation."
                )
            )
        )


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
