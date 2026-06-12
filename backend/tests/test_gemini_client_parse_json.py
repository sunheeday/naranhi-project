import json
import unittest

from app.crawler.gemini_finder import _parse_json as finder_parse_json
from app.crawler.unknown_post_resolver import _parse_json as resolver_parse_json
from app.translation.gemini_client import _parse_json, _repair_invalid_json_escapes


class GeminiClientParseJsonTest(unittest.TestCase):
    def test_valid_json_returns_dict(self):
        self.assertEqual(_parse_json('{"a": 1}'), {"a": 1})

    def test_json_wrapped_in_markdown_fence_is_extracted(self):
        text = '```json\n{"title": "안내"}\n```'
        self.assertEqual(_parse_json(text), {"title": "안내"})

    def test_invalid_backslash_escape_is_repaired(self):
        # 실제 장애 재현: Gemini가 문자열 안에 잘못된 \escape를 섞어 보낸 경우
        # (정기시험 공지 vi 번역에서 JSONDecodeError: Invalid \escape 발생)
        text = '{"title": "수정테이프 \\m 사용 또는 두 줄 긋기"}'
        parsed = _parse_json(text)
        self.assertEqual(parsed["title"], "수정테이프 \\m 사용 또는 두 줄 긋기")

    def test_valid_escapes_survive_repair(self):
        # 잘못된 \m 때문에 복구 경로를 타더라도, 유효한 이스케이프
        # (\n, \", \\, \uXXXX)는 깨지지 않고 보존돼야 한다.
        text = 'noise {"a": "line1\\nline2 \\"q\\" \\\\ x \\uD55C", "bad": "\\m"} noise'
        parsed = _parse_json(text)
        self.assertEqual(parsed["a"], 'line1\nline2 "q" \\ x 한')
        self.assertEqual(parsed["bad"], "\\m")

    def test_literal_control_character_parsed_with_strict_false(self):
        # 문자열 값 안에 리터럴 개행이 들어온 경우 (strict 모드에선 실패)
        text = 'reply: {"a": "line1\nline2"}'
        self.assertEqual(_parse_json(text), {"a": "line1\nline2"})

    def test_non_dict_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            _parse_json("[1, 2, 3]")

    def test_no_json_raises_decode_error(self):
        with self.assertRaises(json.JSONDecodeError):
            _parse_json("JSON 없이 텍스트만 있는 응답")


class RepairInvalidJsonEscapesTest(unittest.TestCase):
    def test_invalid_escape_becomes_literal_backslash(self):
        self.assertEqual(_repair_invalid_json_escapes('"\\m"'), '"\\\\m"')

    def test_valid_pairs_are_preserved(self):
        value = '"\\n \\" \\\\ \\/ \\t \\uD55C"'
        self.assertEqual(_repair_invalid_json_escapes(value), value)

    def test_double_backslash_before_normal_char_is_not_corrupted(self):
        # \\ 뒤에 일반 문자가 와도 쌍 단위로 소비되어 보존된다 (옛 정규식의 결함 케이스)
        value = '"a \\\\ b"'
        self.assertEqual(_repair_invalid_json_escapes(value), value)

    def test_unicode_escape_without_hex_digits_is_repaired(self):
        # \u 뒤에 16진수 4자리가 아니면 유효하지 않으므로 리터럴로 교정
        self.assertEqual(_repair_invalid_json_escapes('"\\under"'), '"\\\\under"')

    def test_trailing_backslash_is_repaired(self):
        self.assertEqual(_repair_invalid_json_escapes('"x\\'), '"x\\\\')


class CrawlerParseJsonVariantsTest(unittest.TestCase):
    def test_finder_repairs_invalid_escape(self):
        text = '{"path": "C:\\my\\docs"}'
        self.assertEqual(finder_parse_json(text), {"path": "C:\\my\\docs"})

    def test_finder_raises_when_no_json(self):
        with self.assertRaises(json.JSONDecodeError):
            finder_parse_json("no json here")

    def test_resolver_repairs_invalid_escape(self):
        text = '{"kind": "family\\xnotice"}'
        self.assertEqual(resolver_parse_json(text), {"kind": "family\\xnotice"})

    def test_resolver_returns_empty_dict_when_no_json(self):
        self.assertEqual(resolver_parse_json("no json here"), {})


if __name__ == "__main__":
    unittest.main()
