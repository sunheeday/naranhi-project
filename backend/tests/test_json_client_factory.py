import unittest

from app.core.config import Settings
from app.translation.gemini_client import GeminiJsonClient
from app.translation.json_client import JsonModelClient, build_json_client


class BuildJsonClientTest(unittest.TestCase):
    def test_default_backend_is_gemini(self) -> None:
        """기본값은 gemini 다 — 이 커밋의 런타임 동작 변화는 0이어야 한다."""
        settings = Settings(VERTEX_AI_PROJECT_ID="probe-only")
        self.assertEqual(settings.translation_backend, "gemini")
        client = build_json_client(settings)
        self.assertIsInstance(client, GeminiJsonClient)

    def test_unknown_backend_falls_back_to_gemini(self) -> None:
        """오타 난 env 로 번역이 멈추면 안 된다. 경고만 남기고 Gemini 로 간다."""
        settings = Settings(VERTEX_AI_PROJECT_ID="probe-only", TRANSLATION_BACKEND="oops")
        self.assertIsInstance(build_json_client(settings), GeminiJsonClient)

    def test_gemini_client_satisfies_the_protocol(self) -> None:
        """GeminiJsonClient 는 한 글자도 고치지 않고 프로토콜을 만족해야 한다."""
        client = GeminiJsonClient(model="gemini-2.5-flash", api_key="unused")
        self.assertIsInstance(client, JsonModelClient)

    def test_bedrock_default_model_is_haiku(self) -> None:
        """기본은 Haiku 다(스펙 §5.10.1). Sonnet 승급은 env 로만 한다."""
        settings = Settings()
        self.assertEqual(settings.bedrock_region, "ap-northeast-2")
        self.assertEqual(
            settings.bedrock_translation_model,
            "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        )
        self.assertIsNone(settings.bedrock_mechanical_model)

    def test_forbidden_models_are_not_defaults(self) -> None:
        """Opus 는 금지(비용), Nova 는 한국어 본문 생성 경로에서 제외(환각).

        기본값에 이 둘이 들어가면 아무도 모르게 운영에 실린다.
        """
        settings = Settings()
        for name in (settings.bedrock_translation_model, settings.bedrock_mechanical_model or ""):
            self.assertNotIn("opus", name)
            self.assertNotIn("nova", name)


if __name__ == "__main__":
    unittest.main()
