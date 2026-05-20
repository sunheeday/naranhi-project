from typing import Any


class NoticeService:
    async def create_notice(self, payload: dict[str, Any]) -> dict[str, object]:
        raise RuntimeError("Manual notice creation is disabled. Notices are school-crawled only.")

    async def analyze_notice(self, notice_id: str, target_language: str) -> dict[str, object]:
        # Placeholder for OCR, AI extraction, translation, and calendar sync pipeline.
        return {
            "ok": True,
            "notice_id": notice_id,
            "target_language": target_language,
            "status": "queued",
        }


def get_notice_service() -> NoticeService:
    return NoticeService()
