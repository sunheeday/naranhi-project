import unittest

from app.translation.orchestrator import _validation_status


class TranslationOrchestratorTest(unittest.TestCase):
    def test_validation_status_preserves_skipped(self):
        self.assertEqual(
            _validation_status({"status": "skipped", "issues": []}),
            "skipped",
        )

    def test_validation_status_uses_verdict_when_status_missing(self):
        self.assertEqual(_validation_status({"verdict": "PASS"}), "passed")
        self.assertEqual(_validation_status({"verdict": "FAIL"}), "failed")


if __name__ == "__main__":
    unittest.main()
