from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, object]:
    settings = get_settings()

    return {
        "ok": True,
        "service": "naranhi-api",
        "supabase_configured": settings.supabase_configured,
        "ai_configured": settings.ai_configured,
    }
