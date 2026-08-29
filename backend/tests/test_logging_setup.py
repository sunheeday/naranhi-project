import json
import logging
import unittest

from app.core.logging_setup import CloudLoggingFormatter, setup_logging


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="naranhi.test",
        level=logging.WARNING,
        pathname="x.py",
        lineno=10,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class CloudLoggingFormatterTest(unittest.TestCase):
    def test_emits_single_json_line_with_severity(self):
        """Cloud Logging 은 stdout 한 줄을 하나의 로그로 읽는다.
        줄바꿈이 섞이면 한 사건이 여러 엔트리로 쪼개진다."""
        output = CloudLoggingFormatter().format(_record())
        self.assertNotIn("\n", output)
        payload = json.loads(output)
        self.assertEqual(payload["severity"], "WARNING")
        self.assertEqual(payload["message"], "hello world")
        self.assertEqual(payload["logger"], "naranhi.test")

    def test_job_type_and_extra_fields_are_included(self):
        """extra= 로 붙인 필드가 구조화 필드로 나가야 로그 기반 지표를 걸 수 있다."""
        payload = json.loads(
            CloudLoggingFormatter(job_type="school_crawl").format(_record(school_id="s-1"))
        )
        self.assertEqual(payload["job_type"], "school_crawl")
        self.assertEqual(payload["school_id"], "s-1")

    def test_exception_is_flattened_into_one_line(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _record()
            record.exc_info = sys.exc_info()
        output = CloudLoggingFormatter().format(record)
        self.assertNotIn("\n", output)
        payload = json.loads(output)
        self.assertIn("ValueError: boom", payload["exception"])

    def test_secret_in_exception_is_redacted(self):
        """사업 C 의 sanitize_error 를 재사용한다 — 실패 로그에도 열쇠가 남으면 안 된다."""
        import os
        import sys

        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "super-secret-key-value"
        try:
            try:
                raise RuntimeError("upstream said: super-secret-key-value")
            except RuntimeError:
                record = _record()
                record.exc_info = sys.exc_info()
            payload = json.loads(CloudLoggingFormatter().format(record))
            self.assertNotIn("super-secret-key-value", payload["exception"])
            self.assertIn("[REDACTED]", payload["exception"])
        finally:
            del os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    def test_secret_in_message_is_redacted(self):
        import os

        os.environ["GEMINI_API_KEY"] = "abc-secret-token"
        try:
            record = _record()
            record.msg = "call failed: %s"
            record.args = ("token=abc-secret-token",)
            payload = json.loads(CloudLoggingFormatter().format(record))
            self.assertNotIn("abc-secret-token", payload["message"])
        finally:
            del os.environ["GEMINI_API_KEY"]

    def test_format_never_raises_on_unrepresentable_extra_value(self):
        """로깅이 실패해도 잡을 죽이면 안 된다 — format() 은 예외 대신 안전한 결과를 낸다."""

        class Explodes:
            def __repr__(self):
                raise RuntimeError("cannot repr")

        record = _record(bad_field=Explodes())
        output = CloudLoggingFormatter().format(record)  # must not raise
        self.assertNotIn("\n", output)
        payload = json.loads(output)
        self.assertEqual(payload["message"], "hello world")


class SetupLoggingTest(unittest.TestCase):
    def tearDown(self):
        logging.getLogger().handlers.clear()
        logging.getLogger().setLevel(logging.WARNING)

    def test_installs_json_formatter_with_job_type(self):
        setup_logging(job_type="probe_job", level="DEBUG")
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        formatter = root.handlers[0].formatter
        self.assertIsInstance(formatter, CloudLoggingFormatter)
        self.assertEqual(root.level, logging.DEBUG)

    def test_invalid_level_falls_back_to_info_without_raising(self):
        setup_logging(job_type="probe_job", level="not-a-real-level")
        self.assertEqual(logging.getLogger().level, logging.INFO)


if __name__ == "__main__":
    unittest.main()
