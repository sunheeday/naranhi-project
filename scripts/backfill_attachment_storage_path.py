"""기존 sources[] 의 public_url 에서 storage_path 를 역산해 채운다.

역산 실패분은 재추출하지 않는다(사용자 결정 2026-08-26). public_url 을 제거해
프론트가 깨진 링크 대신 '첨부 없음' 으로 보이게 하고 errors 에 사유를 남긴다.

APPLY=1 일 때만 쓴다. 기본은 미리보기.
"""
import json
import os
import re
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
APPLY = os.environ.get("APPLY") == "1"
BUCKET = "notice-attachments"

# .../storage/v1/object/public/notice-attachments/<notice_id>/<digest><ext>
KEY_RE = re.compile(rf"/object/public/{re.escape(BUCKET)}/(?P<key>[^?]+)")
ORPHAN_ERROR = "attachment_orphaned_pre_private_bucket"


def request(method, path, body=None):
    req = urllib.request.Request(URL + path, method=method)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data, timeout=120) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else None


rows = request("GET", "/rest/v1/notices?select=id,extracted_content&extracted_content=not.is.null&limit=1000")
stat = Counter()
changed = []

for row in rows:
    ec = row.get("extracted_content") or {}
    sources = ec.get("sources") or []
    dirty = False
    for s in sources:
        pub = s.get("public_url")
        if not pub:
            continue
        stat["public_url 있음"] += 1
        if s.get("storage_path"):
            s.pop("public_url", None)
            stat["storage_path 이미 있음 → public_url 제거"] += 1
            dirty = True
            continue
        m = KEY_RE.search(pub)
        if m:
            s["storage_path"] = m.group("key")
            s.pop("public_url", None)
            stat["역산 성공"] += 1
        else:
            s.pop("public_url", None)
            errs = s.get("errors") or []
            if ORPHAN_ERROR not in errs:
                errs.append(ORPHAN_ERROR)
            s["errors"] = errs
            stat["역산 실패 → 포기"] += 1
        dirty = True
    if dirty:
        changed.append((row["id"], ec))

print("=== 집계 ===")
for k, v in stat.most_common():
    print(f"  {k:44s} {v}")
print(f"  {'변경 대상 공지':44s} {len(changed)}")

if not APPLY:
    print("\n미리보기입니다. 실제로 쓰려면 APPLY=1 을 붙여 다시 실행하세요.")
    sys.exit(0)

for notice_id, ec in changed:
    request("PATCH", f"/rest/v1/notices?id=eq.{notice_id}", {"extracted_content": ec})
print(f"\n{len(changed)}건 갱신 완료")
