from __future__ import annotations

import re

from extractor.models import SourceExtraction


def combined_raw_text(
    sources: list[SourceExtraction],
    included_source_ids: list[str],
) -> str:
    """included_source_ids 순서대로 사용자용 raw_text를 이어 붙인다."""
    by_id = {source.source_id: source for source in sources}
    has_attachment_like_primary = any(
        source.source_type in {"attachment", "attachment_pdf", "attachment_hwp", "attachment_hwpx", "attachment_xlsx", "direct_file"}
        and source.raw_text.strip()
        for source in by_id.values()
    )
    parts: list[str] = []
    for source_id in included_source_ids:
        source = by_id.get(source_id)
        if not source:
            continue
        text = source.raw_text.strip()
        if not text:
            continue
        if has_attachment_like_primary and _looks_like_html_metadata_only(source, text):
            continue
        parts.append(text)
    return "\n\n---\n\n".join(parts)


def _looks_like_html_metadata_only(source: SourceExtraction, text: str) -> bool:
    if source.source_type != "html_body":
        return False
    compact = re.sub(r"\s+", " ", text)
    metadata_hits = sum(term in compact for term in ("작성자", "등록일", "조회수"))
    return len(compact) < 160 and metadata_hits >= 2
