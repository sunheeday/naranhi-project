"""Run the translation pipeline for a single Korean source across multiple languages.

Usage:
    python scripts/translation_quality_driver.py \
        --source .agents/translation-quality/iterations/2026-06-01_iter-001/input/source.ko.md \
        --langs en,ru,ar \
        --out   .agents/translation-quality/iterations/2026-06-01_iter-001/pipeline-output/

Reads Gemini/Vertex settings from backend/.env (or env vars). Writes <lang>.json per language.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

# Make the backend's `app` package importable without installing it.
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Load backend/.env if present so Settings picks it up.
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
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Path to Korean source markdown/text file.",
    )
    parser.add_argument(
        "--langs",
        default="en,ru,ar",
        help="Comma-separated target language codes (default: en,ru,ar).",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output directory. <lang>.json will be written here.",
    )
    args = parser.parse_args()

    source_text = args.source.read_text(encoding="utf-8")
    langs = [lang.strip() for lang in args.langs.split(",") if lang.strip()]
    args.out.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    if not settings.gemini_configured:
        print(
            "ERROR: Gemini not configured. Set GEMINI_API_KEY or VERTEX_AI_PROJECT_ID "
            "in backend/.env or environment.",
            file=sys.stderr,
        )
        return 2

    gemini = GeminiJsonClient.from_settings(settings)
    pipeline = TranslationPipeline(gemini)

    print(
        f"Running pipeline for {len(langs)} language(s): {', '.join(langs)} "
        f"using model={settings.gemini_model} "
        f"({'Vertex AI' if settings.use_vertex else 'AI Studio API key'})"
    )

    results: dict[str, dict] = {}
    for lang in langs:
        print(f"  → {lang} ...", flush=True)
        try:
            result = await run_one(pipeline, source_text, lang)
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED: {exc}", file=sys.stderr)
            result = {
                "status": "driver_error",
                "target_language": lang,
                "error": str(exc),
            }
        results[lang] = result
        out_path = args.out / f"{lang}.json"
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"    saved {out_path}")

    summary = {
        lang: {
            "status": result.get("status"),
            "admin_review_required": (
                (result.get("admin_review") or {}).get("required")
                if isinstance(result.get("admin_review"), dict)
                else None
            ),
            "validation": result.get("validation"),
        }
        for lang, result in results.items()
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
