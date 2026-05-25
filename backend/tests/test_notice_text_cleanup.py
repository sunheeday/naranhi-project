from __future__ import annotations

import unittest

from extractor.attachment_finder import find_attachments
from extractor.html_text_extractor import extract_html_text
from extractor.models import SourceExtraction
from extractor.notice_structurer import combined_raw_text


class NoticeTextCleanupTests(unittest.TestCase):
    def test_combined_raw_text_omits_debug_labels(self) -> None:
        text = combined_raw_text(
            [
                SourceExtraction(
                    source_id="html_body_1",
                    source_type="html_body",
                    source_role="primary",
                    origin_url="https://example.edu",
                    filename="",
                    file_hash="",
                    text_fingerprint="fp-1",
                    duplicate_of=None,
                    extraction_method="html",
                    status="success",
                    raw_text="본문입니다",
                )
            ],
            ["html_body_1"],
        )

        self.assertEqual(text, "본문입니다")
        self.assertNotIn("[html_body_1 html_body]", text)

    def test_combined_raw_text_skips_short_html_metadata_when_attachment_exists(self) -> None:
        text = combined_raw_text(
            [
                SourceExtraction(
                    source_id="attachment_hwp_1",
                    source_type="attachment_hwp",
                    source_role="primary",
                    origin_url="https://example.edu/file.hwp",
                    filename="file.hwp",
                    file_hash="",
                    text_fingerprint="fp-1",
                    duplicate_of=None,
                    extraction_method="hwp",
                    status="success",
                    raw_text="실제 첨부 본문입니다.",
                ),
                SourceExtraction(
                    source_id="html_body_1",
                    source_type="html_body",
                    source_role="primary",
                    origin_url="https://example.edu",
                    filename="",
                    file_hash="",
                    text_fingerprint="fp-2",
                    duplicate_of=None,
                    extraction_method="html",
                    status="success",
                    raw_text="공지 제목\n작성자\n홍길동\n등록일\n2026.05.20\n조회수\n51",
                ),
            ],
            ["attachment_hwp_1", "html_body_1"],
        )

        self.assertEqual(text, "실제 첨부 본문입니다.")

    def test_extract_html_text_drops_attachment_ui_lines(self) -> None:
        html = """
        <div class="board_view">
          <p>가정통신문 본문</p>
          <p>첨부파일</p>
          <p>첨부파일 미리보기</p>
          <p>미리보기</p>
          <p>바로듣기</p>
        </div>
        """

        text = extract_html_text(html)

        self.assertIn("가정통신문 본문", text)
        self.assertNotIn("첨부파일 미리보기", text)
        self.assertNotIn("바로듣기", text)

    def test_find_attachments_reads_dext5_single_quoted_uploads(self) -> None:
        html = """
        <script>
        DEXT5UPLOAD.AddUploadedFile(
          'ae1794',
          '안내문.hwp',
          '/upload/school/notice.hwp',
          '86528',
          'ae1794',
          G_UploadID
        );
        </script>
        """

        refs = find_attachments("https://school.example.edu/notice", html)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].filename, "안내문.hwp")
        self.assertEqual(refs[0].url, "https://school.example.edu/upload/school/notice.hwp")


if __name__ == "__main__":
    unittest.main()
