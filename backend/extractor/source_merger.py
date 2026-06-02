from __future__ import annotations

import re

from extractor.models import SourceExtraction
from extractor.quality import jaccard_similarity, token_set


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

# 포함관계(상위집합) 중복 판정.
# 큰 첨부(HWP)가 본문 내용을 통째로 담고 있을 때, Jaccard 는 크기 차이 때문에 낮게 나와
# 못 잡는다(예: 본문이 HWP 에 100% 들어있어도 Jaccard 0.26). 그래서 '작은 글의 단어가
# 큰 글에 얼마나 들어있나(포함률)'로 따로 판정한다.
CONTAINMENT_THRESHOLD = 0.85       # 작은 글 단어의 85%+ 가 큰 글에 있으면 포함으로 본다
MIN_TOKENS_FOR_CONTAINMENT = 40    # 짧은 안내문("첨부 참고") 오판 방지: 작은 글이 40단어 이상일 때만

# 작은 글에만 있으면 '고유 정보'로 보아 통합하지 않을 핵심 패턴(마감일·참가비 등).
# quality.DATE_RE 는 점수용이라 'X월 Y일' 같은 흔한 마감일 표기를 놓쳐서 여기서 별도 정의한다.
_CRIT_DATE_RE = re.compile(
    r"\d{4}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}"   # 2026.3.30 / 2026년 3월 30(일)
    r"|\d{1,2}\s*월\s*\d{1,2}\s*일"                       # 3월 30일
    r"|\d{1,2}\s*[./]\s*\d{1,2}"                           # 3/30, 3.30
)
_CRIT_MONEY_RE = re.compile(r"\d[\d,]*\s*원")              # 15,000원


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

    # 3. 포함관계: 한쪽(보통 본문)이 다른쪽(보통 첨부 HWP)에 거의 다 들어있으면 중복.
    #    Jaccard 가 크기 차이로 못 잡는 '첨부가 본문의 상위집합' 케이스를 잡는다.
    if _smaller_is_contained(a.raw_text, b.raw_text):
        return True

    return False


def _smaller_is_contained(left_text: str, right_text: str) -> bool:
    """작은(짧은) 글의 단어가 큰 글에 CONTAINMENT_THRESHOLD 이상 들어있으면 True.

    큰 첨부파일이 본문 내용을 통째로 포함하는 흔한 경우를 잡는다. 오탐(서로 다른 두 공지의
    우연한 단어 겹침)과 정보 손실을 막기 위해 두 조건을 함께 둔다:
      - 작은 글이 MIN_TOKENS_FOR_CONTAINMENT 단어 이상일 때만 적용(짧은 안내문 제외)
      - 작은 글에만 있는 날짜/금액(마감일·참가비 등)이 있으면 중복으로 보지 않음(손실 방지)
    """
    left_tokens = token_set(left_text)
    right_tokens = token_set(right_text)
    if not left_tokens or not right_tokens:
        return False

    if len(left_tokens) <= len(right_tokens):
        small_text, small_tokens, big_text, big_tokens = left_text, left_tokens, right_text, right_tokens
    else:
        small_text, small_tokens, big_text, big_tokens = right_text, right_tokens, left_text, left_tokens

    if len(small_tokens) < MIN_TOKENS_FOR_CONTAINMENT:
        return False

    containment = len(small_tokens & big_tokens) / len(small_tokens)
    if containment < CONTAINMENT_THRESHOLD:
        return False

    # 작은 글에만 있는 핵심 정보(날짜·금액)가 있으면 → 합치면 손실 → 중복 아님
    if _has_unique_critical_info(small_text, big_text):
        return False

    return True


def _has_unique_critical_info(small_text: str, big_text: str) -> bool:
    """small_text 의 날짜/금액 중, 그 숫자가 big_text 에 아예 없는 게 있으면 True.

    본문에만 적힌 마감일·참가비 등이 통합 과정에서 사라지는 것을 막는 안전장치.
    추출기마다 표기가 달라도(예: '4.15' vs '4월 15일') 숫자 기준으로 비교하므로,
    같은 값이면 통과(중복 인정)하고 정말 빠진 값만 '본문 고유 정보'로 보아 보존한다.
    """
    big_numbers = set(re.findall(r"\d+", big_text.replace(",", "")))
    for pattern in (_CRIT_DATE_RE, _CRIT_MONEY_RE):
        for match in pattern.findall(small_text):
            numbers = re.findall(r"\d+", match.replace(",", ""))
            if numbers and any(number not in big_numbers for number in numbers):
                return True
    return False


def _best_source(sources: list[SourceExtraction]) -> SourceExtraction:
    """중복 그룹에서 대표 source 선정.

    핵심: 절대 '가장 긴(내용 많은) 글'을 버리지 않는다. 포함관계로 묶인 그룹
    (예: 본문 ⊂ 첨부 HWP)에서 더 짧은 본문을 대표로 뽑으면 첨부의 추가 내용이
    통째로 사라지기 때문이다. 그래서:
      1. 가장 긴 글 길이의 90% 이상인 후보만 추린 뒤
      2. 그 안에서 TYPE_PRIORITY(파일 종류 신뢰도) → 길이 순으로 대표를 고른다.
    (길이가 비슷한 Jaccard 그룹에서는 기존처럼 우선순위 높은 추출기가 대표가 된다.)
    """
    longest = max(len(source.raw_text) for source in sources)
    near_longest = [
        source for source in sources
        if len(source.raw_text) >= longest * 0.9
    ]
    return max(
        near_longest,
        key=lambda source: (
            TYPE_PRIORITY.get(source.source_type, 0),
            len(source.raw_text),
        ),
    )
