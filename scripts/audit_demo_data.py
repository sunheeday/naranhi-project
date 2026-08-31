"""데모·쇼케이스 학교의 데이터 발자국과 자녀 이관 대상을 조사한다.

읽기 전용이다. 아무것도 지우거나 바꾸지 않는다.

식별에 학교 '이름' 을 쓰지 않는다. 데모 학교의 이름이 진짜 학교와 글자까지
똑같은 '부천부흥중학교' 라서 이름으로는 구분이 불가능하기 때문이다.
앵커는 (neis_office_code, neis_school_code) 조합뿐이다 — 그 조합은
schools_neis_office_code_neis_school_code_key(0001:27) 유니크 제약을 타므로
학교 1개를 확정하고, 확정된 UUID 만으로 FK 를 따라간다.
이름은 사람이 눈으로 확인하도록 출력에만 쓴다.

기대와 다르면 종료코드 1 을 낸다. 기대치는 EXPECTED 에 적혀 있고,
2026-08-27 실측 + 사용자 결정에 근거한다.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# 삭제 대상 (label, office_code, school_code, 기대 자녀 수)
ANCHORS = [
    ("데모", "DEMO", "NARANHI001", 2),
    ("쇼케이스", "SHOWCASE", "NARANHI_SHOWCASE", 0),
]

# 데모 학교 자녀의 이관 대상 — 진짜 부천부흥중학교
TRANSFER_TO = ("J10", "7581020")


def get(path):
    req = urllib.request.Request(URL + "/rest/v1/" + path)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "[]")
    except urllib.error.HTTPError as e:
        print(f"  요청 실패 {e.code}: {path}")
        return None


def school_id_for(office, code):
    rows = get(f"schools?neis_office_code=eq.{office}&neis_school_code=eq.{code}&select=id,name,address")
    if rows is None or len(rows) != 1:
        return None, rows
    return rows[0]["id"], rows[0]


failed = False
demo_children = []

for label, office, code, expected_children in ANCHORS:
    print(f"\n=== {label} 학교 ({office}/{code}) ===")
    sid, row = school_id_for(office, code)
    if sid is None:
        if row == []:
            # 삭제 후 재실행하면 여기로 온다. 정상이다.
            print("  학교 없음 — 이미 삭제됐거나 애초에 없다")
            continue
        print(f"  학교가 정확히 1건이 아니다: {row!r}")
        print("  → 삭제 마이그레이션의 앵커 확정이 실패한다")
        failed = True
        continue

    print(f"  id={sid}")
    print(f"  name={row['name']!r}  address={row['address']!r}   (이름은 확인용. 필터에 쓰지 않는다)")

    notice_ids = [n["id"] for n in get(f"notices?school_id=eq.{sid}&select=id") or []]
    counts = {
        "notices": len(notice_ids),
        "school_events": len(get(f"school_events?school_id=eq.{sid}&select=id") or []),
        "school_crawl_state": len(get(f"school_crawl_state?school_id=eq.{sid}&select=school_id") or []),
        "meals": len(get(f"meals?office_code=eq.{office}&school_code=eq.{code}&select=id") or []),
    }
    if notice_ids:
        inl = "(" + ",".join(notice_ids) + ")"
        card_ids = [c["id"] for c in get(f"notice_cards?notice_id=in.{inl}&select=id") or []]
        counts["notice_cards"] = len(card_ids)
        counts["notice_ai_translations"] = len(get(f"notice_ai_translations?notice_id=in.{inl}&select=id") or [])
        # notice_hides 에는 id 컬럼이 없다. PK 가 (user_id, notice_id) 복합키다(0004:1-6).
        # select=id 로 물으면 HTTP 400 이 난다.
        counts["notice_hides"] = len(get(f"notice_hides?notice_id=in.{inl}&select=notice_id") or [])
        if card_ids:
            cinl = "(" + ",".join(card_ids) + ")"
            counts["notice_card_translations"] = len(
                get(f"notice_card_translations?notice_card_id=in.{cinl}&select=id") or []
            )

    children = get(f"children?school_id=eq.{sid}&select=id,user_id,name,grade,class_no,created_at") or []
    counts["children"] = len(children)

    for key, value in counts.items():
        print(f"    {key:26s} {value}")

    if len(children) != expected_children:
        print(f"    !! 자녀가 {len(children)}건이다. 기대치는 {expected_children}건 — 중단하고 보고할 것")
        failed = True
    for c in children:
        print(
            f"      child={c['id'][:8]}  user={c['user_id'][:8]}  name={c['name']!r}  "
            f"{c['grade']}-{c['class_no']}  생성 {c['created_at'][:10]}"
        )
    if label == "데모":
        demo_children = children

# ── 이관 대상 학교 ────────────────────────────────────────────
office, code = TRANSFER_TO
print(f"\n=== 이관 대상 학교 ({office}/{code}) ===")
real_id, real_row = school_id_for(office, code)
if real_id is None:
    print(f"  학교가 정확히 1건이 아니다: {real_row!r} — 이관할 수 없다")
    failed = True
else:
    print(f"  id={real_id}")
    print(f"  name={real_row['name']!r}   (데모 학교와 이름이 같다. 그래서 UUID 로만 다룬다)")

    state = get(f"school_crawl_state?school_id=eq.{real_id}&select=crawl_status,crawl_board_url,crawl_last_checked_at") or []
    if not state:
        print("  !! school_crawl_state 행이 없다 — 이관해도 크롤이 돌지 않는다. 상태 행을 먼저 만들 것")
        failed = True
    else:
        print(f"    crawl_status      {state[0]['crawl_status']}")
        print(f"    crawl_board_url   {state[0]['crawl_board_url']}")
        print(f"    최종 확인          {state[0]['crawl_last_checked_at']}")

    print(f"    notices           {len(get(f'notices?school_id=eq.{real_id}&select=id') or [])}")
    print(f"    school_events     {len(get(f'school_events?school_id=eq.{real_id}&select=id') or [])}")
    before = len(get(f"children?school_id=eq.{real_id}&select=id") or [])
    print(f"    children (이관 전)  {before}")
    print(f"    children (이관 후)  {before + len(demo_children)}  <- 대조용")

# ── 이관될 사용자의 파생 데이터 ────────────────────────────────
if demo_children:
    print("\n=== 이관될 사용자의 파생 데이터 ===")
    for uid in sorted({c["user_id"] for c in demo_children}):
        hides = get(f"notice_hides?user_id=eq.{uid}&select=notice_id") or []
        print(f"  user {uid[:8]}  notice_hides {len(hides)}")
        if hides:
            print("    (숨긴 공지는 데모 학교 공지이므로 학교 삭제 시 cascade 로 함께 사라진다)")

if failed:
    print("\n판정: 기대와 다르다. 중단하고 보고할 것.")
    sys.exit(1)

print("\n판정: 진행 가능. Task 8 의 이관·삭제를 실행할 수 있다.")
