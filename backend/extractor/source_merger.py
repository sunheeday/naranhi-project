from __future__ import annotations

from extractor.models import SourceExtraction
from extractor.quality import jaccard_similarity


# 파일 종류별 추출 신뢰도/정보량 우선순위.
# 중복 그룹에서 어느 source를 대표로 살릴지 결정할 때 사용.
TYPE_PRIORITY = {
    "attachment_hwp": 90,
    "attachment_hwpx": 88,
    "attachment_pdf": 82,
    "html_body": 70,
    "direct_file": 65,
    "attachment_xlsx": 60,
    "attachment_image": 50,
    "inline_image": 45,
    "attachment": 35,
}

MIN_TEXT_FOR_JACCARD = 120
JACCARD_THRESHOLD = 0.9


def assign_roles_and_dedupe(
    sources: list[SourceExtraction],
) -> tuple[list[SourceExtraction], list[str]]:
    """텍스트 추출 결과를 단순 분류한다.

    역할은 다음 3가지 중 하나로만 부여한다:
      - "primary"   : 본문(combined raw_text)에 포함되는 대표 source
      - "duplicate" : 다른 source와 내용이 거의 같아 본문 포함 X
      - "excluded"  : 추출 실패 또는 텍스트 비어있어서 본문 포함 X

    중복 판단은 두 가지로만 한다:
      1) text_fingerprint 동일
      2) Jaccard 유사도 >= 0.9 (최소 120자 이상)
    """
    # 1. 후보 추리기: 추출 성공 + 텍스트 있음
    candidates = [
        source
        for source in sources
        if source.raw_text.strip()
        and source.status in {"success", "partial_success"}
    ]
    candidate_ids = {source.source_id for source in candidates}

    # 후보가 아닌 것들은 모두 excluded
    for source in sources:
        if source.source_id not in candidate_ids:
            source.source_role = "excluded"

    # 2. 후보들을 중복 그룹으로 묶기
    groups = _build_duplicate_groups(candidates)

    # 3. 각 그룹에서 대표 1개씩 → primary, 나머지 → duplicate
    included_groups: list[SourceExtraction] = []
    for group in groups:
        best = _best_source(group)
        best.source_role = "primary"
        included_groups.append(best)
        for source in group:
            if source.source_id == best.source_id:
                continue
            source.source_role = "duplicate"
            source.duplicate_of = best.source_id

    # 4. 본문에 포함될 source ID 순서 (TYPE_PRIORITY 높은 순, 길이 긴 순)
    included_groups.sort(
        key=lambda source: (
            -TYPE_PRIORITY.get(source.source_type, 0),
            -len(source.raw_text),
        )
    )
    included_source_ids = [source.source_id for source in included_groups]

    return sources, included_source_ids


def _build_duplicate_groups(
    candidates: list[SourceExtraction],
) -> list[list[SourceExtraction]]:
    """후보 source들을 중복끼리 같은 그룹으로 묶는다."""
    groups: list[list[SourceExtraction]] = []
    for source in candidates:
        placed = False
        for group in groups:
            if any(_is_duplicate(source, member) for member in group):
                group.append(source)
                placed = True
                break
        if not placed:
            groups.append([source])
    return groups


def _is_duplicate(a: SourceExtraction, b: SourceExtraction) -> bool:
    """두 source가 같은 내용인지 판단."""
    # 1. 정규화된 텍스트의 지문이 같으면 → 같은 내용
    if a.text_fingerprint and a.text_fingerprint == b.text_fingerprint:
        return True

    # 2. 충분히 긴 텍스트끼리 Jaccard 유사도 검사
    if (
        len(a.raw_text.strip()) >= MIN_TEXT_FOR_JACCARD
        and len(b.raw_text.strip()) >= MIN_TEXT_FOR_JACCARD
    ):
        if jaccard_similarity(a.raw_text, b.raw_text) >= JACCARD_THRESHOLD:
            return True

    return False


def _best_source(sources: list[SourceExtraction]) -> SourceExtraction:
    """중복 그룹에서 대표 source 선정.

    기준 (위에서 아래로):
      1. TYPE_PRIORITY (파일 종류별 신뢰도)
      2. raw_text 길이
    """
    return max(
        sources,
        key=lambda source: (
            TYPE_PRIORITY.get(source.source_type, 0),
            len(source.raw_text),
        ),
    )
