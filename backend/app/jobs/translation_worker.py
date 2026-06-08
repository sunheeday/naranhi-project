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
    return result


async def process_jobs(
    *,
    max_jobs: int,
    batch_size: int,
    retry_delay_seconds: int,
) -> int:
    queue = JobQueueService()
    processed = 0
    while processed < max_jobs:
        jobs = queue.claim(job_types=[JOB_TYPE], limit=min(batch_size, max_jobs - processed))
        if not jobs:
            break
        for job in jobs:
            try:
                result = await _run_job(job)
                queue.complete(str(job["id"]), result=serialize_job_result(result))
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
    )
    print(json.dumps({"ok": True, "processed": processed}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run queued notice translation jobs.")
    parser.add_argument("--max-jobs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=int, default=120)
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
