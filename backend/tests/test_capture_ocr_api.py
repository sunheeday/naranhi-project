import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.capture import get_capture_ocr_service, get_notice_service
from app.main import app
from app.services.capture_ocr_service import CaptureOcrResult


class FakeCaptureOcrService:
    def __init__(self) -> None:
        self.extract_text = AsyncMock(
            return_value=CaptureOcrResult(
                extracted_text="학교 가정통신문\n준비물: 실내화",
                mime_type="image/png",
                confidence=0.91,
                is_readable=True,
                detected_layout="photo_notice",
            )
        )


class FakeNoticeService:
    def __init__(self) -> None:
        self.translate_text = AsyncMock(
            return_value={
                "ok": True,
                "target_language": "en",
                "status": "ready_to_save",
                "translation": "School notice\nSupplies: indoor shoes",
            }
        )


class CaptureOcrApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ocr_service = FakeCaptureOcrService()
        self.notice_service = FakeNoticeService()
        app.dependency_overrides[get_capture_ocr_service] = lambda: self.ocr_service
        app.dependency_overrides[get_notice_service] = lambda: self.notice_service
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_extracts_text_from_raw_image_bytes(self):
        response = self.client.post(
            "/capture/ocr",
            content=b"fake-image",
            headers={"content-type": "image/png"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["extracted_text"], "학교 가정통신문\n준비물: 실내화")
        self.assertEqual(body["mime_type"], "image/png")
        self.assertEqual(body["ocr"]["detected_layout"], "photo_notice")
        self.ocr_service.extract_text.assert_awaited_once()
        self.notice_service.translate_text.assert_not_awaited()

    def test_extracts_text_from_upload_and_optionally_translates(self):
        response = self.client.post(
            "/capture/ocr?target_language=en",
            files={"file": ("notice.png", b"fake-image", "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["translation"]["translation"], "School notice\nSupplies: indoor shoes")
        self.ocr_service.extract_text.assert_awaited_once()
        self.notice_service.translate_text.assert_awaited_once_with(
            source_text="학교 가정통신문\n준비물: 실내화",
            target_language="en",
        )

    def test_rejects_ocr_validation_errors(self):
        self.ocr_service.extract_text = AsyncMock(side_effect=ValueError("Image payload is empty."))

        response = self.client.post(
            "/capture/ocr",
            content=b"",
            headers={"content-type": "image/png"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Image payload is empty.")


if __name__ == "__main__":
    unittest.main()
