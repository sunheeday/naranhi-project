"""관리자 전용 GCP 제어 라우터. 호출자는 Next.js 서버뿐이다.

crawler.py 의 _require_internal_token 을 재사용하지 않는다 — 그쪽은 토큰 미설정 +
ENVIRONMENT=local 이면 return 으로 통과시킨다(crawler.py:24-26). 크롤 트리거에는
편의지만 스케줄러 정지·Job 강제 실행에는 허용될 수 없는 fail-open 이다.

인증 경계: Next.js 관리자 세션(admin_sessions, __Host-naranhi_admin 쿠키)은
FastAPI 가 모른다 — 서버가 다르다. 여기는 공유 비밀(X-Admin-Token, GCP Secret
Manager `admin-api-token`)로만 인증한다. Next.js 가 자신의 쿠키 세션을 검증한
"뒤에" 이 토큰을 실어 대리 호출하는 구조를 전제한다. "누가" 눌렀는지는 이
라우터가 직접 알 수 없으므로, 감사 로그의 admin_user_id 는 호출자가 실어 보내는
X-Admin-Actor(호출자 자신의 admin_users.id)에서만 채운다 — 인가에는 쓰지 않고
기록에만 쓴다(gcp_admin_service.parse_admin_actor 가 UUID 형식이 아니면 버린다).
"""

from __future__ import annotations

import logging
import secrets
from typing import Callable, TypeVar

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.services.gcp_admin_service import (
    RunResult,
    list_schedulers,
    parse_admin_actor,
    pause_scheduler,
    record_admin_action,
    resume_scheduler,
    run_job_with_args,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def _require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = (get_settings().admin_api_token or "").strip()
    if not expected:
        # local 예외를 두지 않는다. 토큰이 없으면 환경 불문 잠긴다 — crawler.py 의
        # local fail-open 을 여기서는 재현하지 않는다.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_TOKEN is required.",
        )
    provided = (x_admin_token or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
        )


def _wrap(operation: Callable[[], T], label: str) -> T:
    try:
        return operation()
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RuntimeError as exc:
        LOGGER.warning("%s failed: %s", label, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/schedulers", dependencies=[Depends(_require_admin_token)])
async def get_schedulers() -> dict[str, object]:
    """조회 전용 — 부수효과 없음. 브라우저 프리페치·프록시가 눌러도 안전하다."""
    return {"ok": True, "jobs": _wrap(list_schedulers, "list_schedulers")}


@router.post("/schedulers/{name}/pause", dependencies=[Depends(_require_admin_token)])
async def post_scheduler_pause(
    name: str,
    x_admin_actor: str | None = Header(default=None, alias="X-Admin-Actor"),
) -> dict[str, object]:
    result = _wrap(lambda: pause_scheduler(name), "pause_scheduler")
    record_admin_action(
        admin_user_id=parse_admin_actor(x_admin_actor),
        action="scheduler_pause",
        target=name,
        detail=result,
    )
    return {"ok": True, "job": result}


@router.post("/schedulers/{name}/resume", dependencies=[Depends(_require_admin_token)])
async def post_scheduler_resume(
    name: str,
    x_admin_actor: str | None = Header(default=None, alias="X-Admin-Actor"),
) -> dict[str, object]:
    result = _wrap(lambda: resume_scheduler(name), "resume_scheduler")
    record_admin_action(
        admin_user_id=parse_admin_actor(x_admin_actor),
        action="scheduler_resume",
        target=name,
        detail=result,
    )
    return {"ok": True, "job": result}


@router.post("/jobs/{job_name}/run", dependencies=[Depends(_require_admin_token)])
async def post_job_run(
    job_name: str,
    args: list[str] = Body(default_factory=list, embed=True),
    x_admin_actor: str | None = Header(default=None, alias="X-Admin-Actor"),
) -> dict[str, object]:
    result: RunResult = _wrap(lambda: run_job_with_args(job_name, args), "run_job_with_args")
    record_admin_action(
        admin_user_id=parse_admin_actor(x_admin_actor),
        action="job_run",
        target=job_name,
        detail=result.to_dict(),
    )
    return {"ok": True, **result.to_dict()}
