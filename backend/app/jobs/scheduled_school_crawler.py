from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

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
    print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return summary.exit_code()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run_async(args))
    except Exception as exc:  # noqa: BLE001 - job should fail loudly on systemic errors.
        LOGGER.exception("scheduled school crawler job failed")
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
