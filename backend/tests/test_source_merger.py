from __future__ import annotations

import unittest

from extractor.models import SourceExtraction
from extractor.source_merger import _best_source, assign_roles_and_dedupe


def make_source(source_id: str, source_type: str, raw_text: str, fingerprint: str = "") -> SourceExtraction:
    return SourceExtraction(
        source_id=source_id,
        source_type=source_type,
        source_role="unknown",
        origin_url="",
        filename="",
        file_hash="",
        text_fingerprint=fingerprint,
        duplicate_of=None,
        extraction_method="test",
        status="success",
        raw_text=raw_text,
    )


class BodyPriorityTests(unittest.TestCase):
    def test_best_source_prefers_body_when_equivalent_length(self) -> None:
        # 본문과 첨부가 사실상 동등(둘 다 near_longest) → 본문 우선.
        body = make_source("body", "html_body", "가" * 100)
        hwp = make_source("att", "attachment_hwp", "가" * 100)
        self.assertEqual(_best_source([hwp, body]).source_id, "body")

    def test_best_source_prefers_attachment_when_body_is_stub(self) -> None:
        # 본문이 stub(첨부의 90% 미만) → 첨부 우선(내용 손실 방지).
        body = make_source("body", "html_body", "가" * 30)
        hwp = make_source("att", "attachment_hwp", "가" * 100)
        self.assertEqual(_best_source([hwp, body]).source_id, "att")

    def test_dedupe_keeps_body_as_primary_for_equivalent_attachment(self) -> None:
        # 같은 내용(지문 동일)의 본문+첨부 → 본문이 primary, 첨부는 duplicate.
        text = "가정통신문 동일 내용 " * 30
        body = make_source("body", "html_body", text, fingerprint="same-fp")
        hwp = make_source("att", "attachment_hwp", text, fingerprint="same-fp")
        sources, included = assign_roles_and_dedupe([hwp, body])
        self.assertEqual(included, ["body"])
        self.assertEqual(body.source_role, "primary")
        self.assertEqual(hwp.source_role, "duplicate")
        self.assertEqual(hwp.duplicate_of, "body")


if __name__ == "__main__":
    unittest.main()
