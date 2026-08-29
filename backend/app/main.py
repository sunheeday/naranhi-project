from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.capture import router as capture_router
from app.api.crawler import router as crawler_router
from app.api.health import router as health_router
from app.api.notices import router as notices_router
from app.core.config import get_settings
from app.core.logging_setup import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(job_type="api", level=settings.log_level)

    app = FastAPI(
        title="Naranhi API",
        version="0.1.0",
        description="Notice collection, document analysis, translation, and external API integration service.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(notices_router, prefix="/notices", tags=["notices"])
    app.include_router(crawler_router, prefix="/crawler", tags=["crawler"])
    app.include_router(capture_router, prefix="/capture", tags=["capture"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    return app


app = create_app()
