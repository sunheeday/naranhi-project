from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client


class NoticeService:
    async def create_notice(self, payload: dict[str, Any]) -> dict[str, object]:
        settings = get_settings()

        if not settings.supabase_configured:
            raise RuntimeError("Supabase is not configured.")

        supabase = get_supabase_client()
        result = (
            supabase.table("notices")
            .insert(
                {
                    "title": payload["title"],
                    "original_text": payload.get("raw_text"),
                    "child_id": payload.get("child_id"),
                    "school_id": payload.get("school_id"),
                    "source": "manual",
                    "status": "pending",
                }
            )
            .execute()
        )

        data = result.data[0] if result.data else None

        return {"ok": True, "notice": data}

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
