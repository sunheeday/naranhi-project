from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.services.school_crawler_service import (
    SchoolCrawlerService,
    get_school_crawler_service,
)

router = APIRouter()


def _require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    settings = get_settings()
    expected = (settings.crawler_internal_token or "").strip()

    if not expected:
        if settings.environment.lower() == "local":
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CRAWLER_INTERNAL_TOKEN is required outside local environment.",
        )

    provided = (x_internal_token or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid crawler internal token.",
        )


@router.post(
    "/schools/{school_id}/discover-board",
    dependencies=[Depends(_require_internal_token)],
)
async def discover_school_board(
    school_id: str,
    service: SchoolCrawlerService = Depends(get_school_crawler_service),
) -> dict[str, object]:
    try:
        result = await service.discover_and_save_school_board(school_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if result.status == "school_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School row was not found.",
        )

    return {"ok": True, "result": result.to_api_dict()}
