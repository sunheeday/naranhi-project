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
from app.translation.json_client import build_json_client  # noqa: E402
from app.translation.orchestrator import (  # noqa: E402
    TranslationPipeline,
    TranslationPipelineInput,
)


def _apply_arm_env(iter_dir: Path, arm_id: str) -> dict:
    """arms.json 의 env 를 프로세스 환경에 적용하고 arm 정의를 돌려준다.

    get_settings 는 lru_cache 라 환경을 바꾼 뒤 반드시 캐시를 비워야 한다.
    """
    arms_path = iter_dir / "arms.json"
    if not arms_path.is_file():
        raise SystemExit(f"ERROR: arms.json not found at {arms_path}")
    arms = json.loads(arms_path.read_text(encoding="utf-8")).get("arms") or []
    for arm in arms:
        if arm.get("id") == arm_id:
            for key, value in (arm.get("env") or {}).items():
                os.environ[key] = str(value)
            get_settings.cache_clear()
            return arm
    raise SystemExit(f"ERROR: arm '{arm_id}' not found in {arms_path}")


async def run_one(
    pipeline: TranslationPipeline,
    source_text: str,
    lang: str,
    approved_ingredient_dictionary: list[dict],
    approved_ingredient_dictionary_target: list[dict],
) -> dict:
    payload = TranslationPipelineInput(
        source_text=source_text,
        target_language=lang,
        approved_ingredient_dictionary=approved_ingredient_dictionary,
        approved_ingredient_dictionary_target=approved_ingredient_dictionary_target,
        max_auto_fix_attempts_per_stage=1,
    )
    return await pipeline.run(payload)


def _load_source_meta(source_path: Path) -> dict:
    meta_path = source_path.parent / "source-meta.json"
    if not meta_path.is_file():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _ingredient_dictionaries_for_language(meta: dict, lang: str) -> tuple[list[dict], list[dict]]:
    source_dictionary = list(meta.get("approved_ingredient_dictionary") or [])
    target_by_language = meta.get("approved_ingredient_dictionary_target_by_language") or {}
    target_dictionary = list(target_by_language.get(lang) or [])
    return source_dictionary, target_dictionary


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
    parser.add_argument(
        "--arm",
        default=None,
        help="arms.json 의 arm id. 지정하면 pipeline-output/<arm>/ 아래에 쓴다.",
    )
    args = parser.parse_args()

    iter_dir: Path = args.iter
    manifest_path = iter_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    arm = _apply_arm_env(iter_dir, args.arm) if args.arm else None
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

    gemini = build_json_client(settings)
    pipeline = TranslationPipeline(gemini)

    if settings.translation_backend == "bedrock":
        backend = f"Bedrock {settings.bedrock_region}"
        model_name = settings.bedrock_translation_model
    else:
        backend = "Vertex AI" if settings.use_vertex else "AI Studio API key"
        model_name = settings.gemini_translation_model or settings.gemini_model
    print(
        f"Iteration: {iter_dir.name} | arm={args.arm or '(none)'} | model={model_name} ({backend}) "
        f"| notices={len(notices)} | langs={','.join(target_langs)}"
    )

    summary: list[dict] = []
    start = time.time()

    for notice in notices:
        notice_id = notice["id"]
        role = notice["role"]
        source_path = iter_dir / notice["source_path"]
        out_dir = source_path.parent / "pipeline-output"
        if args.arm:
            out_dir = out_dir / args.arm
        out_dir.mkdir(parents=True, exist_ok=True)
        source_text = source_path.read_text(encoding="utf-8")
        source_meta = _load_source_meta(source_path)

        print(f"\n[{notice_id}] role={role} kind={notice.get('kind')}")

        notice_summary = {"id": notice_id, "role": role, "languages": {}}
        for lang in target_langs:
            t0 = time.time()
            approved_ingredient_dictionary, approved_ingredient_dictionary_target = (
                _ingredient_dictionaries_for_language(source_meta, lang)
            )
            try:
                result = await run_one(
                    pipeline,
                    source_text,
                    lang,
                    approved_ingredient_dictionary,
                    approved_ingredient_dictionary_target,
                )
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

            wall_seconds = round(time.time() - t0, 2)
            if isinstance(result, dict):
                result["wall_seconds"] = wall_seconds

            (out_dir / f"{lang}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            notice_summary["languages"][lang] = {
                "status": result.get("status"),
                "validation": result.get("validation"),
                "wall_seconds": wall_seconds,
            }
        summary.append(notice_summary)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")

    summary_name = f"_pipeline_run_summary.{args.arm}.json" if args.arm else "_pipeline_run_summary.json"
    (iter_dir / summary_name).write_text(
        json.dumps(
            {"arm": args.arm, "elapsed_seconds": round(elapsed, 1), "notices": summary},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
