"""Run the translation pipeline for every notice listed in an iteration's manifest.json.

Usage:
    python scripts/run_iteration.py \
        --iter .agents/translation-quality/iterations/2026-06-01_iter-001/

Writes pipeline-output/<lang>.json under each notice's folder. Per-notice serial,
per-language serial — keeps within API rate limits when only one key is available.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

ENV_FILE = BACKEND_ROOT / ".env"
if ENV_FILE.is_file():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

from app.core.config import get_settings  # noqa: E402
from app.translation.gemini_client import GeminiJsonClient  # noqa: E402
from app.translation.orchestrator import (  # noqa: E402
    TranslationPipeline,
    TranslationPipelineInput,
)


async def run_one(
    pipeline: TranslationPipeline,
    source_text: str,
    lang: str,
) -> dict:
    payload = TranslationPipelineInput(
        source_text=source_text,
        target_language=lang,
        approved_ingredient_dictionary=[],
        approved_ingredient_dictionary_target=[],
        max_auto_fix_attempts_per_stage=1,
    )
    return await pipeline.run(payload)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter", required=True, type=Path, help="Iteration directory.")
    parser.add_argument(
        "--langs",
        default=None,
        help="Override languages (comma-separated). Defaults to manifest.target_languages.",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Comma-separated notice IDs to limit run to (default: all).",
    )
    args = parser.parse_args()

    iter_dir: Path = args.iter
    manifest_path = iter_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_langs = (
        [lang.strip() for lang in args.langs.split(",") if lang.strip()]
        if args.langs
        else list(manifest.get("target_languages") or ["en", "ru", "ar"])
    )

    notices = manifest.get("notices") or []
    if args.only:
        wanted = {item.strip() for item in args.only.split(",") if item.strip()}
        notices = [n for n in notices if n.get("id") in wanted]

    settings = get_settings()
    if not settings.gemini_configured:
        print(
            "ERROR: Gemini not configured. Set GEMINI_API_KEY or VERTEX_AI_PROJECT_ID.",
            file=sys.stderr,
        )
        return 2

    gemini = GeminiJsonClient.from_settings(settings)
    pipeline = TranslationPipeline(gemini)

    backend = "Vertex AI" if settings.use_vertex else "AI Studio API key"
    print(
        f"Iteration: {iter_dir.name} | model={settings.gemini_model} ({backend}) "
        f"| notices={len(notices)} | langs={','.join(target_langs)}"
    )

    summary: list[dict] = []
    start = time.time()

    for notice in notices:
        notice_id = notice["id"]
        role = notice["role"]
        source_path = iter_dir / notice["source_path"]
        out_dir = source_path.parent / "pipeline-output"
        out_dir.mkdir(parents=True, exist_ok=True)
        source_text = source_path.read_text(encoding="utf-8")

        print(f"\n[{notice_id}] role={role} kind={notice.get('kind')}")

        notice_summary = {"id": notice_id, "role": role, "languages": {}}
        for lang in target_langs:
            t0 = time.time()
            try:
                result = await run_one(pipeline, source_text, lang)
                status = result.get("status", "?")
                hf = (result.get("validation") or {}).get("hard_fact") or {}
                ct = (result.get("validation") or {}).get("context_tone") or {}
                print(
                    f"  {lang}: {status} | hf={hf.get('status', '?')} "
                    f"ct={ct.get('status', '?')} | {time.time() - t0:.1f}s"
                )
            except Exception as exc:  # noqa: BLE001
                result = {
                    "status": "driver_error",
                    "target_language": lang,
                    "error": str(exc),
                }
                print(f"  {lang}: ERROR — {exc}", file=sys.stderr)

            (out_dir / f"{lang}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            notice_summary["languages"][lang] = {
                "status": result.get("status"),
                "validation": result.get("validation"),
            }
        summary.append(notice_summary)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")

    (iter_dir / "_pipeline_run_summary.json").write_text(
        json.dumps(
            {"elapsed_seconds": round(elapsed, 1), "notices": summary},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
