"""Create a translation-quality iteration from a curated mock notice seed set.

Usage:
    python scripts/scaffold_translation_quality_iteration.py \
        --iter-dir .agents/translation-quality/iterations/2026-06-02_iter-codex-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = (
    REPO_ROOT / ".agents" / "translation-quality" / "mock-notices" / "seed-set-v1.json"
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter-dir", required=True, type=Path, help="Iteration directory to create.")
    parser.add_argument(
        "--seed",
        default=DEFAULT_SEED,
        type=Path,
        help="Path to a seed-set JSON file. Defaults to mock-notices/seed-set-v1.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite manifest and source files if the iteration directory already exists.",
    )
    args = parser.parse_args()

    iter_dir = args.iter_dir
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    notices = list(seed.get("notices") or [])
    if not notices:
        raise SystemExit(f"Seed set has no notices: {args.seed}")

    iter_dir.mkdir(parents=True, exist_ok=True)
    for relative in (
        "evaluation/held-out-detail",
        "engineering",
        "pipeline-output-after/training",
        "pipeline-output-after/held_out",
    ):
        (iter_dir / relative).mkdir(parents=True, exist_ok=True)

    manifest = {
        "iteration": iter_dir.name,
        "date": iter_dir.name.split("_iter", 1)[0],
        "seed_set": seed.get("name"),
        "target_languages": list(seed.get("target_languages") or ["en", "ru", "ar"]),
        "split": {
            "training": sum(1 for notice in notices if notice.get("role") == "training"),
            "held_out": sum(1 for notice in notices if notice.get("role") == "held_out"),
        },
        "notices": [],
    }

    for notice in notices:
        role = str(notice["role"])
        notice_id = str(notice["id"])
        notice_dir = iter_dir / "notices" / role / notice_id
        notice_dir.mkdir(parents=True, exist_ok=True)

        source_path = notice_dir / "source.ko.md"
        source_meta_path = notice_dir / "source-meta.json"
        if args.force or not source_path.exists():
            source_path.write_text(str(notice["source_text"]).rstrip() + "\n", encoding="utf-8")
        if args.force or not source_meta_path.exists():
            _write_json(
                source_meta_path,
                {
                    "origin": notice.get("origin", seed.get("name")),
                    "kind": notice.get("kind"),
                    "issuer": notice.get("issuer"),
                    "notes": notice.get("notes", ""),
                    "seed_set": seed.get("name"),
                },
            )

        manifest["notices"].append(
            {
                key: value
                for key, value in notice.items()
                if key != "source_text"
            }
            | {
                "source_path": str(source_path.relative_to(iter_dir)),
            }
        )

    if args.force or not (iter_dir / "manifest.json").exists():
        _write_json(iter_dir / "manifest.json", manifest)

    _ensure_file(
        iter_dir / "evaluation" / "feedback-report.md",
        "# Feedback Report\n\nVerdict: pending\n\nThis file is reserved for evaluator output.\n",
    )
    _ensure_file(
        iter_dir / "evaluation" / "scores.json",
        json.dumps(
            {
                "iteration": iter_dir.name,
                "seed_set": seed.get("name"),
                "status": "pending_evaluation",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    _ensure_file(
        iter_dir / "engineering" / "improvement-plan.md",
        "# Improvement Plan\n\nVerdict: pending\n\nThis file is reserved for engineer output.\n",
    )
    _ensure_file(
        iter_dir / "engineering" / "changes-summary.md",
        "# Changes Summary\n\nReserved for implementation notes.\n",
    )
    _ensure_file(
        iter_dir / "_codex-runbook.md",
        "\n".join(
            [
                "# Codex Runbook",
                "",
                "1. Validate the scaffold:",
                f"   `python scripts/validate_translation_iteration.py --iter-dir {iter_dir}`",
                "2. Run the baseline pipeline:",
                f"   `python scripts/run_iteration.py --iter {iter_dir}`",
                "3. Delegate Prompt Auditor / Mock Scenario Curator / Regression Verifier tasks.",
                "4. Apply prompt or validator changes.",
                "5. Re-run the same iteration and compare scores.",
                "",
            ]
        ),
    )

    print(f"Created iteration scaffold at {iter_dir}")
    print(f"Seed set: {args.seed}")
    print(f"Notices: {len(notices)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
