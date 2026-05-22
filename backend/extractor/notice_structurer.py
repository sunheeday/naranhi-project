from __future__ import annotations

from extractor.models import SourceExtraction


def combined_raw_text(
    sources: list[SourceExtraction],
    included_source_ids: list[str],
) -> str:
    """included_source_ids 순서대로 raw_text를 이어 붙인다.

    각 source 사이에는 구분자(`---`)와 source 정보 라벨을 끼운다.
    라벨은 디버깅/메타데이터 용도이며 실제 본문에 노이즈가 될 수 있다면
    호출하는 쪽에서 정제하거나 제거할 수 있다.
    """
    by_id = {source.source_id: source for source in sources}
    parts: list[str] = []
    for source_id in included_source_ids:
        source = by_id.get(source_id)
        if not source:
            continue
        text = source.raw_text.strip()
        if not text:
            continue
        label = f"[{source.source_id} {source.source_type}]"
        parts.append(f"{label}\n{text}")
    return "\n\n---\n\n".join(parts)
