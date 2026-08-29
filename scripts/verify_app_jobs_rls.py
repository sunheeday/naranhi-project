"""anon 키로 app_jobs 가 보이는지 확인한다. 읽기 전용.

종료코드
  0  차단됨 — RLS 가 정상 동작
  1  노출됨 — RLS 미적용
  2  판정 불가 — 설정·네트워크·권한 문제. 「안전하다」가 아니다.

2 를 0 과 구분하는 것이 이 스크립트의 핵심이다. 점검 도구가 고장났을 때
「안전합니다」라고 말하면 그 보장은 없느니만 못하다.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BLOCKED, EXPOSED, INDETERMINATE = 0, 1, 2


def classify(rows_returned: int, content_range: str | None) -> tuple[int, str]:
    """응답에서 판정을 낸다. 네트워크와 무관한 순수 함수 — 테스트 대상."""
    if content_range is None:
        return INDETERMINATE, "Content-Range 헤더 없음"
    total = content_range.rsplit("/", 1)[-1] if "/" in content_range else ""
    if total == "*":
        return INDETERMINATE, f"카운트 미확정 (Content-Range={content_range})"
    if not total.isdigit():
        return INDETERMINATE, f"Content-Range 형식 예상 밖 ({content_range})"
    if int(total) > 0 or rows_returned > 0:
        return EXPOSED, f"전체 {total}행 조회됨 — RLS 미적용"
    return BLOCKED, "0행 — 차단됨"


def main() -> int:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not anon:
        print("판정 불가: SUPABASE_URL 또는 SUPABASE_ANON_KEY 없음")
        return INDETERMINATE

    req = urllib.request.Request(f"{url}/rest/v1/app_jobs?select=id&limit=1")
    req.add_header("apikey", anon)
    req.add_header("Authorization", "Bearer " + anon)
    req.add_header("Prefer", "count=exact")

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode())
            content_range = r.headers.get("Content-Range")
            status = r.status
    except urllib.error.HTTPError as e:
        # 401·403 은 RLS 차단일 수도, 키가 틀린 것일 수도 있다 — 구분할 수 없다.
        # 404·5xx 는 설정·서버 문제다. 어느 쪽도 「차단 확인」이 아니다.
        print(f"판정 불가: HTTP {e.code} {e.reason}")
        return INDETERMINATE
    except Exception as e:  # noqa: BLE001 - 네트워크·파싱 무엇이든 판정 불가다
        print(f"판정 불가: {type(e).__name__}")
        return INDETERMINATE

    rows = len(body) if isinstance(body, list) else 0
    code, reason = classify(rows, content_range)
    label = {BLOCKED: "차단됨", EXPOSED: "노출됨", INDETERMINATE: "판정 불가"}[code]
    print(f"HTTP {status} | 반환 행 {rows} | Content-Range {content_range}")
    print(f"결과: {label} — {reason}")
    return code


if __name__ == "__main__":
    sys.exit(main())
