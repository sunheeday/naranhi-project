from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import logging
from typing import Any

import httpx
from postgrest.exceptions import APIError

from app.core.supabase import get_supabase_client, reset_supabase_client

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnqueueResult:
    accepted: bool
    already_running: bool
    job_id: str | None = None


class JobQueueService:
    def _execute_with_retry(self, operation):  # noqa: ANN001
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return operation(get_supabase_client())
            except (httpx.HTTPError, BrokenPipeError, ConnectionError, OSError) as exc:
                last_error = exc
                LOGGER.warning(
                    "job queue supabase request failed; resetting client and retrying: attempt=%s error=%s",
                    attempt + 1,
                    exc,
                )
                reset_supabase_client()
        if last_error is not None:
            raise last_error
        raise RuntimeError("Job queue operation failed without an error.")

    def enqueue(
        self,
        *,
        job_type: str,
        job_key: str,
        payload: dict[str, Any],
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> EnqueueResult:
        existing = self._execute_with_retry(
            lambda client: (
                client.table("app_jobs")
                .select("id")
                .eq("job_key", job_key)
                .in_("status", ["queued", "processing"])
                .limit(1)
                .execute()
                .data
                or []
            )
        )
        if existing:
            return EnqueueResult(accepted=True, already_running=True, job_id=str(existing[0].get("id") or ""))

        row = {
            "job_type": job_type,
            "job_key": job_key,
            "payload": payload,
            "max_attempts": max_attempts,
        }
        if available_at is not None:
            row["available_at"] = available_at.astimezone(UTC).isoformat()

        try:
            inserted = self._execute_with_retry(lambda client: client.table("app_jobs").insert(row).execute().data or [])
        except APIError as exc:
            if getattr(exc, "code", "") == "23505":
                current = self._execute_with_retry(
                    lambda client: (
                        client.table("app_jobs")
                        .select("id")
                        .eq("job_key", job_key)
                        .in_("status", ["queued", "processing"])
                        .limit(1)
                        .execute()
                        .data
                        or []
                    )
                )
                return EnqueueResult(
                    accepted=True,
                    already_running=True,
                    job_id=str(current[0].get("id") or "") if current else None,
                )
            raise

        job_id = str(inserted[0].get("id") or "") if inserted else None
        return EnqueueResult(accepted=True, already_running=False, job_id=job_id)

    def completed_recently(self, *, job_key: str, within_seconds: int) -> bool:
        """같은 job_key 잡이 최근에 완료됐는지 — 완료 직후 동일 작업 재등록(루프) 방지용."""
        cutoff = (datetime.now(UTC) - timedelta(seconds=within_seconds)).isoformat()
        rows = self._execute_with_retry(
            lambda client: (
                client.table("app_jobs")
                .select("id")
                .eq("job_key", job_key)
                .eq("status", "completed")
                .gte("finished_at", cutoff)
                .limit(1)
                .execute()
                .data
                or []
            )
        )
        return bool(rows)

    def latest_job(self, *, job_key: str) -> dict[str, Any] | None:
        """같은 job_key의 가장 최근 잡 1건 — 프론트 상태 표시(준비중/실패)용."""
        rows = self._execute_with_retry(
            lambda client: (
                client.table("app_jobs")
                .select("id,status,attempts,max_attempts,created_at,finished_at")
                .eq("job_key", job_key)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
                .data
                or []
            )
        )
        return rows[0] if rows else None

    def reclaim_stale_jobs(self, *, job_types: list[str], stale_seconds: int) -> int:
        """오래된 'processing' 잡을 회수한다.

        워커가 잡을 claim한 뒤(status='processing') 재배포·크래시로 죽으면 그 행은
        영구히 'processing'으로 남고, job_key 유니크 인덱스가 동일 작업의 재등록을
        영구 차단한다(좀비 잡). started_at이 stale_seconds보다 오래된 processing 잡을,
        시도가 남았으면 'queued'로 되돌리고 소진됐으면 'failed'로 종료한다.
        추출기(content_extraction_service)의 stale 회수와 같은 방식. 회수 수를 반환한다.
        """
        now = datetime.now(UTC)
        cutoff = (now - timedelta(seconds=stale_seconds)).isoformat()
        rows = self._execute_with_retry(
            lambda client: (
                client.table("app_jobs")
                .select("id,attempts,max_attempts")
                .in_("job_type", job_types)
                .eq("status", "processing")
                .lt("started_at", cutoff)
                .execute()
                .data
                or []
            )
        )

        reclaimed = 0
        for row in rows:
            attempts = int(row.get("attempts") or 0)
            max_attempts = int(row.get("max_attempts") or 1)
            should_retry = attempts < max_attempts
            payload: dict[str, Any] = {
                "updated_at": now.isoformat(),
                "last_error": f"reclaimed stale processing job (started_at older than {stale_seconds}s)",
            }
            if should_retry:
                payload["status"] = "queued"
                payload["available_at"] = now.isoformat()
            else:
                payload["status"] = "failed"
                payload["finished_at"] = now.isoformat()
            # status='processing' 조건부 업데이트: 그 사이 원래 워커가 완료/실패시키면 건너뛴다.
            updated = self._execute_with_retry(
                lambda client, row=row, payload=payload: (
                    client.table("app_jobs")
                    .update(payload)
                    .eq("id", row["id"])
                    .eq("status", "processing")
                    .execute()
                    .data
                    or []
                )
            )
            if updated:
                reclaimed += 1

        if reclaimed:
            LOGGER.warning(
                "reclaimed stale processing jobs: count=%s job_types=%s stale_seconds=%s",
                reclaimed,
                ",".join(job_types),
                stale_seconds,
            )
        return reclaimed

    def claim(self, *, job_types: list[str], limit: int) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        rows = self._execute_with_retry(
            lambda client: (
                client.table("app_jobs")
                .select("*")
                .in_("job_type", job_types)
                .eq("status", "queued")
                .lte("available_at", now.isoformat())
                .order("created_at")
                .limit(limit)
                .execute()
                .data
                or []
            )
        )

        claimed: list[dict[str, Any]] = []
        for row in rows:
            claimed_row = self._execute_with_retry(
                lambda client, row=row: (
                    client.table("app_jobs")
                    .update(
                        {
                            "status": "processing",
                            "attempts": int(row.get("attempts") or 0) + 1,
                            "started_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                        }
                    )
                    .eq("id", row["id"])
                    .eq("status", "queued")
                    .execute()
                    .data
                    or []
                )
            )
            if claimed_row:
                claimed.append(claimed_row[0])
        return claimed

    def complete(self, job_id: str, *, result: dict[str, Any] | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        self._execute_with_retry(
            lambda client: client.table("app_jobs")
            .update(
                {
                    "status": "completed",
                    "finished_at": now,
                    "updated_at": now,
                    "result": result or {},
                    "last_error": None,
                }
            )
            .eq("id", job_id)
            .execute()
        )

    def fail(
        self,
        job: dict[str, Any],
        *,
        error: str,
        retry_delay_seconds: int = 60,
    ) -> None:
        now = datetime.now(UTC)
        attempts = int(job.get("attempts") or 0)
        max_attempts = int(job.get("max_attempts") or 1)
        should_retry = attempts < max_attempts
        payload = {
            "status": "queued" if should_retry else "failed",
            "updated_at": now.isoformat(),
            "last_error": error[:1000],
        }
        if should_retry:
            payload["available_at"] = (now + timedelta(seconds=retry_delay_seconds)).isoformat()
        else:
            payload["finished_at"] = now.isoformat()
        self._execute_with_retry(lambda client: client.table("app_jobs").update(payload).eq("id", job["id"]).execute())


def serialize_job_result(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return {"value": value}
