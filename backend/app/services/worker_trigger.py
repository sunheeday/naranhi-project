"""큐에 잡을 넣은 직후 해당 Cloud Run Job을 깨우는 트리거.

상시가동 워커(min-instances=1, 2초 폴링) 대신, enqueue 시점에 run.jobs.run으로
워커 Job을 1회 실행시켜 "필요할 때만" 큐를 비운다. 기본 off라 로컬·테스트·미설정
환경에서는 아무 동작도 하지 않는다. 모든 호출은 best-effort(실패해도 예외를 올리지
않음) — 트리거가 실패해도 큐의 잡은 백스톱 스케줄러가 처리한다.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

import httpx

from app.core.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)

# job_type → 어느 워커 Job을 깨울지
_TRANSLATION_JOB_TYPES = frozenset({"notice_translation"})
_CRAWLER_JOB_TYPES = frozenset({"school_board_discovery", "school_notice_extraction"})

_RUN_API_BASE = "https://run.googleapis.com/v2"
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# 버스트(예: 한 공지의 9개 언어 동시 요청) 흡수용 인메모리 디바운스.
_debounce_lock = threading.Lock()
_last_triggered_monotonic: dict[str, float] = {}

# fire-and-forget 태스크가 GC되지 않도록 강한 참조 유지
_pending_tasks: set[asyncio.Task] = set()


def _job_name_for_job_type(job_type: str, settings: Settings) -> str | None:
    if job_type in _TRANSLATION_JOB_TYPES:
        return (settings.translation_worker_job_name or "").strip() or None
    if job_type in _CRAWLER_JOB_TYPES:
        return (settings.crawler_worker_job_name or "").strip() or None
    return None


def _debounce_allows(job_name: str, debounce_seconds: float) -> bool:
    if debounce_seconds <= 0:
        return True
    now = time.monotonic()
    with _debounce_lock:
        last = _last_triggered_monotonic.get(job_name)
        if last is not None and (now - last) < debounce_seconds:
            return False
        _last_triggered_monotonic[job_name] = now
        return True


def trigger_worker_for_job_type(job_type: str) -> bool:
    """해당 job_type을 처리하는 Cloud Run Job을 1회 깨운다(동기, best-effort).

    트리거 비활성(기본)·Job 이름/프로젝트 미설정·디바운스 차단 시 호출하지 않는다.
    실패해도 예외를 올리지 않는다. 실제 run.jobs.run을 보냈으면 True.
    """
    settings = get_settings()
    if not settings.worker_trigger_enabled:
        return False
    job_name = _job_name_for_job_type(job_type, settings)
    if not job_name:
        return False
    if not settings.gcp_project_id or not settings.gcp_region:
        LOGGER.warning("worker trigger skipped: GCP_PROJECT_ID/GCP_REGION not set")
        return False
    if not _debounce_allows(job_name, settings.worker_trigger_debounce_seconds):
        return False
    try:
        _post_run_job(job_name, settings)
        return True
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning(
            "worker trigger failed (best-effort): job=%s job_type=%s error=%s",
            job_name,
            job_type,
            exc,
        )
        return False


def _post_run_job(job_name: str, settings: Settings) -> None:
    import google.auth
    from google.auth.transport.requests import Request as AuthRequest

    credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    credentials.refresh(AuthRequest())
    url = (
        f"{_RUN_API_BASE}/projects/{settings.gcp_project_id}"
        f"/locations/{settings.gcp_region}/jobs/{job_name}:run"
    )
    response = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        },
        json={},
        timeout=10.0,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"run.jobs.run returned {response.status_code}: {response.text[:300]}")
    LOGGER.info("worker job triggered: job=%s status=%s", job_name, response.status_code)


def schedule_worker_trigger(job_type: str) -> None:
    """이벤트 루프를 막지 않고 트리거를 예약한다(fire-and-forget).

    동기 google-auth/httpx 호출을 스레드풀에서 돌린다. 트리거 비활성이거나 실행 루프가
    없으면(테스트 등) 아무 동작도 하지 않는다 — 트리거는 항상 best-effort다.
    """
    if not get_settings().worker_trigger_enabled:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(asyncio.to_thread(trigger_worker_for_job_type, job_type))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
