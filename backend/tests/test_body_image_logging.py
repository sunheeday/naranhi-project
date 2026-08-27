"""본문 사진 합성·업로드가 한 줄 로그를 남기는지. 진단(Task 9)의 유일한 관측 수단이다."""
import unittest
from unittest.mock import patch

from app.services.content_extraction_service import _combine_and_upload_body_images


class BodyImageLoggingTest(unittest.IsolatedAsyncioTestCase):
    async def test_logs_counts_when_stitch_fails(self) -> None:
        """PIL 이 한 장도 못 열면 stitched=0 upload=skip 이 남아야 한다."""
        images = [("inline_image_1", b"not-an-image")]
        with self.assertLogs("app.services.content_extraction_service", level="INFO") as logs:
            url = await _combine_and_upload_body_images("notice-1", images)
        self.assertEqual(url, "")
        self.assertTrue(any("body images:" in line and "collected=1" in line for line in logs.output))
        self.assertTrue(any("stitched=0" in line for line in logs.output))

    async def test_logs_upload_result_when_stitch_succeeds(self) -> None:
        def _fake_stitch(images: list[bytes]) -> bytes:
            return b"stitched-png-bytes"

        async def _fake_upload(**kwargs: object) -> None:
            return None  # 업로드 실패

        with patch(
            "app.services.content_extraction_service._stitch_images_vertically", _fake_stitch
        ), patch("app.services.attachment_storage.upload_bytes", _fake_upload):
            with self.assertLogs("app.services.content_extraction_service", level="INFO") as logs:
                url = await _combine_and_upload_body_images("notice-2", [("inline_image_1", b"x")])

        self.assertEqual(url, "")
        self.assertTrue(any("upload=fail" in line for line in logs.output))

    async def test_no_log_when_there_are_no_inline_images(self) -> None:
        """사진이 애초에 없는 공지는 조용해야 한다 — 로그가 잡음이 되면 안 된다."""
        with self.assertNoLogs("app.services.content_extraction_service", level="INFO"):
            self.assertEqual(await _combine_and_upload_body_images("notice-3", []), "")


if __name__ == "__main__":
    unittest.main()
