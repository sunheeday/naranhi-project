from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from typing import Any

from postgrest.exceptions import APIError

from app.core.supabase import get_supabase_client


@dataclass(frozen=True)
class EnqueueResult:
    accepted: bool
    already_running: bool
    job_id: str | None = None


class JobQueueService:
    def enqueue(
        self,
        *,
        job_type: str,
        job_key: str,
        payload: dict[str, Any],
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> EnqueueResult:
        client = get_supabase_client()
        existing = (
            client.table("app_jobs")
            .select("id")
            .eq("job_key", job_key)
            .in_("status", ["queued", "processing"])
            .limit(1)
            .execute()
            .data
            or []
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
            inserted = client.table("app_jobs").insert(row).execute().data or []
        except APIError as exc:
            if getattr(exc, "code", "") == "23505":
                current = (
                    client.table("app_jobs")
                    .select("id")
                    .eq("job_key", job_key)
                    .in_("status", ["queued", "processing"])
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                return EnqueueResult(
                    accepted=True,
                    already_running=True,
                    job_id=str(current[0].get("id") or "") if current else None,
                )
            raise

        job_id = str(inserted[0].get("id") or "") if inserted else None
        return EnqueueResult(accepted=True, already_running=False, job_id=job_id)

    def claim(self, *, job_types: list[str], limit: int) -> list[dict[str, Any]]:
        client = get_supabase_client()
        now = datetime.now(UTC)
        rows = (
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

        claimed: list[dict[str, Any]] = []
        for row in rows:
            claimed_row = (
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
            if claimed_row:
                claimed.append(claimed_row[0])
        return claimed

    def complete(self, job_id: str, *, result: dict[str, Any] | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        get_supabase_client().table("app_jobs").update(
            {
                "status": "completed",
                "finished_at": now,
                "updated_at": now,
                "result": result or {},
                "last_error": None,
            }
        ).eq("id", job_id).execute()

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
        get_supabase_client().table("app_jobs").update(payload).eq("id", job["id"]).execute()


def serialize_job_result(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return {"value": value}
