import unittest

from app.services import attachment_storage


class ObjectKeyTest(unittest.TestCase):
    def test_upload_result_has_no_public_url(self):
        """업로드 결과에 public_url 이 있으면 안 된다.

        URL 은 저장하지 않고 읽는 시점에 서명 URL 로 발급한다.
        저장된 URL 은 만료 개념이 없어 '학부모만 열람' 목표와 모순된다.
        """
        result_keys = attachment_storage.UPLOAD_RESULT_KEYS
        self.assertIn("storage_path", result_keys)
        self.assertNotIn("public_url", result_keys)

    def test_bucket_is_private(self):
        """버킷 자동 생성 시 공개로 만들면 안 된다."""
        self.assertFalse(attachment_storage.BUCKET_PUBLIC)


if __name__ == "__main__":
    unittest.main()
