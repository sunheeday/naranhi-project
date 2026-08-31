from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime

from app.core.logging_setup import setup_logging
from app.services.crawl_run_history_service import outcome_for, record_crawl_run
from app.services.scheduled_crawler_service import ScheduledCrawlerService

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run scheduled school notice crawler for registered schools.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected schools without running the crawler.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore crawl_last_checked_at and unsupported cooldown checks.",
    )
    parser.add_argument(
        "--school-id",
        help="Run against one school id. Useful for manual verification.",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        help="Limit selected schools for local testing. Omit in production.",
    )
    return parser


async def run_async(args: argparse.Namespace) -> int:
    summary = await ScheduledCrawlerService().run(
        school_id=args.school_id,
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
    )
    payload = summary.to_dict()
    print(json.dumps(payload, ensure_ascii=False))
    # dry-run 은 이력에 쌓지 않는다 — 실제로 아무것도 수집하지 않았기 때문이다.
    if not args.dry_run:
        record_crawl_run(payload, outcome=outcome_for(payload))
    return summary.exit_code()


def main(argv: list[str] | None = None) -> int:
    setup_logging(job_type="scheduled_school_crawler")
    parser = build_parser()
    args = parser.parse_args(argv)
    # 크래시 경로에는 ScheduledCrawlerSummary 자체가 없어 started_at 을 거기서 못 구한다.
    # crawl_run_history.started_at 은 not null 이라 실행 시작 시각을 여기서 미리 잡아둔다.
    started_at = datetime.now(UTC).isoformat()
    try:
        return asyncio.run(run_async(args))
    except Exception as exc:  # noqa: BLE001 - job should fail loudly on systemic errors.
        LOGGER.exception("scheduled school crawler job failed")
        # 크래시도 이력에 남긴다. exit 1 만으로는 성공률 미달(alarm)과 구별되지 않는다.
        if not args.dry_run:
            record_crawl_run(
                {
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "dry_run": args.dry_run,
                    "force": args.force,
                },
                outcome="crashed",
                error_message=f"{type(exc).__name__}: {exc}",
            )
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "job_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
