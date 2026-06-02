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

# "No cost" expressions across the source language and the three target
# languages. The Korean source extractor usually emits "free"/"무료" while the
# target extractor may emit "0", "0 krw", "free of charge", etc. These all
# describe the same fact and must collapse to one equivalence token so that a
# faithful translation does not trip a false-positive fee mismatch.
_FREE_OF_CHARGE_TOKENS = {
    "free",
    "free of charge",
    "no charge",
    "no cost",
    "0",
    "0 krw",
    "0krw",
    "0 won",
    "krw 0",
    "무료",
    "бесплатно",  # ru
    "бесплатный",
    "مجانا",  # ar
    "مجاني",
    "مجانية",
    "مجّانًا",
}


def validate_hard_facts_by_code(
    source_hard_facts: dict[str, Any],
    translated_hard_facts: dict[str, Any],
    ingredient_identity_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = _hard_facts(source_hard_facts)
    translated = _hard_facts(translated_hard_facts)
    mismatches: list[dict[str, str]] = []

    # Absolute calendar dates routinely migrate between the ``dates`` and
    # ``deadlines`` fields between the source and target extractions (e.g. the
    # Korean side files "6월 1일(월)" under dates while the target side files the
    # same day under "due by June 1" deadlines). Pool the two absolute-date sets
    # so a field migration is not reported as a missing/extra fact, while a
    # genuinely new or dropped calendar date is still caught.
    source_date_pool = _date_fact_set(source.get("dates")) | _date_fact_set(
        source.get("deadlines")
    )
    translated_date_pool = _date_fact_set(translated.get("dates")) | _date_fact_set(
        translated.get("deadlines")
    )

    for field in CRITICAL_FACT_FIELDS:
        if field == "deadlines":
            # Folded into the pooled absolute-date check under "dates".
            continue
        if field == "dates":
            source_values = source_date_pool
            translated_values = translated_date_pool
        else:
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
    if meal.get("requires_dictionary_mapping") and not _ingredient_mapping_satisfied(
        ingredient_identity_map
    ):
        mismatches.append(
            {
                "field": "meal_and_allergy",
                "source_value": "requires_dictionary_mapping=true",
                "translated_value": "",
                "issue": "meal or ingredient data requires approved dictionary mapping",
                "recommended_fix": "route through ingredient identity mapping and preserve unmapped Korean ingredient tokens without guessing",
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


def _ingredient_mapping_satisfied(ingredient_identity_map: dict[str, Any] | None) -> bool:
    if not isinstance(ingredient_identity_map, dict):
        return False

    unmapped = list(ingredient_identity_map.get("unmapped_ingredients") or [])
    critical_flags = ingredient_identity_map.get("critical_flags") or {}
    has_unmapped_critical = bool(critical_flags.get("contains_unmapped_critical_item"))
    mapped = list(ingredient_identity_map.get("mapped_ingredients") or [])
    return bool(mapped) and not unmapped and not has_unmapped_critical


def _hard_facts(value: dict[str, Any]) -> dict[str, Any]:
    facts = value.get("hard_facts")
    return facts if isinstance(facts, dict) else {}


def _normalized_set_for_field(field: str, value: Any) -> set[str]:
    if field in {"dates", "deadlines"}:
        return _date_fact_set(value)
    if field == "times":
        return _time_fact_set(value)
    if field == "contacts":
        return _contact_fact_set(value)
    if field == "urls":
        return _url_fact_set(value)
    if field == "fees":
        return _fee_fact_set(value)
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
    """Set of absolute calendar dates (``YYYY-MM-DD``) only.

    Only fully specified calendar dates are machine-verifiable and compared in
    the deterministic gate. Non-absolute / relative date tokens are deliberately
    excluded because the source and target extractors normalize them
    inconsistently and a faithful body still trips a false mismatch:
      - academic-year tokens ("2026학년도", "2026 academic year")
      - bare years ("2026", "2027") and year-month without a day ("2026-06")
      - fuzzy / relative phrases ("6월 중", "마감 시", "현재 접수 중",
        "위촉 후 ~ 2027", "until the deadline", "while supplies last")
    A genuine absolute-date change/omission is still caught because every real
    ``YYYY-MM-DD`` (including range endpoints) is compared.
    """
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        dates = _extract_iso_dates(flattened)
        if dates:
            normalized.update(dates)
        # Non-absolute tokens (academic-year, bare year, year-month, relative
        # phrases) are intentionally dropped from the deterministic gate.
    return normalized


def _time_fact_set(value: Any) -> set[str]:
    """Set of clock times-of-day (``HH:MM``) only.

    The ``times`` field mixes two different units that the source and target
    extractors group inconsistently:
      - clock time-of-day ("19:30", "09:00", a "19:30~20:10" range)
      - duration / elapsed time ("40 minutes", "40분", "1 hour")
    Only clock times are compared deterministically. Durations are dropped here
    because they are frequently redundant with a clock range (19:30-20:10 == 40
    minutes) and the two sides express them asymmetrically, which produced false
    "new critical value" mismatches. A genuine clock-time change/omission is
    still caught because every ``HH:MM`` is compared. Range separators
    ("~", "-", "to") expand to their endpoint clock times.
    """
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        normalized.update(_extract_clock_times(flattened))
        # Bare durations (e.g. "40 minutes") are intentionally not gated.
    return normalized


def _extract_clock_times(value: str) -> set[str]:
    times: set[str] = set()
    for match in re.finditer(r"\b(\d{1,2}):(\d{2})\b", value):
        hour = int(match.group(1))
        minute = match.group(2)
        if 0 <= hour <= 23 and 0 <= int(minute) <= 59:
            times.add(f"{hour:02d}:{minute}")
    return times


def _contact_fact_set(value: Any) -> set[str]:
    """Compare contacts only by machine-verifiable tokens (phone/email/url).

    A contact entry such as "인천광역시교육청 안전복지과" (an organization name
    with no number or email) is not machine-verifiable: the source keeps it in
    Korean while the translation renders it in the target language, so a literal
    string comparison always reports a false mismatch. Such prose-only contacts
    are validated by the LLM/context-tone stage, not by this deterministic gate,
    so we drop them here instead of letting them fail every notice.
    """
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        tokens = _extract_contact_tokens(flattened)
        normalized.update(tokens)
    return normalized


def _grade_target_set(value: Any) -> set[str]:
    """Set of machine-verifiable *target grade* tokens only (``grade:<n>``).

    Two normalization asymmetries previously made almost every table/recruitment
    notice fail:
      1. **Class labels vs target grades.** A table header such as "A반"/"Class A"
         is a class (section) identifier, not a target grade. The source files it
         in Korean ("A반") while the target renders "Class A", so they never
         string-match, and the embedded grade list ("1, 2, 3학년") was only
         partly extracted. We now extract *every* grade number in an entry and
         compare those, and we drop the class label itself from the gate (the
         class identifier is not a parent-actionable fact and is verified by the
         body/LLM stage).
      2. **Prose-only eligibility targets.** Entries with no numeric grade
         (e.g. "시민기자단 30명", "youth residing in Incheon", "adults except
         current journalists") are descriptive eligibility text: the source is
         Korean and the target is the translated language, so a literal string
         compare always mismatches. These are dropped from the deterministic
         gate (like prose-only contacts) and verified by the LLM/context-tone
         stage instead.
    A real target-grade omission or over-expansion (e.g. source grade:3 but
    translation says grades 1, 2, 3 with no class context) is still caught.
    """
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        grades = _extract_grade_tokens(flattened)
        normalized.update(grades)
        # Entries with no grade token (prose eligibility, class-only labels) are
        # intentionally not gated.
    return normalized


def _url_fact_set(value: Any) -> set[str]:
    """Compare URLs by a canonical form (lowercased scheme+host, path preserved).

    The translation must keep URLs verbatim, but the source and target
    extractors may differ in trailing slashes or scheme/host casing. Canonical
    comparison absorbs those cosmetic differences while still catching a changed
    path or domain.
    """
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        urls = _extract_urls(flattened)
        if urls:
            normalized.update(urls)
            continue
        if flattened:
            normalized.add(_normalize_fact(flattened))
    return normalized


def _fee_fact_set(value: Any) -> set[str]:
    """Compare fees with a shared 'no cost' equivalence class.

    The source extractor commonly emits "free"/"무료" while the target extractor
    may emit "0", "0 KRW", "Бесплатно", "مجانية", etc. for the same fact. These
    collapse to a single ``free`` token. Other (priced) fees are compared by
    their digit string so currency-symbol/spacing differences do not mismatch.
    """
    if not isinstance(value, list):
        return set()

    normalized: set[str] = set()
    for item in value:
        flattened = _machine_verifiable_value(item)
        token = _normalize_fee(flattened)
        if token:
            normalized.add(token)
    return normalized


# Phrases that describe "no cost to the parent" without a "free"/"0" token.
# The Korean side emits "무료"/"free" while the target side sometimes renders the
# funding model instead (e.g. "fully supported/funded by the Office of
# Education", "전액 지원", "무상"), which is the same fact for the parent. These
# collapse to the ``free`` equivalence class so a faithful body does not trip a
# fee mismatch. (Extension of the iter-001 free-equivalence work.)
_NO_COST_PHRASE_MARKERS = (
    "fully supported",
    "fully funded",
    "fully covered",
    "free of charge",
    "전액 지원",
    "전액지원",
    "무상",
)


def _normalize_fee(value: str) -> str:
    norm = _normalize_fact(value)
    if not norm:
        return ""
    if norm in _FREE_OF_CHARGE_TOKENS:
        return "free"
    if any(marker in norm for marker in _NO_COST_PHRASE_MARKERS):
        return "free"
    digits = re.sub(r"\D", "", norm)
    # "0", "0 krw", "krw 0" etc. all mean no cost.
    if digits and int(digits) == 0:
        return "free"
    if digits:
        return f"amount:{int(digits)}"
    return norm


def _extract_urls(value: str) -> set[str]:
    urls: set[str] = set()
    for match in re.finditer(r"https?://[^\s)>\]\"']+", value):
        raw = match.group(0).rstrip(".,;")
        # split into scheme+authority (lowercase) and path (case-sensitive)
        m = re.match(r"(https?://[^/]+)(/.*)?$", raw)
        if not m:
            continue
        authority = m.group(1).lower()
        path = (m.group(2) or "").rstrip("/")
        urls.add(f"{authority}{path}")
    return urls


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

    # Also pick up URLs embedded inside contact entries (e.g. a Kakao chat link).
    tokens.update(_extract_urls(value))

    for phone in re.findall(r"\+?\d[\d\-\s().]{7,}\d", value):
        digits = re.sub(r"\D", "", phone)
        if len(digits) >= 8:
            tokens.add(f"phone:{_canonical_phone_digits(digits)}")

    return tokens


def _canonical_phone_digits(digits: str) -> str:
    """Canonicalize a Korean phone number so national and international forms match.

    The source extractor keeps the national form ``032-320-0096`` →
    ``0323200096`` while the target extractor sometimes renders the same number
    in international form ``+82 32-320-0096`` → ``82323200096``. Both describe one
    number, so we strip the +82 country code and restore the national leading 0,
    yielding a single canonical key. Non-Korean numbers are returned unchanged.
    """
    if digits.startswith("82"):
        rest = digits[2:]
        # International form drops the national trunk "0"; restore it.
        if not rest.startswith("0"):
            rest = "0" + rest
        return rest
    return digits


def _extract_grade_tokens(value: str) -> set[str]:
    """Extract every target-grade number from an entry as ``grade:<n>`` tokens.

    Handles comma lists ("grades 1, 2, 3", "1, 2, 3학년"), ordinal forms
    ("1st/2nd/3rd grade"), the Korean "N학년", and the pre-normalized
    "grade:<n>" form the extractor sometimes emits. Class-section labels
    ("A반", "Class A", "class a~d") are intentionally NOT turned into grade
    tokens — they describe a section, not a target grade.
    """
    normalized = _normalize_fact(value)
    tokens: set[str] = set()

    # Pre-normalized "grade:3" form.
    for match in re.finditer(r"grade:\s*(\d+)", normalized):
        tokens.add(f"grade:{match.group(1)}")
    # Ordinal list ending in "grade(s)": "1st, 2nd, 3rd grade" — the trailing
    # "grade" applies to the whole ordinal list.
    for match in re.finditer(
        r"((?:\d+\s*(?:st|nd|rd|th)\s*[,/&]\s*|and\s*)*\d+\s*(?:st|nd|rd|th))\s*grades?",
        normalized,
    ):
        for num in re.findall(r"\d+", match.group(1)):
            tokens.add(f"grade:{num}")
    # Single ordinal grade: "3rd grade".
    for match in re.finditer(r"(\d+)\s*(?:st|nd|rd|th)\s*grade", normalized):
        tokens.add(f"grade:{match.group(1)}")
    # "grade 1", "grades 1, 2, 3".
    for match in re.finditer(r"grades?\s*((?:\d+\s*[,/&]\s*|and\s*|\d+\s*)+)", normalized):
        for num in re.findall(r"\d+", match.group(1)):
            tokens.add(f"grade:{num}")
    # Korean "1, 2, 3학년" (the trailing 학년 applies to the whole list).
    for match in re.finditer(r"((?:\d+\s*[,/&·]\s*)*\d+)\s*학년", normalized):
        for num in re.findall(r"\d+", match.group(1)):
            tokens.add(f"grade:{num}")
    if not tokens and re.fullmatch(r"\d+", normalized):
        tokens.add(f"grade:{normalized}")

    return tokens
