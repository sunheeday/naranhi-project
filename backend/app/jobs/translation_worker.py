from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.api.notices import _translate_sources_for_locale_background
from app.services.job_queue_service import JobQueueService, serialize_job_result
from app.services.notice_service import NoticeService

LOGGER = logging.getLogger(__name__)
JOB_TYPE = "notice_translation"


async def _run_job(job: dict[str, object]) -> dict[str, object]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    notice_id = str(payload.get("notice_id") or "").strip()
    target_language = str(payload.get("target_language") or "").strip()
    if not notice_id or not target_language:
        raise RuntimeError("Missing notice_id or target_language in translation job payload.")
    normalized_target_language = target_language.lower()
    if normalized_target_language == "ko":
        LOGGER.info(
            "translation job skipped for canonical ko target: job_id=%s notice_id=%s",
            job.get("id"),
            notice_id,
        )
        return {
            "ok": True,
            "notice_id": notice_id,
            "target_language": "ko",
            "status": "ready_to_save",
            "translation": None,
            "saved": {"skipped": True, "reason": "korean_not_queued"},
        }
    LOGGER.info(
        "translation job started: job_id=%s notice_id=%s target_language=%s",
        job.get("id"),
        notice_id,
        target_language,
    )

    service = NoticeService()
    result = await service.translate_notice(
        notice_id=notice_id,
        target_language=target_language,
        source_text=payload.get("source_text") if isinstance(payload, dict) else None,
        approved_ingredient_dictionary=list(payload.get("approved_ingredient_dictionary") or []),
        approved_ingredient_dictionary_target=list(payload.get("approved_ingredient_dictionary_target") or []),
    )
    await _translate_sources_for_locale_background(
        service=service,
        notice_id=notice_id,
        target_language=target_language,
    )
    LOGGER.info(
        "translation job finished: job_id=%s notice_id=%s target_language=%s",
        job.get("id"),
        notice_id,
        target_language,
    )
    return result


async def process_jobs(
    *,
    max_jobs: int,
    batch_size: int,
    retry_delay_seconds: int,
    stale_seconds: int,
    idle_grace_seconds: float = 0.0,
) -> int:
    queue = JobQueueService()
    queue.reclaim_stale_jobs(job_types=[JOB_TYPE], stale_seconds=stale_seconds)
    processed = 0
    grace_used = False
    # max_jobs<=0 이면 큐가 빌 때까지 drain(Cloud Run Job 1회 실행용).
    while max_jobs <= 0 or processed < max_jobs:
        limit = batch_size if max_jobs <= 0 else min(batch_size, max_jobs - processed)
        jobs = queue.claim(job_types=[JOB_TYPE], limit=limit)
        if not jobs:
            # enqueue-트리거 경합: drain 종료 직전 짧게 한 번 더 폴링해
            # 막 들어온 잡을 놓치지 않는다.
            if idle_grace_seconds > 0 and not grace_used:
                grace_used = True
                await asyncio.sleep(idle_grace_seconds)
                continue
            break
        grace_used = False
        LOGGER.info(
            "translation worker batch claimed: count=%s job_ids=%s",
            len(jobs),
            ",".join(str(job.get("id")) for job in jobs),
        )
        for job in jobs:
            try:
                result = await _run_job(job)
                queue.complete(str(job["id"]), result=serialize_job_result(result))
                LOGGER.info("translation worker job completed: job_id=%s", job.get("id"))
            except asyncio.CancelledError as exc:
                LOGGER.warning("translation worker job cancelled: job_id=%s", job.get("id"))
                queue.fail(job, error=f"{type(exc).__name__}: {exc}", retry_delay_seconds=retry_delay_seconds)
                raise
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("translation worker job failed: job_id=%s", job.get("id"))
                queue.fail(job, error=f"{type(exc).__name__}: {exc}", retry_delay_seconds=retry_delay_seconds)
            processed += 1
    return processed


async def run_async(args: argparse.Namespace) -> int:
    processed = await process_jobs(
        max_jobs=args.max_jobs,
        batch_size=args.batch_size,
        retry_delay_seconds=args.retry_delay_seconds,
        stale_seconds=args.stale_minutes * 60,
        idle_grace_seconds=args.idle_grace_seconds,
    )
    print(json.dumps({"ok": True, "processed": processed}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run queued notice translation jobs.")
    parser.add_argument("--max-jobs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=int, default=120)
    parser.add_argument("--stale-minutes", type=int, default=180)
    # 0 = drain 안 함(상한 max-jobs까지). Cloud Run Job은 --max-jobs 0 --idle-grace-seconds 3 로 실행.
    parser.add_argument("--idle-grace-seconds", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run_async(args))
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("translation worker failed")
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
