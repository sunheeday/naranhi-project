from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.services.content_extraction_service import ContentExtractionService
from app.services.school_crawler_service import (
    SchoolCrawlerService,
    get_school_crawler_service,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


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
    background_tasks: BackgroundTasks,
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

    extraction_queued = result.status == "success" and result.success_count > 0
    if extraction_queued:
        background_tasks.add_task(
            _extract_initial_school_notices,
            school_id,
            result.success_count,
        )

    return {
        "ok": True,
        "result": result.to_api_dict(),
        "extraction": {
            "queued": extraction_queued,
            "max_notices": result.success_count if extraction_queued else 0,
        },
    }


async def _extract_initial_school_notices(school_id: str, max_notices: int) -> None:
    try:
        summary = await ContentExtractionService().run_for_school(
            school_id,
            max_notices=max_notices,
        )
        if summary.error_count:
            # Extraction failures are already persisted per notice. This log is only
            # for operational visibility; the crawler result itself remains success.
            LOGGER.warning(
                "Initial content extraction completed with errors: school_id=%s processed=%s success=%s error=%s",
                school_id,
                summary.processed_count,
                summary.success_count,
                summary.error_count,
            )
    except Exception:  # noqa: BLE001 - background task must not affect crawler response.
        LOGGER.exception(
            "Initial content extraction failed: school_id=%s",
            school_id,
        )
