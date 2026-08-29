from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.core.logging_setup import setup_logging
from app.crawler.neis_client import NeisQuotaExceeded
from app.services.school_schedule_sync_service import (
    SchoolScheduleSyncService,
    select_schedule_sync_targets,
)

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync NEIS SchoolSchedule into school_events for registered schools.",
    )
    parser.add_argument("--school-id", help="Run against one school id. Useful for manual verification.")
    parser.add_argument("--limit", type=_positive_int, help="Limit target schools for local testing.")
    parser.add_argument("--dry-run", action="store_true", help="Print targets without calling NEIS or writing.")
    return parser


async def run_async(args: argparse.Namespace) -> int:
    targets = select_schedule_sync_targets()
    if args.school_id:
        targets = [row for row in targets if str(row.get("id")) == args.school_id]
    if args.limit is not None:
        targets = targets[: args.limit]

    if args.dry_run:
        print(json.dumps({"dry_run": True, "target_count": len(targets),
                          "targets": [{"id": r.get("id"), "name": r.get("name")} for r in targets]},
                         ensure_ascii=False))
        return 0

    service = SchoolScheduleSyncService()
    results: list[dict[str, object]] = []
    quota_exceeded = False

    for row in targets:
        if quota_exceeded:
            # 한도 초과 후에는 남은 학교를 건너뛴다. 재시도 폭주 금지 — 다음 주기에 다시 온다.
            results.append({"school_id": str(row.get("id") or ""), "status": "skipped_quota"})
            continue
        try:
            results.append((await service.sync_school(row)).to_dict())
        except NeisQuotaExceeded as exc:
            quota_exceeded = True
            LOGGER.warning("NEIS quota exceeded, skipping remaining schools: %s", exc)
            results.append({"school_id": str(row.get("id") or ""), "status": "quota_exceeded",
                            "error_message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - one school must not stop the job.
            LOGGER.exception("school schedule sync failed: school_id=%s", row.get("id"))
            results.append({"school_id": str(row.get("id") or ""), "status": "failed",
                            "error_message": f"{type(exc).__name__}: {exc}"})

    synced = sum(1 for item in results if item.get("status") == "synced")
    failed = sum(1 for item in results if item.get("status") == "failed")
    summary = {
        "target_count": len(targets),
        "synced_count": synced,
        "failed_count": failed,
        "quota_exceeded": quota_exceeded,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False))
    # quota_exceeded 뿐 아니라 failed(예: 0039 미적용으로 모든 학교가 예외)도 종료코드에
    # 반영한다. 브리프 원안(quota_exceeded만 반영)대로면 0039 미적용 시 학교 전원이
    # "failed"여도 종료코드 0 — Cloud Run Job 실행 이력이 매주 조용히 "성공"으로 남는다.
    # 여기서 실패로 표시해야 gcloud run jobs executions list / Cloud Logging(ERROR)에
    # 드러난다(브리프 대비 변경 — task-7-report.md 참고).
    return 1 if quota_exceeded or failed > 0 else 0


def main(argv: list[str] | None = None) -> int:
    setup_logging(job_type="sync_school_schedules")
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run_async(args))
    except Exception as exc:  # noqa: BLE001 - job should fail loudly on systemic errors.
        LOGGER.exception("school schedule sync job failed")
        print(json.dumps({"ok": False, "status": "job_failed", "error": f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False), file=sys.stderr)
        return 1


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
