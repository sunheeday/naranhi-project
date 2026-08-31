from __future__ import annotations

import re
import unicodedata
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


# ---------------------------------------------------------------------------
# 산출물 코드 검사 — AI 를 부르지 않는다.
#
# 왜 있는가: 2026-08-30 실측에서 베트남어 번역본에 「일회용」이 한글 그대로 남았다.
# 이런 결함에 AI 검증자를 붙이는 것은 낭비다 — 정규식이면 0원·0초이고 절대 안 놓친다.
# LLM 검증자는 «코드가 원리상 못 하는 것»(의미·어조·문화적 적절성)만 맡는다.
#
# 무게가 다르다: 사실·가독성 위반은 재시도(failed), 구조·반복은 경고(warned)다.
# 사소한 지적으로 재번역을 돌리면 돈만 나가고 하드팩트가 깨질 수 있다.
# ---------------------------------------------------------------------------

_HANGUL_RUN = re.compile(r"[가-힣]{2,}")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S", re.MULTILINE)

# 원문 대비 이 비율보다 짧으면 잘린 것으로 본다. 언어별 길이 차이를 감안해 넉넉히 잡는다
# (한국어는 압축적이라 번역본이 보통 «길어진다» — 40% 미만은 정상 범위가 아니다).
_MIN_LENGTH_RATIO = 0.40
# 목록·제목이 이 비율 미만으로 남으면 항목이 빠진 것으로 본다.
_MIN_STRUCTURE_RATIO = 0.60
# 같은 줄이 이 횟수 이상 반복되면 모델이 루프를 돈 것이다.
_MAX_LINE_REPEAT = 3
# 짧은 줄의 반복은 목록에서 정상이라 길이 기준을 둔다.
_REPEAT_MIN_LINE_LENGTH = 20

# 천단위 구분자가 붙은 수, 또는 맨 숫자. 구분자는 «뒤에 정확히 3자리» 일 때만 인정한다 —
# 그래야 "2026. 5. 14." 를 2026514 로 붙이지 않는다.
_NUMBER = re.compile(r"\d{1,3}(?:[,.  ]\d{3})+|\d+")
# 4자리 미만은 보지 않는다. 인원수·학년·교시는 문장에 녹아 사라지는 것이 정상이다.
_MIN_NUMBER_DIGITS = 4

BLOCKING_CODES = frozenset(
    {"empty_output", "hangul_leftover", "too_short", "numbers_lost"}
)


def _to_ascii_digits(text: str) -> str:
    """아랍어(٢٠٢٦)·태국어(๒๐๒๖) 숫자를 ASCII 로 맞춘다.
    지원 언어에 아랍어·태국어가 있어 이걸 안 하면 «숫자가 사라졌다» 는 오탐이 난다."""
    if not text:
        return ""
    out = []
    for ch in text:
        if ch.isdigit() and not ("0" <= ch <= "9"):
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except (TypeError, ValueError):
                pass
        out.append(ch)
    return "".join(out)


def _significant_numbers(text: str) -> set[str]:
    """금액·전화번호처럼 «틀리면 안 되는» 수만 뽑아 표기를 지운다.
    2,240,000 과 2.240.000 과 2 240 000 과 ٢٬٢٤٠٬٠٠٠ 은 같은 값으로 본다."""
    out: set[str] = set()
    for raw in _NUMBER.findall(_to_ascii_digits(text)):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= _MIN_NUMBER_DIGITS:
            out.add(digits.lstrip("0") or "0")
    return out


def validate_output_by_code(
    *,
    source_text: str,
    translated_text: str,
    target_language: str,
) -> dict[str, Any]:
    """번역 산출물을 코드로만 검사한다. AI 호출 0회.

    status: passed | warned | failed
      failed  — 재시도해야 한다(학부모가 읽을 수 없거나 내용이 잘렸다)
      warned  — 기록만 한다(구조가 달라졌지만 읽는 데 지장 없다)
    """
    issues: list[dict[str, str]] = []
    source = source_text or ""
    out = translated_text or ""

    if not out.strip():
        return {
            "status": "failed",
            "issues": [{"code": "empty_output", "detail": "번역 결과가 비어 있습니다."}],
        }

    # ① 한글 잔존 — 대상 언어가 한국어가 아닌데 한글 덩어리가 남았다.
    if (target_language or "").strip().lower() != "ko":
        leftovers = _HANGUL_RUN.findall(out)
        if leftovers:
            uniq = sorted(set(leftovers))[:8]
            issues.append({
                "code": "hangul_leftover",
                "detail": f"번역본에 한글이 {len(leftovers)}곳 남았습니다: {', '.join(uniq)}",
            })

    # ② 길이 — 잘렸는가.
    if len(source.strip()) >= 200:
        ratio = len(out.strip()) / max(1, len(source.strip()))
        if ratio < _MIN_LENGTH_RATIO:
            issues.append({
                "code": "too_short",
                "detail": f"번역본이 원문의 {ratio:.0%}뿐입니다(기준 {_MIN_LENGTH_RATIO:.0%}).",
            })

    # ③ 구조 — 제목·목록 항목이 사라졌는가.
    for code, pattern, label in (
        ("headings_lost", _HEADING, "제목"),
        ("list_items_lost", _LIST_ITEM, "목록 항목"),
    ):
        src_n = len(pattern.findall(source))
        out_n = len(pattern.findall(out))
        if src_n >= 2 and out_n < src_n * _MIN_STRUCTURE_RATIO:
            issues.append({
                "code": code,
                "detail": f"{label}가 원문 {src_n}개 → 번역본 {out_n}개로 줄었습니다.",
            })

    # ④ 숫자 보존 — 금액·전화번호가 사라졌는가.
    #    실측(2026-08-31): LLM 사실검증이 표 셀의 계산식을 오추출해
    #    「번역은 맞는데 검증 실패」 오탐을 냈다. 원문/번역본의 숫자를 직접 대조하는
    #    이 검사가 그보다 정확하고, 0원·0초다.
    src_numbers = _significant_numbers(source)
    if src_numbers:
        missing = sorted(src_numbers - _significant_numbers(out))
        if missing:
            issues.append({
                "code": "numbers_lost",
                "detail": f"원문의 수 {len(missing)}개가 번역본에 없습니다: {', '.join(missing[:8])}",
            })

    # ⑤ 반복 — 모델이 같은 줄을 되풀이하며 돌았는가.
    counts: dict[str, int] = {}
    for line in out.splitlines():
        stripped = line.strip()
        if len(stripped) >= _REPEAT_MIN_LINE_LENGTH:
            counts[stripped] = counts.get(stripped, 0) + 1
    worst = max(counts.values(), default=0)
    if worst >= _MAX_LINE_REPEAT:
        repeated = next(k for k, v in counts.items() if v == worst)
        issues.append({
            "code": "repeated_line",
            "detail": f"같은 줄이 {worst}번 반복됩니다: {repeated[:60]}",
        })

    if not issues:
        return {"status": "passed", "issues": []}
    blocking = any(i["code"] in BLOCKING_CODES for i in issues)
    return {"status": "failed" if blocking else "warned", "issues": issues}
