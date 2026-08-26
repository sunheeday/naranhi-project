"""anon 키로 app_jobs 가 보이는지 확인한다. 읽기 전용. 행 수만 출력한다."""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

url = os.environ["SUPABASE_URL"].rstrip("/")
anon = os.environ["SUPABASE_ANON_KEY"]

req = urllib.request.Request(f"{url}/rest/v1/app_jobs?select=id&limit=1")
req.add_header("apikey", anon)
req.add_header("Authorization", "Bearer " + anon)
req.add_header("Prefer", "count=exact")

try:
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read().decode())
        cr = r.headers.get("Content-Range") or "?"
        total = cr.split("/")[-1] if "/" in cr else "?"
        print(f"HTTP {r.status} | 반환 행 {len(body)} | 전체 {total}")
        if total not in ("0", "*"):
            print("결과: 노출됨 (RLS 미적용)")
            sys.exit(1)
        print("결과: 차단됨")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} {e.reason} — 차단됨")
