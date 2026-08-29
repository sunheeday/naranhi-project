from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.api.notices import _translate_sources_for_locale_background
from app.core.logging_setup import setup_logging
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

    slots = max(1, batch_size)
    pending: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    counters = {"claimed": 0, "processed": 0, "in_flight": 0}
    slot_freed = asyncio.Event()

    async def _process_one(job: dict[str, object]) -> None:
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

    async def _consumer() -> None:
        while True:
            job = await pending.get()
            if job is None:
                return
            counters["in_flight"] += 1
            try:
                await _process_one(job)
            finally:
                counters["in_flight"] -= 1
                counters["processed"] += 1
                slot_freed.set()

    consumers = [asyncio.create_task(_consumer()) for _ in range(slots)]
    grace_used = False
    # claim()이 빈 응답을 준 뒤로는(그리고 grace 재폴링도 소진했다면) 더 이상
    # 새 claim을 시도하지 않는다 — 이미 pending/in-flight인 잡만 비워내고 끝낸다.
    # 이게 없으면 top-up이 바쁜 동안(슬롯이 남아 있는 한) idle_grace_seconds=0이어도
    # 슬롯이 빌 때마다 계속 claim을 재시도해 "grace 없음" 계약을 어긴다.
    queue_exhausted = False

    try:
        while True:
            if queue_exhausted:
                if pending.qsize() == 0 and counters["in_flight"] == 0:
                    break
                slot_freed.clear()
                await slot_freed.wait()
                continue

            remaining = slots if max_jobs <= 0 else max_jobs - counters["claimed"]
            free = slots - (pending.qsize() + counters["in_flight"])
            limit = min(free, remaining)
            # 슬롯이 하나라도 비면 곧바로 채운다.
            #
            # 처음엔 「claim 이 동기 DB 왕복이니 여유가 절반 이상일 때만 채운다」로
            # 두었는데, 실측을 얻고 보니 잘못된 절충이었다. 잡 하나가 약 51초인데
            # (Task 3: 공지 1건 x 언어 1개 = 51.64초) claim 왕복은 수십 밀리초다.
            # 슬롯 10개 기준 임계값을 절반에 두면 다섯 번째 완료를 기다리는 동안
            # 최대 네 슬롯이 수십 초를 논다. 그걸 아끼려고 절약하는 것은
            # 왕복 여덟 번 — 1초도 안 된다. 바꾼 쪽이 맞다.
            if limit <= 0:
                if remaining <= 0 and pending.qsize() == 0 and counters["in_flight"] == 0:
                    break
                slot_freed.clear()
                await slot_freed.wait()
                continue

            jobs = queue.claim(job_types=[JOB_TYPE], limit=limit)
            if not jobs:
                # enqueue-트리거 경합: drain 종료 직전 짧게 한 번 더 폴링해
                # 막 들어온 잡을 놓치지 않는다.
                if idle_grace_seconds > 0 and not grace_used:
                    grace_used = True
                    await asyncio.sleep(idle_grace_seconds)
                    continue
                queue_exhausted = True
                continue

            grace_used = False
            counters["claimed"] += len(jobs)
            LOGGER.info(
                "translation worker batch claimed: count=%s job_ids=%s",
                len(jobs),
                ",".join(str(job.get("id")) for job in jobs),
            )
            for job in jobs:
                pending.put_nowait(job)
    except BaseException:
        # 바깥에서 취소되면 소비자도 함께 접는다 — gather 시절의 취소 전파와 같은 계약.
        for task in consumers:
            task.cancel()
        await asyncio.gather(*consumers, return_exceptions=True)
        raise

    for _ in consumers:
        pending.put_nowait(None)
    results = await asyncio.gather(*consumers, return_exceptions=True)
    for item in results:
        # CancelledError 는 Exception 이 아니다. graceful shutdown 신호이므로 그대로 전파한다.
        if isinstance(item, BaseException) and not isinstance(item, Exception):
            raise item
    return counters["processed"]


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
    setup_logging(job_type="translation_worker")
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
