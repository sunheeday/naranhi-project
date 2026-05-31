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
        source_values = _normalized_set_for_field(field, source.get(field))
        translated_values = _normalized_set_for_field(field, translated.get(field))
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


def _normalized_set_for_field(field: str, value: Any) -> set[str]:
    if field in {"dates", "deadlines"}:
        return _date_fact_set(value)
    if field == "contacts":
        return _contact_fact_set(value)
    if field == "grade_class_targets":
        return _grade_target_set(value)
    return _normalized_set(value)


def _normalized_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        if flattened:
            normalized.add(_normalize_fact(flattened))
    return {item for item in normalized if item}


def _date_fact_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        dates = _extract_iso_dates(flattened)
        if dates:
            normalized.update(dates)
            continue
        if flattened:
            normalized.add(_normalize_fact(flattened))
    return normalized


def _contact_fact_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        tokens = _extract_contact_tokens(flattened)
        if tokens:
            normalized.update(tokens)
            continue
        if flattened:
            normalized.add(_normalize_fact(flattened))
    return normalized


def _grade_target_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        grades = _extract_grade_tokens(flattened)
        if grades:
            normalized.update(grades)
            continue
        if flattened:
            normalized.add(_normalize_fact(flattened))
    return normalized


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


def _extract_iso_dates(value: str) -> set[str]:
    return {
        match.group(0)
        for match in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", value)
    }


def _extract_contact_tokens(value: str) -> set[str]:
    normalized = _normalize_fact(value)
    tokens: set[str] = set()

    for email in re.findall(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", normalized):
        tokens.add(f"email:{email}")

    for phone in re.findall(r"\+?\d[\d\-\s().]{7,}\d", value):
        digits = re.sub(r"\D", "", phone)
        if len(digits) >= 8:
            tokens.add(f"phone:{digits}")

    return tokens


def _extract_grade_tokens(value: str) -> set[str]:
    normalized = _normalize_fact(value)
    tokens: set[str] = set()

    for match in re.finditer(r"(\d+)\s*(?:st|nd|rd|th)?\s*grade", normalized):
        tokens.add(f"grade:{match.group(1)}")
    for match in re.finditer(r"grade\s*(\d+)", normalized):
        tokens.add(f"grade:{match.group(1)}")
    for match in re.finditer(r"(\d+)\s*학년", normalized):
        tokens.add(f"grade:{match.group(1)}")
    if not tokens and re.fullmatch(r"\d+", normalized):
        tokens.add(f"grade:{normalized}")

    return tokens
