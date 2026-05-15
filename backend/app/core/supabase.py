from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def get_supabase_client():
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase is not configured for the FastAPI service.")

    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_role_key)
