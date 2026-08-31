from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.core.logging_setup import setup_logging
from app.services.content_extraction_service import ContentExtractionService


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run content extraction for crawled school notices.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidate notices without claiming or extracting them.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force extraction for a specific --notice-id.",
    )
    parser.add_argument(
        "--notice-id",
        help="Run against one notice id. Required when using --force.",
    )
    parser.add_argument(
        "--max-notices",
        type=_positive_int,
        help="Maximum notices to process in this run.",
    )
    return parser


async def run_async(args: argparse.Namespace) -> int:
    summary = await ContentExtractionService().run(
        notice_id=args.notice_id,
        max_notices=args.max_notices,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return summary.exit_code()


def main(argv: list[str] | None = None) -> int:
    setup_logging(job_type="scheduled_content_extractor")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.force and not args.notice_id:
        parser.error("--force requires --notice-id")
    try:
        return asyncio.run(run_async(args))
    except Exception as exc:  # noqa: BLE001 - systemic job errors should fail loudly.
        LOGGER.exception("scheduled content extractor job failed")
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
