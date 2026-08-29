from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging_setup import setup_logging
from app.jobs.crawler_worker import process_jobs as process_crawler_jobs
from app.jobs.translation_worker import process_jobs as process_translation_jobs

LOGGER = logging.getLogger(__name__)
SUPPORTED_JOB_GROUPS = {"translation", "crawler"}


def _normalize_job_groups(values: list[str]) -> list[str]:
    normalized = [value.strip().lower() for value in values if value.strip()]
    deduped: list[str] = []
    for value in normalized:
        if value not in SUPPORTED_JOB_GROUPS:
            raise ValueError(f"Unsupported WORKER_JOB_GROUPS value: {value}")
        if value not in deduped:
            deduped.append(value)
    return deduped or ["translation"]


async def _run_worker_group(group: str) -> int:
    settings = get_settings()
    stale_seconds = settings.worker_job_stale_minutes * 60
    if group == "translation":
        return await process_translation_jobs(
            max_jobs=settings.worker_batch_size,
            batch_size=settings.worker_batch_size,
            retry_delay_seconds=settings.worker_retry_delay_seconds,
            stale_seconds=stale_seconds,
        )
    if group == "crawler":
        return await process_crawler_jobs(
            max_jobs=settings.worker_batch_size,
            batch_size=settings.worker_batch_size,
            retry_delay_seconds=settings.worker_retry_delay_seconds,
            stale_seconds=stale_seconds,
        )
    raise RuntimeError(f"Unsupported worker job group: {group}")


async def _worker_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    job_groups = _normalize_job_groups(settings.worker_job_groups)
    poll_interval = max(0.1, float(settings.worker_poll_interval_seconds))
    LOGGER.info(
        "worker service started: groups=%s batch_size=%s poll_interval=%s",
        ",".join(job_groups),
        settings.worker_batch_size,
        poll_interval,
    )

    while not stop_event.is_set():
        processed_total = 0
        for group in job_groups:
            try:
                processed_total += await _run_worker_group(group)
            except Exception:  # noqa: BLE001
                LOGGER.exception("worker service loop failed: group=%s", group)
        if processed_total == 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                continue


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(job_type="worker_service", level=get_settings().log_level)
    stop_event = asyncio.Event()
    task = asyncio.create_task(_worker_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(task, timeout=25.0)
        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    app = FastAPI(
        title="Naranhi Worker",
        version="0.1.0",
        description="Long-running worker service for queued crawler and translation jobs.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        settings = get_settings()
        return {
            "ok": True,
            "service": "naranhi-worker",
            "job_groups": _normalize_job_groups(settings.worker_job_groups),
            "supabase_configured": settings.supabase_configured,
            "ai_configured": settings.ai_configured,
        }

    return app


app = create_app()
