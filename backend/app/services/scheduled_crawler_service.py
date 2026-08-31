from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.services.school_crawler_service import (
    SchoolBoardDiscoveryResult,
    SchoolCrawlerService,
)

LOGGER = logging.getLogger(__name__)

UNSUPPORTED_STATUSES = {
    "unsupported_login_required",
    "unsupported_forbidden",
    "unsupported_external_dynamic",
}


@dataclass(frozen=True)
class ScheduledSchoolTarget:
    school_id: str
    school_name: str
    crawl_status: str | None
    crawl_last_checked_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "school_id": self.school_id,
            "school_name": self.school_name,
            "crawl_status": self.crawl_status,
            "crawl_last_checked_at": (
                self.crawl_last_checked_at.isoformat()
                if self.crawl_last_checked_at
                else None
            ),
        }


@dataclass(frozen=True)
class ScheduledSchoolResult:
    school_id: str
    school_name: str
    status: str
    success_count: int
    error_message: str | None
    # 어느 게시판을 봤는가. announcement_fallback = 가정통신문 게시판을 못 찾아
    # 공지사항 게시판으로 대체했다는 뜻이다. 글은 긁히므로 status 는 success 다.
    board_kind: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduledCrawlerSummary:
    started_at: str
    finished_at: str
    dry_run: bool
    force: bool
    total_registered: int
    selected_count: int
    skipped_count: int
    processed_count: int
    success_count: int
    failure_count: int
    fallback_count: int
    success_rate: float
    alarm: bool
    targets: list[dict[str, Any]]
    results: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def exit_code(self) -> int:
        return 1 if self.alarm else 0


class ScheduledCrawlerService:
    def __init__(
        self,
        crawler: SchoolCrawlerService | None = None,
    ) -> None:
        self._crawler = crawler or SchoolCrawlerService()

    async def run(
        self,
        *,
        school_id: str | None = None,
        limit: int | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> ScheduledCrawlerSummary:
        settings = get_settings()
        started_at = _utc_now()
        selected, skipped, total_registered = select_school_targets(
            school_id=school_id,
            limit=limit,
            force=force,
            unsupported_recheck_hours=settings.crawler_unsupported_recheck_hours,
            now=started_at,
        )

        if dry_run:
            return _build_summary(
                started_at=started_at,
                dry_run=True,
                force=force,
                total_registered=total_registered,
                selected=selected,
                skipped=skipped,
                results=[],
                fail_rate_threshold=settings.crawler_schedule_fail_rate_threshold,
            )

        semaphore = asyncio.Semaphore(settings.crawler_schedule_concurrency)

        async def run_one(target: ScheduledSchoolTarget) -> ScheduledSchoolResult:
            async with semaphore:
                return await self._run_target(target)

        results = await asyncio.gather(*(run_one(target) for target in selected))
        return _build_summary(
            started_at=started_at,
            dry_run=False,
            force=force,
            total_registered=total_registered,
            selected=selected,
            skipped=skipped,
            results=results,
            fail_rate_threshold=settings.crawler_schedule_fail_rate_threshold,
        )

    async def _run_target(self, target: ScheduledSchoolTarget) -> ScheduledSchoolResult:
        settings = get_settings()
        try:
            result = await self._crawler.discover_and_save_school_board(
                target.school_id,
                max_posts=settings.crawler_schedule_notice_count,
                use_gemini=settings.crawler_enable_gemini,
            )
            item = _result_item(target, result)
            LOGGER.info(
                "scheduled school crawler result: school_id=%s status=%s success_count=%s",
                item.school_id,
                item.status,
                item.success_count,
            )
            return item
        except Exception as exc:  # noqa: BLE001 - one school must not stop the job.
            LOGGER.exception(
                "scheduled school crawler failed: school_id=%s",
                target.school_id,
            )
            return ScheduledSchoolResult(
                school_id=target.school_id,
                school_name=target.school_name,
                status="internal_error",
                success_count=0,
                error_message=f"{type(exc).__name__}: {exc}",
            )


def select_school_targets(
    *,
    school_id: str | None,
    limit: int | None,
    force: bool,
    unsupported_recheck_hours: int,
    now: datetime | None = None,
) -> tuple[list[ScheduledSchoolTarget], list[ScheduledSchoolTarget], int]:
    now = now or _utc_now()
    targets = (
        _fetch_single_school_target(school_id)
        if school_id
        else _fetch_registered_school_targets()
    )
    total_registered = len(targets)
    sorted_targets = sorted(targets, key=_target_sort_key)

    selected: list[ScheduledSchoolTarget] = []
    skipped: list[ScheduledSchoolTarget] = []
    for target in sorted_targets:
        if should_crawl_school(
            target,
            now=now,
            force=force,
            unsupported_recheck_hours=unsupported_recheck_hours,
        ):
            selected.append(target)
        else:
            skipped.append(target)

    if limit is not None:
        selected = selected[:limit]

    return selected, skipped, total_registered


def should_crawl_school(
    target: ScheduledSchoolTarget,
    *,
    now: datetime,
    force: bool,
    unsupported_recheck_hours: int,
) -> bool:
    if force:
        return True

    if target.crawl_status not in UNSUPPORTED_STATUSES:
        return True

    if target.crawl_last_checked_at is None:
        return True

    return now - target.crawl_last_checked_at >= timedelta(
        hours=unsupported_recheck_hours,
    )


def _fetch_registered_school_targets() -> list[ScheduledSchoolTarget]:
    supabase = get_supabase_client()
    children = supabase.table("children").select("school_id").execute().data or []
    school_ids = sorted(
        {
            str(row["school_id"])
            for row in children
            if row.get("school_id")
        },
    )
    if not school_ids:
        return []

    rows: list[dict[str, Any]] = []
    for chunk in _chunks(school_ids, 100):
        schools_result = (
            supabase.table("schools")
            .select("id,name")
            .in_("id", chunk)
            .execute()
        )
        states_result = (
            supabase.table("school_crawl_state")
            .select("school_id,crawl_status,crawl_last_checked_at")
            .in_("school_id", chunk)
            .execute()
        )
        states = {
            str(row.get("school_id") or ""): row
            for row in (states_result.data or [])
            if row.get("school_id")
        }
        for row in schools_result.data or []:
            merged = dict(row)
            merged.update(states.get(str(row.get("id") or ""), {}))
            rows.append(merged)

    return [_target_from_row(row) for row in rows if row.get("id")]


def _fetch_single_school_target(school_id: str) -> list[ScheduledSchoolTarget]:
    supabase = get_supabase_client()
    school_result = (
        supabase
        .table("schools")
        .select("id,name")
        .eq("id", school_id)
        .limit(1)
        .execute()
    )
    rows = school_result.data or []
    if not rows:
        return []
    state_result = (
        supabase.table("school_crawl_state")
        .select("school_id,crawl_status,crawl_last_checked_at")
        .eq("school_id", school_id)
        .limit(1)
        .execute()
    )
    merged = dict(rows[0])
    if state_result.data:
        merged.update(dict(state_result.data[0]))
    return [_target_from_row(merged)]


def _target_from_row(row: dict[str, Any]) -> ScheduledSchoolTarget:
    return ScheduledSchoolTarget(
        school_id=str(row.get("id") or ""),
        school_name=str(row.get("name") or ""),
        crawl_status=_optional_str(row.get("crawl_status")),
        crawl_last_checked_at=_parse_datetime(row.get("crawl_last_checked_at")),
    )


def _target_sort_key(target: ScheduledSchoolTarget) -> tuple[int, datetime, str]:
    checked_at = target.crawl_last_checked_at
    return (
        0 if checked_at is None else 1,
        checked_at or datetime.min.replace(tzinfo=UTC),
        target.school_id,
    )


def _result_item(
    target: ScheduledSchoolTarget,
    result: SchoolBoardDiscoveryResult,
) -> ScheduledSchoolResult:
    return ScheduledSchoolResult(
        school_id=result.school_id,
        school_name=result.school_name or target.school_name,
        status=result.status,
        success_count=result.success_count,
        error_message=result.error_message,
        board_kind=result.board_kind,
    )


def _build_summary(
    *,
    started_at: datetime,
    dry_run: bool,
    force: bool,
    total_registered: int,
    selected: list[ScheduledSchoolTarget],
    skipped: list[ScheduledSchoolTarget],
    results: list[ScheduledSchoolResult],
    fail_rate_threshold: float,
) -> ScheduledCrawlerSummary:
    finished_at = _utc_now()
    processed = len(results)
    success_count = sum(1 for item in results if item.status == "success")
    failure_count = processed - success_count
    success_rate = success_count / processed if processed else 1.0
    alarm = bool(processed and success_rate < fail_rate_threshold)

    # 게시판 오선택은 실패가 아니다 — 그 학교는 공지를 실제로 받고 있다.
    # 실패로 세면 fail_rate 알람이 오작동해 학부모가 아무것도 못 받게 된다.
    # 성공률 정의를 바꾸지 않고 따로 센다. 학교가 8곳이라 숫자 하나면 눈으로 판정된다.
    fallback_schools = [item.school_name for item in results if item.board_kind == "announcement_fallback"]
    if fallback_schools:
        LOGGER.warning(
            "scheduled crawler board fallback: count=%s schools=%s",
            len(fallback_schools),
            ",".join(fallback_schools),
        )

    return ScheduledCrawlerSummary(
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        dry_run=dry_run,
        force=force,
        total_registered=total_registered,
        selected_count=len(selected),
        skipped_count=len(skipped),
        processed_count=processed,
        success_count=success_count,
        failure_count=failure_count,
        fallback_count=len(fallback_schools),
        success_rate=round(success_rate, 4),
        alarm=alarm,
        targets=[target.to_dict() for target in selected],
        results=[item.to_dict() for item in results],
    )


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _utc_now() -> datetime:
    return datetime.now(UTC)
