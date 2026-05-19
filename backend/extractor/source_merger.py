from __future__ import annotations

from collections import defaultdict

from extractor.models import SourceExtraction
from extractor.quality import jaccard_similarity


ROLE_PRIORITY = {
    "form": 90,
    "primary": 80,
    "supplement": 60,
    "activity": 45,
    "metadata_only": 20,
    "unknown": 10,
    "unreadable": 0,
    "duplicate": -10,
}

TYPE_PRIORITY = {
    "attachment_hwp": 90,
    "attachment_hwpx": 88,
    "attachment_pdf": 82,
    "html_body": 70,
    "direct_file": 65,
    "attachment_image": 50,
    "inline_image": 45,
    "attachment": 35,
}


def assign_roles_and_dedupe(sources: list[SourceExtraction]) -> tuple[list[SourceExtraction], list[str]]:
    for source in sources:
        source.source_role = _initial_role(source)

    _mark_duplicates(sources)
    included_source_ids = _included_source_ids(sources)
    if not any(source.source_role == "primary" and source.source_id in included_source_ids for source in sources):
        best = _best_source([source for source in sources if source.source_id in included_source_ids])
        if best:
            best.source_role = "primary"

    return sources, included_source_ids


def _initial_role(source: SourceExtraction) -> str:
    if source.status in {"skipped", "unsupported_file_type"}:
        return "unknown"
    if source.status not in {"success", "partial_success"} and not source.raw_text.strip():
        return "unreadable"
    if source.quality_score < 12:
        return "metadata_only"

    structured = source.structured or {}
    doc_type = str(structured.get("document_type") or "").lower()
    if doc_type in {"consent_form", "application_form", "survey"}:
        return "form"

    text = source.raw_text
    if any(term in text for term in ("활동지", "워크시트", "학습지", "미로", "색칠", "붙임")):
        return "activity"
    if any(term in text for term in ("참고", "붙임", "홍보자료", "보도자료")) and source.source_type != "html_body":
        return "supplement"
    return "primary" if source.source_type in {"html_body", "attachment_hwp", "attachment_hwpx", "attachment_pdf", "direct_file"} else "supplement"


def _mark_duplicates(sources: list[SourceExtraction]) -> None:
    hash_groups: dict[str, list[SourceExtraction]] = defaultdict(list)
    fingerprint_groups: dict[str, list[SourceExtraction]] = defaultdict(list)
    for source in sources:
        if source.file_hash:
            hash_groups[source.file_hash].append(source)
        if source.text_fingerprint and len(source.raw_text.strip()) >= 80:
            fingerprint_groups[source.text_fingerprint].append(source)

    for group in list(hash_groups.values()) + list(fingerprint_groups.values()):
        _mark_duplicate_group(group)

    for index, source in enumerate(sources):
        if source.duplicate_of or len(source.raw_text.strip()) < 120:
            continue
        for other in sources[index + 1 :]:
            if other.duplicate_of or len(other.raw_text.strip()) < 120:
                continue
            if jaccard_similarity(source.raw_text, other.raw_text) >= 0.92:
                _mark_duplicate_group([source, other])


def _mark_duplicate_group(group: list[SourceExtraction]) -> None:
    unique = {source.source_id: source for source in group}
    if len(unique) <= 1:
        return
    best = _best_source(list(unique.values()))
    if not best:
        return
    for source in unique.values():
        if source.source_id == best.source_id:
            continue
        source.duplicate_of = best.source_id
        source.source_role = "duplicate"


def _best_source(sources: list[SourceExtraction]) -> SourceExtraction | None:
    if not sources:
        return None
    return max(
        sources,
        key=lambda source: (
            ROLE_PRIORITY.get(source.source_role, 0),
            TYPE_PRIORITY.get(source.source_type, 0),
            source.quality_score,
            len(source.raw_text),
        ),
    )


def _included_source_ids(sources: list[SourceExtraction]) -> list[str]:
    readable = [
        source
        for source in sources
        if not source.duplicate_of
        and source.status in {"success", "partial_success"}
        and source.raw_text.strip()
        and source.source_role not in {"metadata_only", "unreadable"}
    ]
    readable.sort(
        key=lambda source: (
            -ROLE_PRIORITY.get(source.source_role, 0),
            -TYPE_PRIORITY.get(source.source_type, 0),
            -source.quality_score,
            int(source.metadata.get("order_index") or 0),
        )
    )
    return [source.source_id for source in readable]
