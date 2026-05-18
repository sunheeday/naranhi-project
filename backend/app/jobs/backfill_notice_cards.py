from __future__ import annotations

import argparse
import json
import logging
import sys

from app.services.notice_card_service import run_notice_card_backfill


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild derived notice_cards from extracted_content.",
    )
    parser.add_argument(
        "--notice-id",
        help="Rebuild cards for one notice id.",
    )
    parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=100,
        help="Maximum notices to scan. Use 0 for no limit. Default: 100.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidate card counts without deleting or inserting cards.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = run_notice_card_backfill(
            notice_id=args.notice_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        print(json.dumps(summary.to_dict(), ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - systemic job errors should fail loudly.
        LOGGER.exception("notice card backfill failed")
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


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
