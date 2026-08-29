"""Cloud Scheduler 조회·정지·재개 + Cloud Run Job 인자 지정 실행.

worker_trigger.trigger_worker_for_job_type 을 재사용하지 않는 이유 셋:
  ① 인메모리 디바운스(worker_trigger.py:45-54) — 관리자가 누른 버튼이 조용히
     무시되면 안 된다.
  ② except Exception 으로 모든 실패를 삼키고 False 를 돌려준다(:77-84) —
     관리자에게는 실패 사유가 그대로 보여야 한다.
  ③ WORKER_TRIGGER_ENABLED 가 꺼져 있으면 no-op(:64-65) — 관리자 조작은
     이 스위치와 무관해야 한다.

여기 있는 함수는 디바운스 없음 / 예외 전파 / overrides 채움이다.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

LOGGER = logging.getLogger(__name__)

_RUN_API_BASE = "https://run.googleapis.com/v2"
_SCHEDULER_API_BASE = "https://cloudscheduler.googleapis.com/v1"
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_TIMEOUT_SECONDS = 20.0

# ⚠️ 화이트리스트를 코드 상수로 고정한다. 조작 가능한 이름을 API 인자로 자유롭게
#    받으면 관리자 콘솔이 GCP 프로젝트 전체의 조작 창구가 된다.
#
#    docs/scheduled-crawl-runbook.md 의 생성 명령을 그대로 믿지 않고
#    `gcloud scheduler jobs list --location=asia-northeast3` (읽기 전용, 2026-08-29)
#    로 실운영 이름을 직접 확인했다. 문서/구브리프가 틀렸던 두 곳:
#      school-crawler   문서 추정 "-1800" → 실제 "-1900"
#      content-extractor 문서 추정 "-1900" → 실제 "-2000"
#    naranhi-crawler-backstop / naranhi-translation-backstop(10분 주기)은
#    의도적으로 뺐다 — 이 Task 의 대상은 하루 2회 정기 크롤/추출 스케줄러뿐이다.
CONTROLLABLE_SCHEDULERS = frozenset(
    {
        "naranhi-school-crawler-0600",
        "naranhi-school-crawler-1900",
        "naranhi-content-extractor-0700",
        "naranhi-content-extractor-2000",
    }
)

# 인자 지정 실행을 허용하는 Job. 워커 Job(translation/crawler)은 넣지 않는다 —
# 그쪽은 큐가 깨우는 것이지 사람이 인자를 넣어 부르는 대상이 아니다.
# `gcloud run jobs list --region=asia-northeast3` (읽기 전용)로 두 이름 모두
# 실운영과 일치함을 확인했다.
RUNNABLE_JOBS = frozenset(
    {
        "naranhi-content-extractor",
        "naranhi-school-crawler",
    }
)


@dataclass(frozen=True)
class RunResult:
    job_name: str
    operation: str
    args: list[str]

    def to_dict(self) -> dict[str, object]:
        return {"job_name": self.job_name, "operation": self.operation, "args": self.args}


def _authed_headers() -> dict[str, str]:
    import google.auth
    from google.auth.transport.requests import Request as AuthRequest

    credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    credentials.refresh(AuthRequest())
    return {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }


def _scheduler_parent() -> str:
    settings = get_settings()
    location = (settings.scheduler_location or settings.gcp_region or "").strip()
    if not settings.gcp_project_id or not location:
        raise RuntimeError("GCP_PROJECT_ID / SCHEDULER_LOCATION 이 설정되지 않았습니다.")
    return f"projects/{settings.gcp_project_id}/locations/{location}"


def _raise_for_status(response: Any, label: str) -> None:
    if response.status_code >= 300:
        raise RuntimeError(f"{label} returned {response.status_code}: {response.text[:300]}")


def _short_name(full_name: str) -> str:
    return (full_name or "").rsplit("/", 1)[-1]


def list_schedulers() -> list[dict[str, object]]:
    """문서가 아니라 API 가 돌려준 실제 cron 과 state 를 보여준다."""
    response = httpx.get(
        f"{_SCHEDULER_API_BASE}/{_scheduler_parent()}/jobs",
        headers=_authed_headers(),
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_status(response, "cloudscheduler.jobs.list")
    jobs = response.json().get("jobs") or []
    result = []
    for job in jobs:
        name = _short_name(job.get("name") or "")
        result.append(
            {
                "name": name,
                "schedule": job.get("schedule"),
                "time_zone": job.get("timeZone"),
                "state": job.get("state"),
                "last_attempt_time": job.get("lastAttemptTime"),
                "controllable": name in CONTROLLABLE_SCHEDULERS,
            }
        )
    return result


def pause_scheduler(name: str) -> dict[str, object]:
    return _scheduler_action(name, "pause")


def resume_scheduler(name: str) -> dict[str, object]:
    return _scheduler_action(name, "resume")


def _scheduler_action(name: str, action: str) -> dict[str, object]:
    if name not in CONTROLLABLE_SCHEDULERS:
        raise PermissionError(f"조작 대상이 아닌 스케줄러입니다: {name}")
    response = httpx.post(
        f"{_SCHEDULER_API_BASE}/{_scheduler_parent()}/jobs/{name}:{action}",
        headers=_authed_headers(),
        json={},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_status(response, f"cloudscheduler.jobs.{action}")
    body = response.json()
    LOGGER.info(
        "scheduler %s: name=%s state=%s",
        action,
        name,
        body.get("state"),
        extra={"scheduler_name": name, "scheduler_action": action},
    )
    return {"name": name, "state": body.get("state"), "schedule": body.get("schedule")}


def run_job_with_args(job_name: str, args: list[str]) -> RunResult:
    """Cloud Run Job 을 args overrides 로 1회 실행한다.

    worker_trigger.py:87-108 은 리터럴 json={} 이라 배포 시점에 고정된 --args 로만
    돈다. 그래서 「공지 1건 강제 재추출」이 수동 gcloud 밖에 방법이 없었다.
    """
    if job_name not in RUNNABLE_JOBS:
        raise PermissionError(f"실행 대상이 아닌 Job 입니다: {job_name}")
    settings = get_settings()
    if not settings.gcp_project_id or not settings.gcp_region:
        raise RuntimeError("GCP_PROJECT_ID / GCP_REGION 이 설정되지 않았습니다.")

    url = (
        f"{_RUN_API_BASE}/projects/{settings.gcp_project_id}"
        f"/locations/{settings.gcp_region}/jobs/{job_name}:run"
    )
    response = httpx.post(
        url,
        headers=_authed_headers(),
        json={"overrides": {"containerOverrides": [{"args": list(args)}]}},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_status(response, "run.jobs.run")
    operation = str(response.json().get("name") or "")
    LOGGER.info(
        "cloud run job started: job=%s operation=%s",
        job_name,
        operation,
        extra={"job_name": job_name, "operation": operation},
    )
    return RunResult(job_name=job_name, operation=operation, args=list(args))


def record_admin_action(
    *,
    admin_user_id: str | None,
    action: str,
    target: str | None,
    detail: dict[str, object] | None = None,
) -> None:
    """admin_audit_log 에 1행 남긴다. best-effort — 실패해도 방금 수행한 GCP 조작을
    되돌리지 않는다(이미 일어난 일이다). 대신 Task 8 패턴대로 조용히 넘어가되
    구조화 로그로 흔적을 남긴다 — 0038 이 아직 운영에 없거나 잠깐 조회가 실패해도
    "왜 감사 로그가 비어있는지"를 나중에 알 수 있게.

    admin_user_id 는 FastAPI 가 스스로 알 수 없다 — 이 라우터는 공유 토큰
    (X-Admin-Token)으로만 인증하고 "누가"는 모른다. 호출자(Next.js, 향후 Task
    13-15의 프록시 라우트)가 자신의 admin_sessions 세션에서 꺼내 X-Admin-Actor
    헤더로 넘겨주면 채워지고, 없거나 형식이 안 맞으면 null로 남는다 —
    행위 자체(무엇을 했는지)는 어느 쪽이든 기록된다.

    detail 에는 호출부가 이미 PII 없는 값만 담는다(스케줄러 이름/상태, Job
    이름/operation/args). 공지 제목·본문 같은 필드는 애초에 이 서비스가 다루지
    않는다.
    """
    from app.core.supabase import get_supabase_client

    row: dict[str, object] = {
        "admin_user_id": admin_user_id,
        "action": action,
        "target": target,
        "detail": detail or {},
    }
    try:
        get_supabase_client().table("admin_audit_log").insert(row).execute()
    except Exception as exc:  # noqa: BLE001 - 감사 로그 실패가 관리자 응답을 막으면 안 된다.
        LOGGER.warning(
            "admin audit log insert failed, continuing: action=%s target=%s error=%s",
            action,
            target,
            exc,
            extra={"action": action, "insert_error_type": type(exc).__name__},
        )


def parse_admin_actor(raw: str | None) -> str | None:
    """X-Admin-Actor 헤더를 admin_user_id(UUID)로만 받아들인다.
    형식이 안 맞으면 조용히 None — 신뢰되지 않는 자유서식 문자열을
    admin_audit_log.admin_user_id(uuid 컬럼)에 넣으려 하지 않는다."""
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw.strip()))
    except (ValueError, AttributeError):
        return None
