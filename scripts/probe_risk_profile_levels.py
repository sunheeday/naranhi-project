"""운영 공지 원문(`notices.original_text`)으로 risk_profile 「high 확정」 하한을 센다. 읽기 전용.

Task 1 1차 시도: `notice_ai_translations.raw_steps.risk_profile`을 직접 조회하려 했으나,
그 컬럼 자체가 DB에 없다(orchestrator.py 반환값의 in-memory 키일 뿐, `_save_translation_result()`가
DB에 쓰는 row에는 포함되지 않는다). 그래서 `_risk_profile_from_source()`(orchestrator.py:545)의
판정 로직 중 `source_text`만으로 결정되는 두 조건을 그대로 복사해 원문에 대해 재현한다:

    level = "high" if reasons else "low"

reasons 를 채우는 조건 중 아래 두 개는 `source_text` 하나만 보고 성립하며, reasons 를
늘리기만 하지 줄이지 못한다(다른 조건들과 OR 관계). 따라서 이 둘 중 하나만 걸려도
그 공지는 `high`가 확정된다 — 「high 확정 비율의 하한」을 구할 수 있다.

  1. len(compact_source) > 1600                                  -> "long_notice"
  2. 13개 단서 낱말 중 하나라도 포함(소문자 비교)                  -> "has_high_risk_text_cues"
     첨부·붙임·별첨·양식·서식·qr·링크·계좌·스쿨뱅킹·납부·수납·동의서·서명

둘 다 안 걸린 공지만 「저위험 후보」이며, 이들도 hard_facts 기반 조건(첨부 URL/기한/연락처/
다중 일정 등)에 걸리면 실제로는 high 일 수 있다 — 이 스크립트는 그 부분은 판정하지 않는다.
"""
import json
import os
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PAGE = 1000

# orchestrator.py:577 에서 그대로 복사.
LONG_NOTICE_THRESHOLD = 1600

# orchestrator.py:580-594 에서 그대로 복사.
HIGH_RISK_TEXT_CUES = (
    "첨부",
    "붙임",
    "별첨",
    "양식",
    "서식",
    "qr",
    "링크",
    "계좌",
    "스쿨뱅킹",
    "납부",
    "수납",
    "동의서",
    "서명",
)


def fetch_all(path_no_paging: str, select_cols: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        path = f"{path_no_paging}?select={select_cols}&limit={PAGE}&offset={offset}"
        req = urllib.request.Request(URL + path)
        req.add_header("apikey", KEY)
        req.add_header("Authorization", "Bearer " + KEY)
        with urllib.request.urlopen(req, timeout=120) as r:
            page = json.loads(r.read().decode())
        rows.extend(page)
        offset += len(page)
        if len(page) < PAGE:
            break
    return rows


# 1) 번역 대상이 된 공지의 notice_id 집합 (notice_ai_translations 는 notice당 target_language 별로
#    행이 여러 개일 수 있으므로 dedupe한다 — risk_profile 은 source_text 로만 결정되므로
#    같은 notice_id 는 target_language 와 무관하게 항상 같은 판정이 나온다).
translation_rows = fetch_all("/rest/v1/notice_ai_translations", "notice_id")
translated_notice_ids = {row["notice_id"] for row in translation_rows if row.get("notice_id")}

# 2) 그 공지들의 원문. notices 전체를 읽고 번역 대상 집합으로 필터링한다(표본이 작아 in.() 청크 불필요).
notice_rows = fetch_all("/rest/v1/notices", "id,original_text")
targets = [row for row in notice_rows if row["id"] in translated_notice_ids]

total = 0
long_notice_ids: set[str] = set()
cue_ids: set[str] = set()
missing_text_ids: list[str] = []
neither_rows: list[dict] = []

for row in targets:
    notice_id = row["id"]
    original_text = row.get("original_text")
    if not isinstance(original_text, str) or not original_text.strip():
        missing_text_ids.append(notice_id)
        continue
    total += 1
    compact_source = original_text.strip()

    is_long = len(compact_source) > LONG_NOTICE_THRESHOLD
    if is_long:
        long_notice_ids.add(notice_id)

    lowered_source = compact_source.lower()
    has_cue = any(cue in lowered_source for cue in HIGH_RISK_TEXT_CUES)
    if has_cue:
        cue_ids.add(notice_id)

    if not is_long and not has_cue:
        neither_rows.append({"id": notice_id, "preview": compact_source[:200]})

high_confirmed_ids = long_notice_ids | cue_ids
neither_count = total - len(high_confirmed_ids)

print(f"=== 번역 대상 공지(notice_ai_translations.notice_id distinct) 후보: {len(translated_notice_ids)}건 ===")
print(f"=== notices 매칭 + original_text 있음: {total}건 (original_text 없음/공백: {len(missing_text_ids)}건) ===")
print()
print(f"long_notice (len > {LONG_NOTICE_THRESHOLD}) 로 걸린 수: {len(long_notice_ids)}")
print(f"has_high_risk_text_cues 로 걸린 수: {len(cue_ids)}")
print()

share_confirmed = (len(high_confirmed_ids) / total * 100) if total else 0.0
share_neither = (neither_count / total * 100) if total else 0.0
print(f"high 확정(둘 중 하나라도) 하한: {len(high_confirmed_ids)}건 ({share_confirmed:.1f}%)")
print(f"둘 다 안 걸림(저위험 후보): {neither_count}건 ({share_neither:.1f}%)")

if missing_text_ids:
    print(f"\n주의: original_text 가 없어 판정 못한 notice_id {len(missing_text_ids)}건: {missing_text_ids[:20]}")

print("\n=== 저위험 후보 notice_id (최대 20개) ===")
for row in neither_rows[:20]:
    print(f"  {row['id']}")

if neither_rows:
    print("\n=== 저위험 후보 본문 앞 200자 (최대 5건) ===")
    for row in neither_rows[:5]:
        print(f"--- {row['id']} ---")
        print(row["preview"])
        print()

print("\n결론:")
if neither_count == 0:
    print("→ 본문만으로도 전량이 high 확정된다. 저위험 분기(orchestrator.py:186-231)는 도달 불가 — dead path 확정.")
else:
    print(
        f"→ {neither_count}건은 본문 조건만으로는 high 가 확정되지 않는다. "
        "이 공지들이 hard_facts 조건(첨부 URL/기한/연락처/다중 일정 등)에도 안 걸리는지는 "
        "이 스크립트로는 판정하지 않았다 — 위 미리보기를 사람이 보고 판단할 것."
    )
