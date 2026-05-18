from __future__ import annotations

import unittest

from extractor.extractors.hwp_extractor import _decode_para_text_body, _hwp_header_flags


class HwpExtractorTests(unittest.TestCase):
    def test_decodes_para_text_while_skipping_extended_control_payload(self) -> None:
        body = (
            "가".encode("utf-16le")
            + (0x09).to_bytes(2, "little")
            + b"\x01\x02\x03\x04\x05\x06"
            + "나".encode("utf-16le")
        )

        self.assertEqual(_decode_para_text_body(body), "가\t나")

    def test_hwp_header_flags(self) -> None:
        header = bytearray(40)
        header[36:40] = (0b10111).to_bytes(4, "little")

        flags = _hwp_header_flags(bytes(header))

        self.assertTrue(flags["compressed"])
        self.assertTrue(flags["password"])
        self.assertTrue(flags["distribution"])
        self.assertFalse(flags["script"])
        self.assertTrue(flags["drm"])


if __name__ == "__main__":
    unittest.main()
