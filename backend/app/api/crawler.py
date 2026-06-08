from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.job_queue_service import JobQueueService
from app.services.school_crawler_service import _fetch_school_row

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
) -> dict[str, object]:
    _preflight_school_discovery(school_id)
    enqueue = JobQueueService().enqueue(
        job_type="school_board_discovery",
        job_key=f"school-discovery:{school_id}",
        payload={"school_id": school_id, "max_posts": get_settings().crawler_initial_notice_count},
        max_attempts=5,
    )
    return JSONResponse(
        {
            "ok": True,
            "accepted": True,
            "already_running": enqueue.already_running,
            "job_id": enqueue.job_id,
            "school_id": school_id,
        },
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.post(
    "/schools/{school_id}/extract-pending",
    dependencies=[Depends(_require_internal_token)],
)
async def extract_pending_school_notices(
    school_id: str,
    max_notices: int | None = Query(default=None, ge=1, le=50),
) -> dict[str, object]:
    _preflight_school_discovery(school_id)
    notice_limit = max_notices or get_settings().extractor_max_notices_per_run
    enqueue = JobQueueService().enqueue(
        job_type="school_notice_extraction",
        job_key=f"school-extraction:{school_id}",
        payload={"school_id": school_id, "max_notices": notice_limit},
        max_attempts=5,
    )
    return JSONResponse(
        {
            "ok": True,
            "accepted": True,
            "already_running": enqueue.already_running,
            "job_id": enqueue.job_id,
            "extraction": {
                "queued": True,
                "max_notices": notice_limit,
            },
        },
        status_code=status.HTTP_202_ACCEPTED,
    )


def _preflight_school_discovery(school_id: str) -> None:
    settings = get_settings()
    if not settings.supabase_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured.",
        )

    try:
        school_row = _fetch_school_row(school_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if not school_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School row was not found.",
        )
