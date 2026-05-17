from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = {
    "월": 0,
    "화": 1,
    "수": 2,
    "목": 3,
    "금": 4,
    "토": 5,
    "일": 6,
}

EXPLICIT_DATE_RE = re.compile(
    r"(?P<year>20\d{2})\s*(?:년|[./-])\s*"
    r"(?P<month>\d{1,2})\s*(?:월|[./-])\s*"
    r"(?P<day>\d{1,2})\s*일?"
)
KOREAN_MONTH_DAY_RE = re.compile(r"(?<![\d./-])(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일?")
SLASH_MONTH_DAY_RE = re.compile(r"(?<![\d./-])(?P<month>\d{1,2})\s*[/.]\s*(?P<day>\d{1,2})(?!\s*[./-]\s*\d)")
TIME_RE = re.compile(
    r"(?:(?P<ampm>오전|오후)\s*)?(?P<hour>\d{1,2})\s*시(?:\s*(?P<minute>\d{1,2})\s*분?)?"
    r"|(?<!\d)(?P<hour24>\d{1,2}):(?P<minute24>\d{2})(?!\d)"
)
RELATIVE_DAY_RE = re.compile(r"(오늘|내일|모레)")
WEEKDAY_RE = re.compile(r"(?:(이번|다음)\s*주\s*)?([월화수목금토일])요일")


@dataclass(frozen=True)
class _DateCandidate:
    value: datetime
    start: int
    end: int


def parse_korean_deadline(text: str | None, *, reference: datetime | str | None = None) -> datetime | None:
    if not text:
        return None
    reference_dt = _reference_datetime(reference)
    normalized = _normalize_text(text)
    time_part = _parse_time(normalized)

    candidates = _date_candidates(normalized, reference_dt, time_part)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.value, item.start)).value


def _date_candidates(text: str, reference: datetime, time_part: tuple[int, int] | None) -> list[_DateCandidate]:
    candidates: list[_DateCandidate] = []
    explicit_year: int | None = None

    for match in EXPLICIT_DATE_RE.finditer(text):
        year = int(match.group("year"))
        explicit_year = explicit_year or year
        candidate = _safe_datetime(year, int(match.group("month")), int(match.group("day")), time_part)
        if candidate:
            candidates.append(_DateCandidate(candidate, match.start(), match.end()))

    inherited_year = explicit_year
    for pattern in (KOREAN_MONTH_DAY_RE, SLASH_MONTH_DAY_RE):
        for match in pattern.finditer(text):
            if _overlaps_existing(match.start(), match.end(), candidates):
                continue
            month = int(match.group("month"))
            day = int(match.group("day"))
            year = inherited_year or _next_occurrence_year(reference, month, day)
            candidate = _safe_datetime(year, month, day, time_part)
            if candidate:
                candidates.append(_DateCandidate(candidate, match.start(), match.end()))

    relative = _relative_day_candidate(text, reference, time_part)
    if relative:
        candidates.append(relative)

    weekday = _weekday_candidate(text, reference, time_part)
    if weekday:
        candidates.append(weekday)

    return candidates


def _relative_day_candidate(text: str, reference: datetime, time_part: tuple[int, int] | None) -> _DateCandidate | None:
    match = RELATIVE_DAY_RE.search(text)
    if not match:
        return None
    offset = {"오늘": 0, "내일": 1, "모레": 2}[match.group(1)]
    base = reference + timedelta(days=offset)
    hour, minute = time_part or (0, 0)
    return _DateCandidate(base.replace(hour=hour, minute=minute, second=0, microsecond=0), match.start(), match.end())


def _weekday_candidate(text: str, reference: datetime, time_part: tuple[int, int] | None) -> _DateCandidate | None:
    match = WEEKDAY_RE.search(text)
    if not match:
        return None
    prefix = match.group(1) or ""
    target_weekday = WEEKDAYS[match.group(2)]
    days_until = target_weekday - reference.weekday()
    if prefix == "다음":
        days_until += 7
    elif days_until < 0:
        days_until += 7
    base = reference + timedelta(days=days_until)
    hour, minute = time_part or (0, 0)
    return _DateCandidate(base.replace(hour=hour, minute=minute, second=0, microsecond=0), match.start(), match.end())


def _parse_time(text: str) -> tuple[int, int] | None:
    match = TIME_RE.search(text)
    if not match:
        return None
    if match.group("hour24"):
        hour = int(match.group("hour24"))
        minute = int(match.group("minute24"))
    else:
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        ampm = match.group("ampm")
        if ampm == "오후" and hour < 12:
            hour += 12
        elif ampm == "오전" and hour == 12:
            hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _reference_datetime(value: datetime | str | None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.now(UTC)
    else:
        parsed = datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _next_occurrence_year(reference: datetime, month: int, day: int) -> int:
    candidate = _safe_datetime(reference.year, month, day, None)
    if candidate is None:
        return reference.year
    if candidate.date() < reference.date():
        return reference.year + 1
    return reference.year


def _safe_datetime(year: int, month: int, day: int, time_part: tuple[int, int] | None) -> datetime | None:
    hour, minute = time_part or (0, 0)
    try:
        return datetime(year, month, day, hour, minute, tzinfo=KST)
    except ValueError:
        return None


def _overlaps_existing(start: int, end: int, candidates: list[_DateCandidate]) -> bool:
    return any(start < item.end and item.start < end for item in candidates)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def to_iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
