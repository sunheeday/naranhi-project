"""Validate a translation-quality iteration scaffold before or after a run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter-dir", required=True, type=Path, help="Iteration directory to validate.")
    args = parser.parse_args()

    iter_dir = args.iter_dir
    manifest_path = iter_dir / "manifest.json"
    if not manifest_path.is_file():
        _error(f"manifest not found: {manifest_path}")
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    notices = list(manifest.get("notices") or [])
    target_languages = list(manifest.get("target_languages") or [])
    errors: list[str] = []

    if not target_languages:
        errors.append("manifest.target_languages is empty")
    if not notices:
        errors.append("manifest.notices is empty")

    roles = {notice.get("role") for notice in notices}
    if "training" not in roles or "held_out" not in roles:
        errors.append("manifest must include both training and held_out notices")

    seen_ids: set[str] = set()
    for notice in notices:
        notice_id = str(notice.get("id") or "")
        if not notice_id:
            errors.append("a notice is missing id")
            continue
        if notice_id in seen_ids:
            errors.append(f"duplicate notice id: {notice_id}")
        seen_ids.add(notice_id)

        role = str(notice.get("role") or "")
        if role not in {"training", "held_out"}:
            errors.append(f"{notice_id}: invalid role {role!r}")
            continue

        source_rel = notice.get("source_path")
        if not source_rel:
            errors.append(f"{notice_id}: missing source_path")
            continue

        source_path = iter_dir / str(source_rel)
        meta_path = source_path.parent / "source-meta.json"
        if not source_path.is_file():
            errors.append(f"{notice_id}: missing source file {source_path}")
        if not meta_path.is_file():
            errors.append(f"{notice_id}: missing source-meta.json {meta_path}")

    for required_dir in (
        iter_dir / "evaluation",
        iter_dir / "evaluation" / "held-out-detail",
        iter_dir / "engineering",
        iter_dir / "pipeline-output-after" / "training",
        iter_dir / "pipeline-output-after" / "held_out",
    ):
        if not required_dir.is_dir():
            errors.append(f"missing required directory: {required_dir}")

    if errors:
        for message in errors:
            _error(message)
        return 2

    print(
        json.dumps(
            {
                "iteration": iter_dir.name,
                "notice_count": len(notices),
                "target_languages": target_languages,
                "status": "ok",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
