"""본문 사진 회수율 진단. 읽기 전용 — notices 에 절대 쓰지 않는다.

'body_images_combined 가 0건' 이라는 최초 관측은 틀렸다(최상위 body_image 키는
코드에 존재하지 않는다). 올바른 위치인 sources[] 로 다시 세면 35건 중 11건이다.
따라서 질문은 '왜 안 도는가' 가 아니라 '왜 69% 에서는 안 나오는가' 이고,
그 24건의 상당수는 애초에 본문에 사진이 없는 정상 공지일 수 있다.

이 스크립트는 분모를 다시 정의한다.
"""
import json
import os
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# 본문 사진 합성 기능 도입 커밋 61fe3e2 (2026-06-04). 이보다 앞서 추출된 공지에는
# 코드가 없었으므로 산출물이 없는 것이 정상이다. 스케줄러 정지가 06-15 이므로
# 기능이 살아 있던 창은 11일뿐이다.
FEATURE_LANDED = "2026-06-04"


def get(path: str):
    req = urllib.request.Request(URL + path)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


rows = get(
    "/rest/v1/notices"
    "?select=id,status,created_at,extraction_started_at,extraction_error_code,extracted_content"
    "&extracted_content=not.is.null&limit=1000"
)

print(f"조회된 공지(extracted_content not null) 총 {len(rows)}건\n")

window = Counter()
denom = Counter()
loss_rows = []
reasons = Counter()
budget_reasons = Counter()

for row in rows:
    ec = row.get("extracted_content") or {}
    sources = ec.get("sources") or []
    has_combined = any(s.get("source_id") == "body_images_combined" for s in sources)
    inline = [s for s in sources if s.get("source_type") == "inline_image"]
    started = str(row.get("extraction_started_at") or row.get("created_at") or "")
    in_window = started >= FEATURE_LANDED

    window["창 안" if in_window else "창 밖(도입 전)"] += 1
    if in_window and has_combined:
        window["창 안 + 보유"] += 1

    if has_combined:
        denom["보유"] += 1
        continue
    if not inline:
        denom["미보유 · 본문에 사진 없음"] += 1
        continue

    denom["미보유 · 사진은 있음(손실 후보)"] += 1
    loss_rows.append(row)
    for s in inline:
        reasons[f"{s.get('status')} / {'|'.join(str(e) for e in (s.get('errors') or [])) or '-'}"] += 1
    for reason in (ec.get("metadata") or {}).get("budget_exhausted_reasons") or []:
        budget_reasons[str(reason)] += 1

print("=== 1. 기능 도입 창 (H1) ===")
for k, v in window.most_common():
    print(f"  {k:28s} {v}")
in_win = window["창 안"]
if in_win:
    rate = window["창 안 + 보유"] / in_win
    print(f"  창 안 보유율: {rate:.0%}  → 80% 이상이면 판정 D1(고장 아님)")

print("\n=== 2. 분모 재정의 (H2) ===")
for k, v in denom.most_common():
    print(f"  {k:32s} {v}")

print("\n=== 3. 손실 후보의 인라인 이미지 상태 분포 ===")
for k, v in reasons.most_common():
    print(f"  {k:52s} {v}")

print("\n=== 4. 손실 후보의 공지 상태 (H5) ===")
print("  ", Counter(str(r.get("status")) for r in loss_rows).most_common())
print("  error_code:", Counter(str(r.get("extraction_error_code")) for r in loss_rows).most_common())

print("\n=== 5. 예산 소진 사유 (이미 저장되고 있다) ===")
for k, v in budget_reasons.most_common(10):
    print(f"  {k:52s} {v}")

print("\n=== 6. 손실 후보 공지 id (Cloud Logging 대조용) ===")
for r in loss_rows[:20]:
    print("  ", r["id"], r.get("status"), r.get("extraction_started_at"))
