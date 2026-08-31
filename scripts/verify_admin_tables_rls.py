"""anon 키로 관리자 테이블·RPC 가 닿는지 검사한다. 읽기 전용.

종료코드: 0 = 전부 차단됨 / 1 = 노출됨 / 2 = 테이블 없음(마이그레이션 미적용)
값은 아무것도 출력하지 않는다 — 상태코드와 행 수만 찍는다.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
ANON = os.environ["SUPABASE_ANON_KEY"]
TABLES = ("admin_users", "admin_sessions", "admin_audit_log")

exposed = []
missing = []
blocked = []


def _get(path):
    req = urllib.request.Request(URL + path)
    req.add_header("apikey", ANON)
    req.add_header("Authorization", "Bearer " + ANON)
    req.add_header("Prefer", "count=exact")
    return urllib.request.urlopen(req, timeout=60)


for table in TABLES:
    try:
        with _get(f"/rest/v1/{table}?select=id&limit=1") as response:
            body = json.loads(response.read().decode())
            content_range = response.headers.get("Content-Range") or "?"
            total = content_range.split("/")[-1]
            print(f"{table:18s} HTTP {response.status} | 반환 {len(body)} | 전체 {total}")
            if total not in ("0", "*"):
                exposed.append(table)
            else:
                blocked.append(table)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:200]
        print(f"{table:18s} HTTP {exc.code} {exc.reason}")
        if "PGRST205" in detail or exc.code == 404:
            missing.append(table)
        else:
            blocked.append(table)

# RPC 도 anon 으로 못 불러야 한다. security definer 함수라 권한이 새면 자격 검증기가 공개된다.
rpc_blocked = False
try:
    req = urllib.request.Request(
        URL + "/rest/v1/rpc/admin_verify_password",
        method="POST",
        data=json.dumps({"p_username": "probe", "p_password": "probe"}).encode(),
    )
    req.add_header("apikey", ANON)
    req.add_header("Authorization", "Bearer " + ANON)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as response:
        print(f"{'rpc:verify':18s} HTTP {response.status} — 호출됨")
except urllib.error.HTTPError as exc:
    print(f"{'rpc:verify':18s} HTTP {exc.code} {exc.reason} — 차단됨")
    rpc_blocked = True

if missing:
    print(f"\n결과: 테이블 없음 — {', '.join(missing)} (마이그레이션 미적용)")
    sys.exit(2)
if exposed:
    print(f"\n결과: 노출됨 — {', '.join(exposed)}")
    sys.exit(1)
if not rpc_blocked:
    print("\n결과: RPC 가 anon 으로 호출된다 — 권한 회수 실패")
    sys.exit(1)
print(f"\n결과: 차단됨 (테이블 {len(blocked)}개 + RPC)")
