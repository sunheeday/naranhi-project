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
