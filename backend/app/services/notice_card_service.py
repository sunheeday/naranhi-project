from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client


LOGGER = logging.getLogger(__name__)
CARD_META_SOURCE = "extracted_content"
SUMMARY_FACT_LIMIT = 3
CARD_ORDER = {
    "summary": 0,
    "action": 1,
    "schedule": 2,
    "supplies": 3,
    "info": 4,
}


@dataclass(frozen=True)
class NoticeCardItem:
    text: str
    hint: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {"text": self.text}
        if self.hint:
            payload["hint"] = self.hint
        return payload


@dataclass(frozen=True)
class GeneratedNoticeCard:
    type: str
    content: dict[str, Any]
    order: int

    def to_insert(self, notice_id: str) -> dict[str, Any]:
        return {
            "notice_id": notice_id,
            "type": self.type,
            "content": self.content,
            "order": self.order,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NoticeCardBackfillSummary:
    dry_run: bool
    notice_id: str | None
    limit: int
    scanned_count: int
    updated_count: int
    skipped_count: int
    results: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_notice_cards_from_extracted_content(extracted_content: Any) -> list[GeneratedNoticeCard]:
    canonical = _canonical_summary(extracted_content)
    confidence = _float_or_none(canonical.get("confidence"))
    cards: list[GeneratedNoticeCard] = []

    key_facts = _string_list(canonical.get("key_facts"))
    summary_items = _summary_items(canonical, key_facts[:SUMMARY_FACT_LIMIT])
    if summary_items:
        cards.append(_card("summary", summary_items, confidence=confidence))

    action_items = _action_items(canonical)
    if action_items:
        cards.append(_card("action", action_items, confidence=confidence))

    schedule_items = _schedule_items(canonical)
    if schedule_items:
        cards.append(_card("schedule", schedule_items, confidence=confidence))

    supply_items = _items_from_values(_string_list(canonical.get("preparation_items")))
    if supply_items:
        cards.append(_card("supplies", supply_items, confidence=confidence))

    info_items = _info_items(canonical, key_facts[SUMMARY_FACT_LIMIT:])
    if info_items:
        cards.append(_card("info", info_items, confidence=confidence))

    return cards


def replace_notice_cards(notice_id: str, extracted_content: Any) -> int:
    cards = build_notice_cards_from_extracted_content(extracted_content)
    supabase = get_supabase_client()
    supabase.table("notice_cards").delete().eq("notice_id", notice_id).execute()
    if not cards:
        return 0
    supabase.table("notice_cards").insert([card.to_insert(notice_id) for card in cards]).execute()
    return len(cards)


def run_notice_card_backfill(
    *,
    notice_id: str | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> NoticeCardBackfillSummary:
    _ensure_supabase_configured()
    rows = _fetch_backfill_targets(notice_id=notice_id, limit=limit)
    results: list[dict[str, Any]] = []
    updated_count = 0
    skipped_count = 0

    for row in rows:
        row_notice_id = str(row.get("id") or "")
        cards = build_notice_cards_from_extracted_content(row.get("extracted_content"))
        if not row_notice_id or not cards:
            skipped_count += 1
            results.append({"notice_id": row_notice_id, "card_count": 0, "status": "skipped"})
            continue

        if not dry_run:
            replace_notice_cards(row_notice_id, row.get("extracted_content"))
        updated_count += 1
        results.append(
            {
                "notice_id": row_notice_id,
                "card_count": len(cards),
                "types": [card.type for card in cards],
                "status": "would_update" if dry_run else "updated",
            }
        )

    return NoticeCardBackfillSummary(
        dry_run=dry_run,
        notice_id=notice_id,
        limit=limit,
        scanned_count=len(rows),
        updated_count=updated_count,
        skipped_count=skipped_count,
        results=results,
    )


def _fetch_backfill_targets(*, notice_id: str | None, limit: int) -> list[dict[str, Any]]:
    query = (
        get_supabase_client()
        .table("notices")
        .select("id,extracted_content")
        .eq("source", "crawl")
        .eq("status", "done")
    )
    if notice_id:
        query = query.eq("id", notice_id)
    elif limit > 0:
        query = query.limit(limit)
    rows = query.execute().data or []
    return [row for row in rows if _canonical_summary(row.get("extracted_content"))]


def _ensure_supabase_configured() -> None:
    settings = get_settings()
    missing = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")


def _canonical_summary(extracted_content: Any) -> dict[str, Any]:
    if not isinstance(extracted_content, dict):
        return {}
    canonical = extracted_content.get("canonical_summary")
    return canonical if isinstance(canonical, dict) else {}


def _summary_items(canonical: dict[str, Any], key_facts: list[str]) -> list[NoticeCardItem]:
    values = []
    summary = _clean_text(canonical.get("summary_oneliner"))
    if summary:
        values.append(summary)
    values.extend(key_facts)
    return _items_from_values(values)


def _action_items(canonical: dict[str, Any]) -> list[NoticeCardItem]:
    deadline = _clean_text(canonical.get("deadline"))
    values: list[str] = []
    values.extend(_string_list(canonical.get("required_actions")))
    values.extend(_string_list(canonical.get("forms_to_submit")))
    values.extend(_prefixed_values("비용", canonical.get("fees")))
    return _items_from_values(values, hint=deadline)


def _schedule_items(canonical: dict[str, Any]) -> list[NoticeCardItem]:
    values: list[str] = []
    values.extend(_string_list(canonical.get("important_dates")))
    values.extend(_string_list(canonical.get("activity_summary")))
    values.extend(_prefixed_values("장소", canonical.get("locations")))
    return _items_from_values(values)


def _info_items(canonical: dict[str, Any], remaining_key_facts: list[str]) -> list[NoticeCardItem]:
    values: list[str] = []
    values.extend(_string_list(canonical.get("supplement_summary")))
    values.extend(_prefixed_values("연락처", canonical.get("contacts")))
    values.extend(_prefixed_values("대상", canonical.get("targets")))
    values.extend(_prefixed_values("주의", canonical.get("warnings")))
    values.extend(_prefixed_values("링크", canonical.get("links")))
    values.extend(remaining_key_facts)
    return _items_from_values(values)


def _card(card_type: str, items: list[NoticeCardItem], *, confidence: float | None) -> GeneratedNoticeCard:
    meta: dict[str, Any] = {"source": CARD_META_SOURCE}
    if confidence is not None:
        meta["confidence"] = confidence
    return GeneratedNoticeCard(
        type=card_type,
        order=CARD_ORDER[card_type],
        content={
            "items": [item.to_dict() for item in items],
            "meta": meta,
        },
    )


def _items_from_values(values: list[str], *, hint: str | None = None) -> list[NoticeCardItem]:
    items: list[NoticeCardItem] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(NoticeCardItem(text=text, hint=hint))
    return items


def _prefixed_values(prefix: str, value: Any) -> list[str]:
    return [f"{prefix}: {item}" for item in _string_list(value)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _clean_text(value)
        return [text] if text else []
    if isinstance(value, dict):
        text = _string_from_mapping(value)
        return [text] if text else []
    if isinstance(value, list | tuple | set):
        result: list[str] = []
        for item in value:
            result.extend(_string_list(item))
        return result
    text = _clean_text(value)
    return [text] if text else []


def _string_from_mapping(value: dict[Any, Any]) -> str:
    preferred_keys = ("text", "title", "name", "date", "deadline", "amount", "url", "href", "phone", "email")
    parts: list[str] = []
    for key in preferred_keys:
        if key in value:
            text = _clean_text(value.get(key))
            if text:
                parts.append(text)
    if not parts:
        parts = [f"{key}: {_clean_text(item)}" for key, item in value.items() if _clean_text(item)]
    return " · ".join(parts)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).replace("\r", "\n").split())
    return text.strip()


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
