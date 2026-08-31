from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
import logging
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.crawler.neis_client import NeisClient, SchoolScheduleEntry

LOGGER = logging.getLogger(__name__)

NEIS_SOURCE = "neis"


def academic_year_range(today: date) -> tuple[int, str, str]:
    """학년도 범위(3/1 ~ 이듬해 2월 말). 1·2월은 직전 학년도에 속한다."""
    year = today.year if today.month >= 3 else today.year - 1
    last_day = 29 if calendar.isleap(year + 1) else 28
    return year, f"{year}0301", f"{year + 1}02{last_day}"


def build_neis_event_rows(school_id: str, entries: list[SchoolScheduleEntry]) -> list[dict[str, Any]]:
    """NEIS 일정 → school_events 행.

    notice_id 는 null 이다 — 이어 붙일 공지가 없다. 그래서 이 행들은
    notice_service._replace_school_events_from_pipeline(:1137-1191)의 시야에
    들어오지 않고, 홈 화면 D-day 칩(app/(app)/page.tsx:337-343)의
    .in('notice_id', …) 필터에도 걸리지 않는다.
    """
    return [
        {
            "school_id": school_id,
            "notice_id": None,
            "title": entry.title,
            "event_date": entry.event_date,
            "end_date": None,
            "event_kinds": ["event"],
            "location": None,
            "description": entry.description,
            "source_language": "ko",
            "source": NEIS_SOURCE,
        }
        for entry in entries
    ]


@dataclass(frozen=True)
class SchoolScheduleSyncResult:
    school_id: str
    school_name: str
    status: str  # "synced" | "skipped_no_codes" | "failed"
    academic_year: int
    from_date: str
    to_date: str
    fetched_count: int
    deleted_count: int
    inserted_count: int
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SchoolScheduleSyncService:
    def __init__(self, client: NeisClient | None = None) -> None:
        settings = get_settings()
        self._client = client or NeisClient(
            settings.neis_api_key or "",
            timeout=settings.crawler_timeout_seconds,
        )

    async def sync_school(
        self,
        school: dict[str, Any],
        *,
        today: date | None = None,
    ) -> SchoolScheduleSyncResult:
        """한 학교의 학년도 학사일정을 전량 교체한다.

        NeisQuotaExceeded 는 잡지 않는다 — 호출한 배치가 남은 학교를 건너뛰도록
        위로 올린다(재시도 폭주 금지).
        """
        school_id = str(school.get("id") or "")
        school_name = str(school.get("name") or "")
        office_code = str(school.get("neis_office_code") or "").strip()
        school_code = str(school.get("neis_school_code") or "").strip()
        year, from_ymd, to_ymd = academic_year_range(today or datetime.now(UTC).date())
        from_date = _iso(from_ymd)
        to_date = _iso(to_ymd)

        if not school_id or not office_code or not school_code:
            return SchoolScheduleSyncResult(
                school_id=school_id,
                school_name=school_name,
                status="skipped_no_codes",
                academic_year=year,
                from_date=from_date,
                to_date=to_date,
                fetched_count=0,
                deleted_count=0,
                inserted_count=0,
                error_message="neis_office_code/neis_school_code 가 없습니다.",
            )

        entries = await self._client.fetch_school_schedule(
            office_code,
            school_code,
            from_ymd,
            to_ymd,
        )
        deleted, inserted = replace_neis_events(
            school_id=school_id,
            entries=entries,
            from_date=from_date,
            to_date=to_date,
        )
        return SchoolScheduleSyncResult(
            school_id=school_id,
            school_name=school_name,
            status="synced",
            academic_year=year,
            from_date=from_date,
            to_date=to_date,
            fetched_count=len(entries),
            deleted_count=deleted,
            inserted_count=inserted,
        )


def replace_neis_events(
    *,
    school_id: str,
    entries: list[SchoolScheduleEntry],
    from_date: str,
    to_date: str,
) -> tuple[int, int]:
    """source='neis' + 같은 학년도 범위만 전량 교체한다.

    🔴 delete 에서 .eq("source", NEIS_SOURCE) 를 빼면 공지에서 뽑은 일정
    (source='notice_ai')을 지운다. 이 조건 없이 delete 를 실행하지 않는다.

    upsert 를 쓰지 않는 이유: 0039 의 유니크는 부분 인덱스(where source='neis')라
    PostgREST 의 on_conflict 대상으로 추론되지 않는다. 삭제 후 삽입으로 교체하고,
    부분 인덱스는 동시 실행 시의 중복을 막는 가드로만 쓴다.
    """
    supabase = get_supabase_client()
    deleted = (
        supabase.table("school_events")
        .delete()
        .eq("school_id", school_id)
        .eq("source", NEIS_SOURCE)
        .gte("event_date", from_date)
        .lte("event_date", to_date)
        .execute()
        .data
        or []
    )

    rows = build_neis_event_rows(school_id, entries)
    if not rows:
        return len(deleted), 0

    inserted = supabase.table("school_events").insert(rows).execute().data or []
    return len(deleted), len(inserted)


def select_schedule_sync_targets() -> list[dict[str, Any]]:
    """자녀가 등록된 학교만 대상. scheduled_crawler_service._fetch_registered_school_targets 와 같은 기준."""
    supabase = get_supabase_client()
    children = supabase.table("children").select("school_id").execute().data or []
    school_ids = sorted({str(row["school_id"]) for row in children if row.get("school_id")})
    if not school_ids:
        return []

    rows: list[dict[str, Any]] = []
    for index in range(0, len(school_ids), 100):
        chunk = school_ids[index : index + 100]
        result = (
            supabase.table("schools")
            .select("id,name,neis_office_code,neis_school_code")
            .in_("id", chunk)
            .execute()
        )
        rows.extend(result.data or [])
    return rows


def _iso(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
