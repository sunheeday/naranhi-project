from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.services.content_extraction_service import ContentExtractionService
from app.services.job_queue_service import JobQueueService, serialize_job_result
from app.services.school_crawler_service import SchoolCrawlerService

LOGGER = logging.getLogger(__name__)
JOB_TYPE_DISCOVERY = "school_board_discovery"
JOB_TYPE_EXTRACTION = "school_notice_extraction"


async def _run_discovery_job(job: dict[str, object], queue: JobQueueService) -> dict[str, object]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    school_id = str(payload.get("school_id") or "").strip()
    if not school_id:
        raise RuntimeError("Missing school_id in discovery job payload.")
    max_posts = int(payload.get("max_posts") or 0) or None
    LOGGER.info(
        "crawler discovery started: job_id=%s school_id=%s max_posts=%s",
        job.get("id"),
        school_id,
        max_posts,
    )
    result = await SchoolCrawlerService().discover_and_save_school_board(school_id, max_posts=max_posts)
    if result.status == "success" and result.success_count > 0:
        queue.enqueue(
            job_type=JOB_TYPE_EXTRACTION,
            job_key=f"school-extraction:{school_id}",
            payload={"school_id": school_id, "max_notices": result.success_count},
            max_attempts=5,
        )
    LOGGER.info(
        "crawler discovery finished: job_id=%s school_id=%s status=%s success_count=%s board_url=%s",
        job.get("id"),
        school_id,
        result.status,
        result.success_count,
        result.board_url,
    )
    return result.to_dict()


async def _run_extraction_job(job: dict[str, object]) -> dict[str, object]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    school_id = str(payload.get("school_id") or "").strip()
    if not school_id:
        raise RuntimeError("Missing school_id in extraction job payload.")
    max_notices = int(payload.get("max_notices") or 0) or 5
    LOGGER.info(
        "crawler extraction started: job_id=%s school_id=%s max_notices=%s",
        job.get("id"),
        school_id,
        max_notices,
    )
    summary = await ContentExtractionService().run_for_school(school_id, max_notices=max_notices)
    LOGGER.info(
        "crawler extraction finished: job_id=%s school_id=%s processed=%s success=%s errors=%s gemini_calls=%s",
        job.get("id"),
        school_id,
        summary.processed_count,
        summary.success_count,
        summary.error_count,
        summary.gemini_calls_used,
    )
    return summary.to_dict()


async def _process_single_job(
    queue: JobQueueService,
    job: dict[str, object],
    *,
    retry_delay_seconds: int,
) -> None:
    try:
        job_type = str(job.get("job_type") or "")
        LOGGER.info("crawler worker job claimed: job_id=%s job_type=%s", job.get("id"), job_type)
        if job_type == JOB_TYPE_DISCOVERY:
            result = await _run_discovery_job(job, queue)
        elif job_type == JOB_TYPE_EXTRACTION:
            result = await _run_extraction_job(job)
        else:
            raise RuntimeError(f"Unsupported crawler job type: {job_type}")
        queue.complete(str(job["id"]), result=serialize_job_result(result))
        LOGGER.info("crawler worker job completed: job_id=%s job_type=%s", job.get("id"), job_type)
    except asyncio.CancelledError as exc:
        LOGGER.warning("crawler worker job cancelled: job_id=%s", job.get("id"))
        queue.fail(job, error=f"{type(exc).__name__}: {exc}", retry_delay_seconds=retry_delay_seconds)
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("crawler worker job failed: job_id=%s", job.get("id"))
        queue.fail(job, error=f"{type(exc).__name__}: {exc}", retry_delay_seconds=retry_delay_seconds)


async def process_jobs(
    *,
    max_jobs: int,
    batch_size: int,
    retry_delay_seconds: int,
    stale_seconds: int,
    idle_grace_seconds: float = 0.0,
) -> int:
    queue = JobQueueService()
    queue.reclaim_stale_jobs(
        job_types=[JOB_TYPE_DISCOVERY, JOB_TYPE_EXTRACTION],
        stale_seconds=stale_seconds,
    )
    processed = 0
    grace_used = False
    # max_jobs<=0 이면 큐가 빌 때까지 drain(Cloud Run Job 1회 실행용).
    while max_jobs <= 0 or processed < max_jobs:
        limit = batch_size if max_jobs <= 0 else min(batch_size, max_jobs - processed)
        jobs = queue.claim(
            job_types=[JOB_TYPE_DISCOVERY, JOB_TYPE_EXTRACTION],
            limit=limit,
        )
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
            "crawler worker batch claimed: count=%s job_ids=%s",
            len(jobs),
            ",".join(str(job.get("id")) for job in jobs),
        )

        await asyncio.gather(
            *[
                _process_single_job(
                    queue,
                    job,
                    retry_delay_seconds=retry_delay_seconds,
                )
                for job in jobs
            ]
        )
        processed += len(jobs)
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
    parser = argparse.ArgumentParser(description="Run queued crawler and extraction jobs.")
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
        LOGGER.exception("crawler worker failed")
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
