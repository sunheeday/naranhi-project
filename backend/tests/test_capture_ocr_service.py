import unittest
from unittest.mock import AsyncMock

from app.services.capture_ocr_service import CaptureOcrResult, CaptureOcrService


class CaptureOcrServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_validates_image_payload_and_delegates_to_provider(self):
        provider = AsyncMock()
        provider.extract_bytes.return_value = CaptureOcrResult(
            extracted_text="공지",
            mime_type="image/jpeg",
            is_readable=True,
        )
        service = CaptureOcrService(provider=provider)

        result = await service.extract_text(
            data=b"fake-image",
            mime_type="image/jpeg; charset=binary",
            source_name="notice.jpg",
        )

        self.assertEqual(result.extracted_text, "공지")
        provider.extract_bytes.assert_awaited_once_with(
            b"fake-image",
            mime_type="image/jpeg",
            source_name="notice.jpg",
        )

    async def test_rejects_unsupported_mime_type(self):
        service = CaptureOcrService(provider=AsyncMock())

        with self.assertRaisesRegex(ValueError, "Unsupported image content type"):
            await service.extract_text(
                data=b"not-an-image",
                mime_type="application/pdf",
            )

    async def test_infers_image_mime_type_from_filename_when_upload_type_is_generic(self):
        provider = AsyncMock()
        provider.extract_bytes.return_value = CaptureOcrResult(
            extracted_text="공지",
            mime_type="image/jpeg",
            is_readable=True,
        )
        service = CaptureOcrService(provider=provider)

        await service.extract_text(
            data=b"fake-image",
            mime_type="application/octet-stream",
            source_name="notice.jpg",
        )

        provider.extract_bytes.assert_awaited_once_with(
            b"fake-image",
            mime_type="image/jpeg",
            source_name="notice.jpg",
        )


if __name__ == "__main__":
    unittest.main()
