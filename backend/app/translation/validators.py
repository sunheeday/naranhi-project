from __future__ import annotations

import re
from typing import Any


CRITICAL_FACT_FIELDS = (
    "dates",
    "times",
    "deadlines",
    "fees",
    "contacts",
    "urls",
    "grade_class_targets",
)


def validate_hard_facts_by_code(
    source_hard_facts: dict[str, Any],
    translated_hard_facts: dict[str, Any],
) -> dict[str, Any]:
    source = _hard_facts(source_hard_facts)
    translated = _hard_facts(translated_hard_facts)
    mismatches: list[dict[str, str]] = []

    for field in CRITICAL_FACT_FIELDS:
        source_values = _normalized_set(source.get(field))
        translated_values = _normalized_set(translated.get(field))
        missing = sorted(source_values - translated_values)
        extra = sorted(translated_values - source_values)

        if missing:
            mismatches.append(
                {
                    "field": field,
                    "source_value": ", ".join(missing),
                    "translated_value": ", ".join(sorted(translated_values)) or "",
                    "issue": "source fact is missing or changed in translated facts",
                    "recommended_fix": "restore the source fact with the same meaning",
                }
            )
        if extra and field in {"dates", "times", "fees", "contacts", "urls"}:
            mismatches.append(
                {
                    "field": field,
                    "source_value": ", ".join(sorted(source_values)) or "",
                    "translated_value": ", ".join(extra),
                    "issue": "translated facts contain a new critical value",
                    "recommended_fix": "remove unsupported critical value unless it exists in source",
                }
            )

    meal = source_hard_facts.get("meal_and_allergy") or {}
    if meal.get("requires_dictionary_mapping"):
        mismatches.append(
            {
                "field": "meal_and_allergy",
                "source_value": "requires_dictionary_mapping=true",
                "translated_value": "",
                "issue": "meal or ingredient data requires approved dictionary mapping",
                "recommended_fix": "route through ingredient identity mapping or human review",
            }
        )

    verdict = "PASS" if not mismatches else "FAIL"
    severity = "none" if verdict == "PASS" else "high"

    return {
        "verdict": verdict,
        "severity": severity,
        "mismatches": mismatches,
        "requires_human_review": False,
    }


def _hard_facts(value: dict[str, Any]) -> dict[str, Any]:
    facts = value.get("hard_facts")
    return facts if isinstance(facts, dict) else {}


def _normalized_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        if flattened:
            normalized.add(_normalize_fact(flattened))
    return {item for item in normalized if item}


def _machine_verifiable_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("normalized", "value", "raw_text", "text"):
            item = value.get(key)
            if item is not None:
                return _flatten_value(item)
        return ""
    return _flatten_value(value)


def _flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        parts: list[str] = []
        for key in sorted(value):
            item = value[key]
            if item is not None:
                parts.append(_flatten_value(item))
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(_flatten_value(item) for item in value)
    return str(value)


def _normalize_fact(value: str) -> str:
    stripped = value.strip().lower()
    stripped = re.sub(r"\s+", " ", stripped)
    stripped = stripped.replace("：", ":")
    stripped = stripped.replace("–", "-").replace("—", "-")
    return stripped
