from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from extractor.extractors.hwp_extractor import _hwp_to_markdown


class HwpMarkdownFallbackTests(unittest.TestCase):
    def test_skips_gracefully_when_hwp5html_unavailable(self) -> None:
        # hwp5html(콘솔 스크립트)이 없으면 빈 문자열 -> 호출부가 기존 OLE 체인으로 폴백한다.
        with patch("extractor.extractors.hwp_extractor._hwp5html_command", return_value=None):
            out = _hwp_to_markdown(Path("does-not-exist.hwp"), [])
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
