from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client


CARD_META_SOURCE = "extracted_content"
SUMMARY_ITEM_LIMIT = 8
RAW_SUMMARY_LINE_LIMIT = 220
CARD_ORDER = {
    "summary": 0,
}
NOISE_EXACT_LINES = {
    "내용",
    "내용을",
    "목록",
    "작성자",
    "등록일",
    "파일첨부",
    "다운로드",
    "이름",
    "제목",
    "no",
    "no.",
    "가정통신문 게시판 상세보기",
    "게시판 상세보기",
    "파일명",
    "파일형식",
    "파일크기",
    "조회수",
    "교훈",
    "가정",
    "통신",
    "직인생략",
    "다 주요내용",
    "주요내용",
    "운영회비 총괄표",
}
NOISE_CONTAINS = (
    "공익제보센터",
    "신고내용",
    "신고방법",
    "cleanedu@sen.go.kr",
    "1588-0260",
    "학교장",
    "공회 준비",
    "준비하세요",
    "비상대비물자 준비 요령",
    "우편번호",
    "홈페이지",
    "fax",
    "담당부서",
    "주관부서",
    "교무실",
    "행정실",
    "직인생략",
    "늘 학교에 관심",
    "감사의 마음",
)
GENERIC_TARGETS = {"학생", "학부모", "학부모님", "보호자"}
PRIORITY_KEY_FACT_TERMS = (
    "훈련기간",
    "훈련내용",
    "일시",
    "기간",
    "날짜",
    "시간",
    "체험 장소",
    "장소",
    "대상",
    "제출",
    "신청",
    "동의서",
    "지참",
    "준비물",
    "자녀에게",
    "확인해 주시기",
    "협조사항",
)
ACTION_TERMS = ("제출", "신청", "납부", "작성", "회신", "응답", "동의", "동의서", "지참", "확인")
RAW_PRIORITY_TERMS = (
    "훈련기간",
    "훈련내용",
    "출결사유",
    "출결처리",
    "주요내용",
    "대상:",
    "대상",
    "일시",
    "기간",
    "장소",
    "단축수업",
    "하교 시간",
    "운영 결과",
    "회비 납부",
    "납부 현황",
    "상세한 지출",
    "출석인정",
    "경조사",
    "제출",
    "신청",
    "동의서",
    "준비물",
    "지참",
    "확인해 주시",
    "지도하여 주시",
)
RAW_SECONDARY_TERMS = (
    "안내",
    "변경",
    "실시",
    "예정",
    "협조",
    "참여",
    "열람",
    "문의",
    "투명성",
    "운영",
    "포함하지 않습니다",
    "처리되지 않습니다",
)
RAW_STRONG_TERMS = ("훈련기간", "훈련내용", "출결사유", "출결처리", "대상:", "일시", "장소")


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
    return build_notice_cards(title=None, original_text=None, extracted_content=extracted_content)


def build_notice_cards(
    *,
    title: str | None,
    original_text: str | None,
    extracted_content: Any,
) -> list[GeneratedNoticeCard]:
    canonical = _canonical_summary(extracted_content)
    summary_card_items = _summary_card_items(extracted_content)
    summary_card_meta = _summary_card_meta(extracted_content)
    confidence = _float_or_none(summary_card_meta.get("confidence"))
    if confidence is None:
        confidence = _float_or_none(canonical.get("confidence"))
    cards: list[GeneratedNoticeCard] = []

    summary_items = summary_card_items or _summary_candidate_items(canonical, title=title, original_text=original_text)
    if summary_items:
        cards.append(
            _card(
                "summary",
                summary_items,
                confidence=confidence,
                source=str(summary_card_meta.get("source") or CARD_META_SOURCE),
                model=_clean_text(summary_card_meta.get("model")),
            )
        )

    return cards


def replace_notice_cards(
    notice_id: str,
    extracted_content: Any,
    *,
    title: str | None = None,
    original_text: str | None = None,
) -> int:
    cards = build_notice_cards(title=title, original_text=original_text, extracted_content=extracted_content)
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
        cards = build_notice_cards(
            title=_clean_text(row.get("title")),
            original_text=str(row.get("original_text") or ""),
            extracted_content=row.get("extracted_content"),
        )
        if not row_notice_id or not cards:
            skipped_count += 1
            results.append({"notice_id": row_notice_id, "card_count": 0, "status": "skipped"})
            continue

        if not dry_run:
            replace_notice_cards(
                row_notice_id,
                row.get("extracted_content"),
                title=_clean_text(row.get("title")),
                original_text=str(row.get("original_text") or ""),
            )
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
        .select("id,title,original_text,extracted_content")
        .eq("source", "crawl")
        .eq("status", "done")
        .order("id", desc=False)
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


def _summary_card_items(extracted_content: Any) -> list[NoticeCardItem]:
    if not isinstance(extracted_content, dict):
        return []
    summary_card = extracted_content.get("summary_card")
    if not isinstance(summary_card, dict):
        return []
    raw_items = summary_card.get("items")
    if not isinstance(raw_items, list):
        return []
    items: list[NoticeCardItem] = []
    for raw_item in raw_items:
        text = ""
        hint = None
        if isinstance(raw_item, dict):
            text = _clean_text(raw_item.get("text"))
            hint = _clean_text(raw_item.get("hint")) or None
        else:
            text = _clean_text(raw_item)
        if text:
            items.append(NoticeCardItem(text=text, hint=hint))
    return _dedupe_items(items)[:SUMMARY_ITEM_LIMIT]


def _summary_card_meta(extracted_content: Any) -> dict[str, Any]:
    if not isinstance(extracted_content, dict):
        return {}
    summary_card = extracted_content.get("summary_card")
    return summary_card if isinstance(summary_card, dict) else {}


def _summary_candidate_items(
    canonical: dict[str, Any],
    *,
    title: str | None,
    original_text: str | None,
) -> list[NoticeCardItem]:
    summary = _best_title(title, canonical)
    items: list[NoticeCardItem] = []
    if summary and not _noise_line(summary):
        items.append(NoticeCardItem(text=summary))

    raw_items = _raw_summary_items(original_text or "", title=summary)
    key_facts = _string_list(canonical.get("key_facts"))
    use_canonical_fallback = not raw_items
    labeled_items = _important_labeled_items(
        canonical,
        key_facts,
        allow_date_fallback=not raw_items and use_canonical_fallback,
    )
    fallback_items = _items_from_values(key_facts)
    if not use_canonical_fallback:
        return _dedupe_items([*items, *raw_items])[:SUMMARY_ITEM_LIMIT]
    return _dedupe_items([*items, *raw_items, *labeled_items, *fallback_items])[:SUMMARY_ITEM_LIMIT]


def _important_labeled_items(
    canonical: dict[str, Any],
    key_facts: list[str],
    *,
    allow_date_fallback: bool,
) -> list[NoticeCardItem]:
    values: list[str] = []
    priority_key_facts = _priority_key_fact_lines(key_facts)
    values.extend(_target_values(canonical.get("targets")))
    values.extend(priority_key_facts)
    if allow_date_fallback and not priority_key_facts:
        values.extend(_prefixed_values("일정", canonical.get("important_dates")))
    values.extend(_prefixed_values("장소", canonical.get("locations")))
    values.extend(_action_values(canonical.get("required_actions")))
    values.extend(_prefixed_values("제출", canonical.get("forms_to_submit")))
    values.extend(_prefixed_values("준비물", canonical.get("preparation_items")))
    values.extend(_prefixed_values("비용", canonical.get("fees")))
    values.extend(_prefixed_values("문의", canonical.get("contacts")))
    return _items_from_values(values)


def _best_title(title: str | None, canonical: dict[str, Any]) -> str:
    title_text = _clean_text(title)
    if title_text and not _noise_line(title_text):
        return title_text
    summary = _clean_text(canonical.get("summary_oneliner"))
    return summary if summary and not _noise_line(summary) else ""


def _raw_summary_items(original_text: str, *, title: str) -> list[NoticeCardItem]:
    lines = _meaningful_raw_lines(original_text, title=title)
    scored: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        display_line = _strip_greeting_prefix(line)
        score = _raw_line_score(display_line)
        if score <= 0:
            continue
        scored.append((score, index, display_line))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [line for _, _, line in scored[: SUMMARY_ITEM_LIMIT * 2]]
    return _items_from_values(selected)


def _meaningful_raw_lines(original_text: str, *, title: str) -> list[str]:
    raw_lines = [_normalize_raw_line(line) for line in original_text.splitlines()]
    raw_lines = _merge_wrapped_raw_lines(raw_lines)
    lines: list[str] = []
    for line in raw_lines:
        if not line:
            continue
        if _raw_line_is_noise(line, title=title):
            continue
        lines.append(line)
    return _dedupe_text_lines(lines)


def _merge_wrapped_raw_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    pending = ""
    for line in lines:
        if not line:
            if pending:
                merged.append(pending)
                pending = ""
            continue
        if pending and _should_join_raw_lines(pending, line):
            pending = _join_raw_lines(pending, line)
            continue
        if pending:
            merged.append(pending)
        pending = line
    if pending:
        merged.append(pending)
    return merged


def _should_join_raw_lines(previous: str, current: str) -> bool:
    if len(previous) + len(current) > RAW_SUMMARY_LINE_LIMIT:
        return False
    if _mostly_amount_or_table_fragment(previous) or _mostly_amount_or_table_fragment(current):
        return False
    if current.startswith(("래", "생", "의 ", "수 있도록", "방법을", "사항은", "내용을", "확인하시고", "싶으신")):
        return True
    if previous.endswith((" 아", " 학", " 운영", " 지출", " 기타 문의")):
        return True
    return False


def _join_raw_lines(previous: str, current: str) -> str:
    if previous.endswith(" 아") and current.startswith("래"):
        return f"{previous[:-2]} 아래{current[1:]}"
    if previous.endswith(" 학") and current.startswith("생"):
        return f"{previous[:-2]} 학생{current[1:]}"
    return f"{previous} {current}"


def _normalize_raw_line(line: str) -> str:
    text = _clean_text(line)
    if not text:
        return ""
    if text.startswith("[") and "]" in text:
        return ""
    if text == "---":
        return ""
    text = text.strip("<> ")
    text = text.replace("󰊱", "").replace("󰊵", "").replace("󰊳", "").replace("󰊷", "")
    text = " ".join(text.split())
    return text.strip()


def _raw_line_is_noise(line: str, *, title: str) -> bool:
    text = _clean_text(line)
    text = _strip_greeting_prefix(text)
    if _noise_line(text):
        return True
    if title and _same_or_subtitle(text, title):
        return True
    if _masked_name_line(text):
        return True
    if _date_only_line(text):
        return True
    if _heading_only_line(text):
        return True
    if _mostly_amount_or_table_fragment(text):
        return True
    if len(text) > RAW_SUMMARY_LINE_LIMIT:
        return True
    lower = text.lower()
    if any(token in lower for token in ("http://", "https://", "주소 :", "주소:", "fax", "홈페이지", "우편번호")):
        return True
    if text.startswith(("※ 안전한TV", "네이버 지도", "카카오맵", "티맵", "민방위대피소")):
        return True
    return False


def _raw_line_score(line: str) -> int:
    text = _strip_greeting_prefix(_clean_text(line))
    if not text:
        return 0
    score = 0
    if any(term in text for term in RAW_STRONG_TERMS):
        score += 110
    if any(term in text for term in RAW_PRIORITY_TERMS):
        score += 80
    if any(term in text for term in RAW_SECONDARY_TERMS):
        score += 35
    if _sentence_like(text):
        score += 25
    if any(term in text for term in ("안녕하십니까", "감사", "기원합니다", "깊은 감사")):
        score -= 80
    if any(term in text for term in ("서울특별시교육청", "담당자", "담당부서", "생활안전부:", "홈페이지")):
        score -= 80
    if len(text) < 8:
        score -= 60
    if len(text) > 180:
        score -= 30
    return score


def _strip_greeting_prefix(text: str) -> str:
    value = _clean_text(text)
    value = re.sub(r"^안녕하십니까[?.]?\s*", "", value)
    value = re.sub(r"^학부모님\s*안녕하십니까[?.]?\s*", "", value)
    value = re.sub(r"^존경하는\s+.*?기원합니다[.。]?\s*", "", value)
    return value.strip()


def _same_or_subtitle(text: str, title: str) -> bool:
    text_key = _normalize_for_compare(text)
    title_key = _normalize_for_compare(title)
    if not text_key or not title_key:
        return False
    if text_key == title_key:
        return True
    if len(text_key) >= 7 and (text_key in title_key or title_key in text_key):
        return True
    if len(text_key) >= 7 and any(term in text for term in ("안내", "가정통신문")):
        text_chars = set(text_key)
        overlap = sum(1 for ch in text_chars if ch in title_key) / max(1, len(text_chars))
        return overlap >= 0.8
    return False


def _sentence_like(text: str) -> bool:
    return any(token in text for token in ("합니다", "바랍니다", "드립니다", "됩니다", "있습니다", "없습니다", "주세요", "안내"))


def _heading_only_line(text: str) -> bool:
    normalized = _normalize_for_compare(text)
    return normalized in {"다주요내용", "주요내용", "훈련개요", "학부모협조사항", "대피소찾는방법"}


def _masked_name_line(text: str) -> bool:
    return len(text) <= 4 and "*" in text


def _date_only_line(text: str) -> bool:
    compact = text.strip("<> ")
    return bool(re.fullmatch(r"(?:20\d{2}[./년\s-]*)?\d{1,2}[./월\s-]+\d{1,2}\s*일?\.?", compact))


def _mostly_amount_or_table_fragment(text: str) -> bool:
    compact = text.replace(" ", "")
    if len(compact) <= 1:
        return True
    digit_or_symbol = sum(1 for ch in compact if ch.isdigit() or ch in ",.-+()=원")
    return len(compact) <= 18 and digit_or_symbol / len(compact) >= 0.65


def _dedupe_text_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        key = _normalize_for_compare(line)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def _normalize_for_compare(value: str) -> str:
    return "".join(ch for ch in _clean_text(value).lower() if ch.isalnum())


def _card(
    card_type: str,
    items: list[NoticeCardItem],
    *,
    confidence: float | None,
    source: str = CARD_META_SOURCE,
    model: str | None = None,
) -> GeneratedNoticeCard:
    meta: dict[str, Any] = {"source": source or CARD_META_SOURCE}
    if confidence is not None:
        meta["confidence"] = confidence
    if model:
        meta["model"] = model
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
        if not text or text in seen or _noise_line(text):
            continue
        seen.add(text)
        items.append(NoticeCardItem(text=text, hint=hint))
    return items


def _prefixed_values(prefix: str, value: Any) -> list[str]:
    return [f"{prefix}: {item}" for item in _string_list(value)]


def _target_values(value: Any) -> list[str]:
    targets = [target for target in _string_list(value) if target not in GENERIC_TARGETS]
    if not targets:
        return []
    return [f"대상: {', '.join(targets)}"]


def _action_values(value: Any) -> list[str]:
    result: list[str] = []
    for item in _string_list(value):
        if any(term in item for term in ACTION_TERMS):
            result.append(f"해야 할 일: {item}")
    return result


def _priority_key_fact_lines(key_facts: list[str]) -> list[str]:
    return [line for line in key_facts if any(term in line for term in PRIORITY_KEY_FACT_TERMS)]


def _dedupe_items(items: list[NoticeCardItem]) -> list[NoticeCardItem]:
    deduped: list[NoticeCardItem] = []
    seen: set[str] = set()
    for item in items:
        text = _clean_text(item.text)
        if not text or text in seen or _noise_line(text):
            continue
        seen.add(text)
        deduped.append(NoticeCardItem(text=text, hint=item.hint))
    return deduped


def _noise_line(value: str) -> bool:
    text = _clean_text(value)
    if not text:
        return True
    lower = text.lower()
    stripped = lower.strip(" .:-_·•○□■()[]<>")
    if stripped in NOISE_EXACT_LINES:
        return True
    if len(stripped) <= 2:
        return True
    if any(token in lower for token in NOISE_CONTAINS):
        return True
    if not any(ch.isalnum() for ch in stripped):
        return True
    return False


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
