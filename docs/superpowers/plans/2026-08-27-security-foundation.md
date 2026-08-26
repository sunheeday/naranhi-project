# 보안 기반 · 인증 복구 · DB 배포 자동화 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 익명 키로 뚫려 있는 작업 큐를 막고, 구글 로그인 경로를 되살리고, 공지 첨부를 해당 학교 학부모만 받을 수 있게 하고, DB 마이그레이션을 머지 시 자동 적용한다.

**Architecture:** 네 갈래를 순차 배포한다. ① 마이그레이션 이력을 정합시키고 RLS 한 줄을 적용 ② 그 적용 수단을 GitHub Actions로 영구화 ③ 우회 스위치를 둘에서 하나로 줄이고 구글 로그인·14일 세션을 복구 ④ 첨부를 저장된 공개 URL 방식에서 요청 시 서명 URL 발급 방식으로 바꾸고 마지막에 버킷을 잠근다. 각 단계는 단독 롤백이 가능하다.

**Tech Stack:** Next.js 15 App Router, `@supabase/ssr`, Supabase(Postgres + Storage + Auth, 도쿄 리전), Python 3.12 FastAPI, `supabase-py`, GitHub Actions, Supabase CLI

**Spec:** [docs/superpowers/specs/2026-08-26-security-foundation-design.md](../specs/2026-08-26-security-foundation-design.md)

## Global Constraints

- **마이그레이션 번호**: 다음 번호는 **0037**부터. `0035`는 `docs/기능명세서-자녀-개인일정.md`가 `child_personal_schedules`용으로 예약, `0036`은 이 계획의 Task 1이 사용. 파일명 번호 중복 금지.
- **프로젝트 ref**: `aoihmzewthgyoxtejfwo` (공개값). Supabase 리전 = Northeast Asia (Tokyo).
- **DB 비밀번호 불필요**: Supabase CLI가 액세스 토큰으로 임시 로그인 역할을 만들어 접속한다 (`supabase db push --dry-run`으로 검증 완료). `SUPABASE_DB_PASSWORD`를 요구하는 단계를 만들지 말 것.
- **열쇠 취급**: 토큰·키를 명령줄 인자나 URL 쿼리에 넣지 않는다. 값 출력 금지(길이만). 저장은 환경변수 또는 시크릿 저장소로만.
- **우회 스위치는 하나**: 이 작업이 끝나면 인증 우회 경로는 `DEV_LOGIN_ENABLED` 하나로만 제어되어야 한다. `TEST_ENTRY_BYPASS`는 완전히 사라진다.
- **개발 진입로는 켜둔다**: 사용자 결정에 따라 프로덕션에서도 `DEV_LOGIN_ENABLED=true`. 나중에 명시적 지시가 있을 때 끈다.
- **재추출 금지**: 이행 실패 첨부는 포기한다. 재추출 작업을 만들지 말 것.
- **데모 예외 금지**: 데모 학교를 스코프 검사의 예외로 두지 않는다.
- **테스트 실행**:
  - 백엔드: `PYTHONPATH=backend python -m unittest discover backend/tests`
  - 프론트: `npm run typecheck` + `npm run build` (**프론트 테스트 러너가 없다** — `package.json`에 test 스크립트 없음. 프론트 검증은 타입체크·빌드·실제 HTTP 확인으로 한다)
- **커밋 메시지**: 한국어, `type(scope): 요약` 형식. 저장소 관례를 따른다.

---

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `supabase/migrations/0036_app_jobs_rls.sql` | 작업 큐 접근 차단 | 존재 (Task 1에서 적용) |
| `supabase/migrations/0037_notice_attachments_private.sql` | 첨부 버킷 비공개 전환 | 신규 (Task 7) |
| `.github/workflows/db-migrate.yml` | 마이그레이션 검사·적용 | 신규 (Task 2) |
| `scripts/check_migration_numbers.py` | 번호 중복 검사 | 신규 (Task 2) |
| `middleware.ts` | 인증 게이트 | 수정 (Task 3) |
| `lib/test-entry-bypass.ts` | 데모 우회 | **삭제** (Task 3) |
| `app/api/auth/dev-login/route.ts` | 개발 계정 로그인 | 수정 (Task 4) |
| `app/home/route.ts` | 개발 진입로 | 신규 (Task 4) |
| `lib/supabase/server.ts` | Supabase 클라이언트 팩토리 | 수정 (Task 5) |
| `backend/app/services/attachment_storage.py` | 첨부 업로드 | 수정 (Task 6) |
| `scripts/backfill_attachment_storage_path.py` | 기존 첨부 이행 | 신규 (Task 6) |
| `app/api/notices/[noticeId]/attachments/[sourceId]/route.ts` | 서명 URL 발급 + 스코프 검사 | 신규 (Task 7) |
| `lib/notices.ts` | 첨부 읽기 | 수정 (Task 7) |

---

## 배포 순서 (스펙 §8 정정)

스펙 §8은 인증(6번)을 첨부 라우트(5번)보다 **뒤에** 두면서 "스코프 검사가 동작하려면 로그인한 사용자가 있어야 한다"고 적었다 — **근거와 순서가 뒤집혀 있다.** 이 계획은 인증을 앞으로 옮긴다.

```
Task 1  이력 정합 + RLS 적용        (즉시 보안 효과)
Task 2  배포 자동화 워크플로          (이후 모든 마이그레이션의 통로)
Task 3  우회 스위치 통합
Task 4  /home 개발 진입로
Task 5  14일 세션                    ← 여기까지 인증 복구 완료
Task 6  첨부 백엔드 + 이행
Task 7  첨부 라우트 + 버킷 잠금
```

---

## Task 1: 마이그레이션 이력 정합 및 작업 큐 차단

`supabase migration list` 실측 결과 원격 이력에 `0001~0033`이 기록되어 있고, `0030(end_date)`·`0034`·`0036` 세 개가 로컬에만 있다. 앞의 둘은 **DB에 실제 적용되어 있으나 이력에 누락**됐다(운영 컬럼 조회로 확인). 세 파일 모두 멱등이므로 재실행이 무해하다.

**Files:**
- Apply: `supabase/migrations/0036_app_jobs_rls.sql` (이미 존재, 브랜치 `fix/app-jobs-rls`)
- Create: `scripts/verify_app_jobs_rls.py`

**Interfaces:**
- Consumes: 없음
- Produces: 원격 `supabase_migrations.schema_migrations`에 `0030`,`0034`,`0036` 기록. 이후 모든 Task가 `supabase db push`를 깨끗하게 쓸 수 있다.

- [ ] **Step 1: 적용 전 노출 상태를 기록으로 남긴다**

`scripts/verify_app_jobs_rls.py` 생성:

```python
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
```

- [ ] **Step 2: 적용 전 상태를 확인한다 (실패를 먼저 본다)**

```bash
export SUPABASE_URL="$(gh variable get NEXT_PUBLIC_SUPABASE_URL)"
export SUPABASE_ANON_KEY="$(gh variable get NEXT_PUBLIC_SUPABASE_ANON_KEY)"
python scripts/verify_app_jobs_rls.py
```

Expected: `전체 230` 근처의 숫자 + `결과: 노출됨` + 종료코드 1

- [ ] **Step 3: 적용될 내용을 먼저 확인한다**

```bash
supabase db push --dry-run --include-all
```

Expected: 적용 대상으로 `0030_school_events_end_date.sql`, `0034_child_dietary_restrictions.sql`, `0036_app_jobs_rls.sql` **세 개만** 나열된다. 그 외 파일이 나오면 **중단하고 보고할 것** — 이력이 예상과 다르다는 뜻이다.

- [ ] **Step 4: 적용한다**

```bash
supabase db push --include-all
```

Expected: 세 파일 적용 완료. 오류 없음.

- [ ] **Step 5: 차단됐는지 확인한다**

```bash
python scripts/verify_app_jobs_rls.py
```

Expected: `전체 0` + `결과: 차단됨` + 종료코드 0

- [ ] **Step 6: 다른 테이블이 안 깨졌는지 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
for t in ['app_jobs','notices','school_events']:
    r=urllib.request.Request(f'{u}/rest/v1/{t}?select=id&limit=1')
    r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k); r.add_header('Prefer','count=exact')
    x=urllib.request.urlopen(r,timeout=60)
    print(t, x.headers.get('Content-Range'))
"
```

Expected: `app_jobs 0-0/230` — service_role 로는 여전히 전부 보인다(RLS 우회). 이게 안 나오면 백엔드가 깨진다.

- [ ] **Step 7: 이력이 정합됐는지 확인한다**

```bash
supabase migration list
```

Expected: Local 열과 Remote 열이 모든 행에서 일치. 빈 Remote 칸이 없다.

- [ ] **Step 8: 커밋**

```bash
git add scripts/verify_app_jobs_rls.py
git commit -m "chore: app_jobs RLS 적용 검증 스크립트 추가

anon 키로 app_jobs 가 보이는지 확인한다. 적용 전 230행 → 적용 후 0행.
CI 에서도 재사용할 수 있도록 종료코드로 판정한다."
```

---

## Task 2: DB 배포 자동화

**Files:**
- Create: `.github/workflows/db-migrate.yml`
- Create: `scripts/check_migration_numbers.py`

**Interfaces:**
- Consumes: Task 1이 정합시킨 원격 이력
- Produces: `main` 머지 시 `supabase db push` 자동 실행. 이후 Task 7의 `0037` 마이그레이션이 이 통로로 나간다.

- [ ] **Step 1: 번호 중복 검사 스크립트를 쓴다**

`scripts/check_migration_numbers.py`:

```python
"""supabase/migrations/ 의 번호 접두가 중복되는지 검사한다. CI 용."""
import re
import sys
from collections import defaultdict
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "supabase" / "migrations"
PATTERN = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

by_number = defaultdict(list)
bad_names = []

for path in sorted(MIGRATIONS.glob("*.sql")):
    m = PATTERN.match(path.name)
    if not m:
        bad_names.append(path.name)
        continue
    by_number[m.group(1)].append(path.name)

failed = False

for name in bad_names:
    print(f"이름 규칙 위반: {name} (형식: NNNN_snake_case.sql)")
    failed = True

for number, names in sorted(by_number.items()):
    if len(names) > 1:
        print(f"번호 중복 {number}: {', '.join(names)}")
        failed = True

if failed:
    print("\n마이그레이션 번호 검사 실패")
    sys.exit(1)

print(f"마이그레이션 {sum(len(v) for v in by_number.values())}개, 번호 중복 없음")
```

- [ ] **Step 2: 지금은 실패하는 것을 확인한다**

```bash
python scripts/check_migration_numbers.py
```

Expected: `번호 중복 0030: 0030_notice_ai_translations_add_translated_title.sql, 0030_school_events_end_date.sql` + 종료코드 1

> 이 실패는 **의도된 것**이다. 기존 중복은 이미 양쪽 다 적용·기록됐으므로 파일명을 바꾸면 안 된다(rename 시 CLI가 미적용으로 보고 재실행한다). 다음 단계에서 예외로 등록한다.

- [ ] **Step 3: 기존 중복을 예외로 등록한다**

`scripts/check_migration_numbers.py`의 `by_number` 루프 직전에 추가:

```python
# 이미 원격에 적용·기록된 역사적 중복. 파일명을 바꾸면 CLI 가 미적용으로 보고
# 재실행하므로 rename 하지 않는다. 신규 중복만 잡는다.
GRANDFATHERED = {"0030"}
```

그리고 루프를 수정:

```python
for number, names in sorted(by_number.items()):
    if len(names) > 1 and number not in GRANDFATHERED:
        print(f"번호 중복 {number}: {', '.join(names)}")
        failed = True
```

- [ ] **Step 4: 통과하는지 확인한다**

```bash
python scripts/check_migration_numbers.py
```

Expected: `마이그레이션 37개, 번호 중복 없음` + 종료코드 0

- [ ] **Step 5: 새 중복을 만들면 잡히는지 확인한다**

```bash
cp supabase/migrations/0036_app_jobs_rls.sql supabase/migrations/0036_dup_probe.sql
python scripts/check_migration_numbers.py; echo "종료코드: $?"
rm supabase/migrations/0036_dup_probe.sql
```

Expected: `번호 중복 0036: ...` + 종료코드 1, 그리고 파일 삭제 후 다시 통과

- [ ] **Step 6: 워크플로를 쓴다**

`.github/workflows/db-migrate.yml`:

```yaml
name: DB migrations

on:
  pull_request:
    paths:
      - 'supabase/migrations/**'
      - '.github/workflows/db-migrate.yml'
  push:
    branches: [main]
    paths:
      - 'supabase/migrations/**'
  workflow_dispatch:

jobs:
  check:
    name: 번호 검사 + 적용 예정 확인
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: 마이그레이션 번호 중복 검사
        run: python scripts/check_migration_numbers.py

      - uses: supabase/setup-cli@v1
        with:
          version: latest

      - name: 적용 예정 목록 (적용하지 않음)
        env:
          SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}
        run: |
          supabase link --project-ref "${{ vars.SUPABASE_PROJECT_REF }}"
          supabase db push --dry-run --include-all

  apply:
    name: 적용
    if: github.event_name != 'pull_request'
    needs: check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: supabase/setup-cli@v1
        with:
          version: latest

      - name: 마이그레이션 적용
        env:
          SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}
        run: |
          supabase link --project-ref "${{ vars.SUPABASE_PROJECT_REF }}"
          supabase db push --include-all

      - name: 적용 후 이력 확인
        env:
          SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}
        run: supabase migration list
```

- [ ] **Step 7: 워크플로 문법을 검사한다**

```bash
python -c "
import yaml, sys
d = yaml.safe_load(open('.github/workflows/db-migrate.yml', encoding='utf-8'))
print('jobs:', list(d['jobs'].keys()))
assert 'check' in d['jobs'] and 'apply' in d['jobs']
assert d['jobs']['apply']['needs'] == 'check'
print('OK')
"
```

Expected: `jobs: ['check', 'apply']` + `OK`

- [ ] **Step 8: 커밋**

```bash
git add scripts/check_migration_numbers.py .github/workflows/db-migrate.yml
git commit -m "ci: DB 마이그레이션 자동 적용 + 번호 중복 검사

PR 에서는 번호 검사와 적용 예정 목록만 보고, main 머지에서만 실제 적용한다.
프로덕션 DB 가 하나뿐이라 PR 단계 적용은 되돌릴 수 없기 때문이다.

DB 비밀번호는 쓰지 않는다 — CLI 가 액세스 토큰으로 임시 로그인 역할을
만들어 접속한다(db push --dry-run 으로 검증).

0030 중복은 이미 양쪽 다 적용·기록된 역사적 중복이라 예외로 둔다.
파일명을 바꾸면 CLI 가 미적용으로 보고 재실행한다."
```

---

## Task 3: 우회 스위치 통합

지금 우회가 둘이다 — `TEST_ENTRY_BYPASS`(전 경로 무인증 통과)와 `DEV_LOGIN_ENABLED`(개발 계정 로그인). 개발 진입로를 켜둘 것이므로, **스위치가 둘로 남으면 하나를 꺼도 열려 있게 된다.** 하나로 줄인다.

**Files:**
- Modify: `middleware.ts` (18~28행 부근의 `isTestEntryBypass` 분기)
- Delete: `lib/test-entry-bypass.ts`
- Modify: `.github/workflows/deploy-cloud-run.yml:84` (`TEST_ENTRY_BYPASS=true` 제거)
- Modify: `lib/test-entry-bypass.ts` 를 import 하는 모든 파일

**Interfaces:**
- Consumes: 없음
- Produces: `TEST_ENTRY_BYPASS` 심볼이 저장소에서 사라진다. Task 4가 `DEV_LOGIN_ENABLED` 하나만 다루면 된다.

- [ ] **Step 1: 참조 지점을 전부 찾는다**

```bash
grep -rn "TEST_ENTRY_BYPASS\|test-entry-bypass\|ensureBypassChildForSchool" \
  --include=*.ts --include=*.tsx --include=*.yml . | grep -v node_modules
```

Expected: `middleware.ts`, `lib/test-entry-bypass.ts`, `.github/workflows/deploy-cloud-run.yml`, 그리고 이를 import 하는 페이지/액션들. **목록을 기록해 둘 것** — 다음 단계에서 하나씩 지운다.

- [ ] **Step 2: middleware 의 우회 분기를 제거한다**

`middleware.ts`에서 아래 블록을 **통째로 삭제**한다:

```typescript
const TEST_BYPASS_ENTRY_PATHS = ['/login', '/onboarding']
```

그리고 `middleware` 함수 안에서:

```typescript
  const isTestEntryBypass = process.env.TEST_ENTRY_BYPASS === 'true'

  if (isTestEntryBypass) {
    const shouldRedirectHome = TEST_BYPASS_ENTRY_PATHS.some((p) => pathname.startsWith(p))
    if (shouldRedirectHome) {
      return NextResponse.redirect(new URL('/', request.url))
    }
    return NextResponse.next({ request })
  }
```

이 블록도 삭제한다. 아래의 `isPreview` 분기부터가 새 시작점이 된다.

- [ ] **Step 3: `/home` 을 공개 경로에 추가한다**

`middleware.ts`의 `PUBLIC_PATHS` 배열에 `'/home'`을 넣는다:

```typescript
const PUBLIC_PATHS = [
  '/demo',
  '/home',
  '/login',
  '/auth/callback',
  '/api/auth/dev-login',
  '/api/health',
  '/api/supabase/health',
  '/api/locale',
]
```

- [ ] **Step 4: `lib/test-entry-bypass.ts` 와 그 호출부를 제거한다**

Step 1에서 기록한 각 호출부에서 import 와 호출을 지운다. 데모 학교 컨텍스트를 세팅하던 자리는 **아무것도 하지 않도록** 비운다(대체 로직을 넣지 않는다 — 데모는 끝났다).

그 다음 파일을 삭제한다:

```bash
git rm lib/test-entry-bypass.ts
```

- [ ] **Step 5: 배포 워크플로에서 env 를 뺀다**

`.github/workflows/deploy-cloud-run.yml`의 `env_vars:` 블록에서 아래 한 줄을 삭제한다:

```yaml
            TEST_ENTRY_BYPASS=true
```

- [ ] **Step 6: 잔존 참조가 없는지 확인한다**

```bash
grep -rn "TEST_ENTRY_BYPASS\|test-entry-bypass\|ensureBypassChildForSchool" \
  --include=*.ts --include=*.tsx --include=*.yml . | grep -v node_modules
echo "종료코드: $?  (1 이면 없음 = 정상)"
```

Expected: 출력 없음, 종료코드 1

- [ ] **Step 7: 타입체크와 빌드가 통과하는지 확인한다**

```bash
npm run typecheck && npm run build
```

Expected: 둘 다 성공. 실패하면 Step 4에서 지운 호출부의 잔재다.

- [ ] **Step 8: 커밋**

```bash
git add -A middleware.ts lib .github/workflows/deploy-cloud-run.yml
git commit -m "refactor(auth): 우회 스위치를 DEV_LOGIN_ENABLED 하나로 통합

TEST_ENTRY_BYPASS(전 경로 무인증 통과)와 DEV_LOGIN_ENABLED(개발 계정 로그인)
두 개가 공존해서, 하나를 꺼도 다른 하나로 열려 있는 구조였다.

개발 진입로는 당분간 켜두기로 했으므로 스위치가 둘이면 위험하다.
TEST_ENTRY_BYPASS 를 완전히 제거하고 DEV_LOGIN_ENABLED 만 남긴다.

데모 종료 결정에 따라 lib/test-entry-bypass.ts 도 삭제한다.
가드를 추가하는 게 아니라 삭제다 — 남겨두면 새 데모 데이터가 계속 생긴다."
```

---

## Task 4: `/home` 개발 진입로

`app/api/auth/dev-login/route.ts:8`이 `process.env.NODE_ENV === 'production'`이면 **무조건 404**를 낸다. 프로덕션에서 켜두려면 이 가드를 `DEV_LOGIN_ENABLED` 하나로 바꿔야 한다.

**Files:**
- Modify: `app/api/auth/dev-login/route.ts:8`
- Create: `app/home/route.ts`
- Modify: `.github/workflows/deploy-cloud-run.yml` (env 3개 추가)

**Interfaces:**
- Consumes: Task 3이 남긴 `DEV_LOGIN_ENABLED` 단일 스위치
- Produces: `GET /home` → 개발 계정으로 로그인된 상태로 `/`. `DEV_LOGIN_ENABLED`가 `'true'`가 아니면 `/login`으로 이동.

- [ ] **Step 1: 프로덕션 가드를 스위치 하나로 바꾼다**

`app/api/auth/dev-login/route.ts`의 8행:

```typescript
  if (process.env.NODE_ENV === 'production' || process.env.DEV_LOGIN_ENABLED !== 'true') {
```

를 아래로 바꾼다:

```typescript
  // 프로덕션에서도 켤 수 있다(사용자 결정 2026-08-26). 스위치는 DEV_LOGIN_ENABLED 하나뿐이며,
  // 이 값을 'true' 가 아닌 것으로 바꾸면 우회 경로가 완전히 닫힌다.
  if (process.env.DEV_LOGIN_ENABLED !== 'true') {
```

- [ ] **Step 2: `/home` 라우트를 쓴다**

`app/home/route.ts` 생성:

```typescript
import { NextResponse, type NextRequest } from 'next/server'

/** 개발·시연용 진입로. DEV_LOGIN_ENABLED 가 켜져 있을 때만 개발 계정으로 즉시 로그인한다.
 *  꺼져 있으면 평범한 로그인 화면으로 보낸다. 우회 스위치는 이 값 하나뿐이다. */
export async function GET(request: NextRequest) {
  if (process.env.DEV_LOGIN_ENABLED !== 'true') {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  const devLoginUrl = new URL('/api/auth/dev-login', request.url)
  const upstream = await fetch(devLoginUrl, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ next: '/' }),
  })

  const payload = await upstream.json().catch(() => null)
  if (!upstream.ok || !payload?.ok) {
    const reason = payload?.error ?? 'dev_login_failed'
    return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(reason)}`, request.url))
  }

  const response = NextResponse.redirect(new URL(payload.next ?? '/', request.url))
  const setCookie = upstream.headers.getSetCookie?.() ?? []
  for (const cookie of setCookie) {
    response.headers.append('set-cookie', cookie)
  }
  return response
}
```

- [ ] **Step 3: 배포 워크플로에 env 를 넣는다**

`.github/workflows/deploy-cloud-run.yml`의 `env_vars:` 블록에 세 줄을 추가한다:

```yaml
            DEV_LOGIN_ENABLED=true
```

그리고 같은 스텝의 `secrets:` 블록에 두 줄을 추가한다 (계정 자격이므로 시크릿으로):

```yaml
            DEV_LOGIN_EMAIL=dev-login-email:latest
            DEV_LOGIN_PASSWORD=dev-login-password:latest
```

> **선행 작업**: GCP Secret Manager 에 `dev-login-email`, `dev-login-password` 를 만들어야 한다.
> 값은 Supabase Auth 에 실제로 존재하는 계정이어야 한다. 없으면 Supabase 대시보드
> → Authentication → Users → Add user 로 만든다.
> 시크릿 생성은 값을 명령줄에 넣지 않도록 파일 경유로 한다:
> ```bash
> # 값을 파일에 적어두고
> gcloud secrets create dev-login-email --data-file=./tmp_email.txt
> gcloud secrets create dev-login-password --data-file=./tmp_pw.txt
> rm ./tmp_email.txt ./tmp_pw.txt
> ```

- [ ] **Step 4: 로컬에서 꺼진 상태를 확인한다**

```bash
DEV_LOGIN_ENABLED=false npm run build >/dev/null 2>&1 && echo "빌드 OK"
npm run typecheck
```

Expected: 타입체크·빌드 성공

- [ ] **Step 5: 로컬에서 동작을 확인한다**

`.env.local`에 `DEV_LOGIN_ENABLED=true`, `DEV_LOGIN_EMAIL`, `DEV_LOGIN_PASSWORD`가 있는 상태로:

```bash
npm run dev &
sleep 8
curl -s -o /dev/null -w "DEV_LOGIN_ENABLED=true → HTTP %{http_code} → %{redirect_url}\n" \
  "http://localhost:3000/home"
```

Expected: `HTTP 307` 또는 `302`, redirect_url 이 `/` (로그인 성공)

- [ ] **Step 6: 꺼졌을 때 로그인으로 가는지 확인한다**

```bash
# dev 서버를 끄고 env 없이 재기동한 뒤
curl -s -o /dev/null -w "스위치 꺼짐 → %{redirect_url}\n" "http://localhost:3000/home"
```

Expected: redirect_url 이 `/login`

- [ ] **Step 7: 커밋**

```bash
git add app/api/auth/dev-login/route.ts app/home/route.ts .github/workflows/deploy-cloud-run.yml
git commit -m "feat(auth): /home 개발 진입로 추가, 프로덕션 가드를 스위치 하나로 교체

dev-login 라우트가 NODE_ENV=production 이면 무조건 404 를 내고 있었다.
사용자 결정에 따라 프로덕션에서도 켜야 하므로 DEV_LOGIN_ENABLED 단독 판정으로 바꾼다.

/home 은 GET 진입로다. 스위치가 켜져 있으면 개발 계정으로 로그인시키고,
꺼져 있으면 /login 으로 보낸다. 나중에 이 env 한 줄만 바꾸면 우회가 완전히 닫힌다."
```

---

## Task 5: 14일 자동 로그인

`lib/supabase/server.ts`는 쿠키 옵션에 수명을 지정하지 않는다. Supabase 기본값은 refresh token 에 시간 제한이 없으므로(회전 방식), **쿠키 수명이 곧 자동 로그인 기간**이 된다.

**Files:**
- Modify: `lib/supabase/server.ts` (`createSupabaseServerClient`의 `setAll`)
- Modify: `middleware.ts` (세션 갱신 시 쿠키를 쓰는 자리)

**Interfaces:**
- Consumes: Task 3이 정리한 `middleware.ts`
- Produces: 인증 쿠키의 `maxAge`가 14일(1,209,600초). 다른 Task는 이 값에 의존하지 않는다.

- [ ] **Step 1: 공용 상수를 만든다**

`lib/supabase/config.ts` 파일이 이미 있다면 거기에, 없으면 `lib/supabase/server.ts` 상단에 추가:

```typescript
/** 자동 로그인 유지 기간. Supabase refresh token 은 기본적으로 시간 제한이 없으므로
 *  브라우저 쿠키 수명이 곧 재로그인 없이 쓸 수 있는 기간이 된다. */
export const AUTH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 14
```

- [ ] **Step 2: 서버 클라이언트의 쿠키에 수명을 준다**

`lib/supabase/server.ts`의 `setAll` 을 수정:

```typescript
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, {
              ...options,
              maxAge: options?.maxAge ?? AUTH_COOKIE_MAX_AGE_SECONDS,
            });
          });
        } catch {
          // Server Components cannot set cookies. Middleware refresh handles it.
        }
      }
```

- [ ] **Step 3: middleware 의 쿠키에도 같은 수명을 준다**

`middleware.ts`에서 `response.cookies.set(...)` 을 호출하는 자리를 찾아 같은 방식으로 `maxAge`를 넣는다:

```typescript
            response.cookies.set(name, value, {
              ...options,
              maxAge: options?.maxAge ?? AUTH_COOKIE_MAX_AGE_SECONDS,
            })
```

`import { AUTH_COOKIE_MAX_AGE_SECONDS } from './lib/supabase/server'` 를 상단에 추가한다.

- [ ] **Step 4: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공

- [ ] **Step 5: 실제 쿠키 수명을 확인한다**

dev 서버를 띄우고 `/home` 으로 로그인한 뒤:

```bash
curl -s -i -c /tmp/cookies.txt "http://localhost:3000/home" >/dev/null
python -c "
import time
now = time.time()
for line in open('/tmp/cookies.txt'):
    if line.startswith('#') or not line.strip(): continue
    p = line.split('\t')
    if len(p) >= 7 and 'sb-' in p[5]:
        days = (int(p[4]) - now) / 86400
        print(f'{p[5]}: 약 {days:.1f}일 남음')
"
```

Expected: `sb-...-auth-token` 계열 쿠키가 **약 14일** 남음으로 나온다

- [ ] **Step 6: 커밋**

```bash
git add lib/supabase/server.ts middleware.ts
git commit -m "feat(auth): 자동 로그인 14일 유지

Supabase refresh token 은 기본적으로 시간 제한이 없고 회전 방식이라,
브라우저 쿠키 수명이 곧 재로그인 없이 쓸 수 있는 기간이 된다.
서버 클라이언트와 middleware 양쪽에서 maxAge 를 14일로 지정한다.

프로젝트 설정 변경은 필요 없다."
```

---

## Task 6: 첨부 백엔드 — `storage_path`만 저장 + 기존 데이터 이행

**Files:**
- Modify: `backend/app/services/attachment_storage.py` (`ensure_bucket`, `_upload_sync`, `_upload_bytes_sync`)
- Create: `scripts/backfill_attachment_storage_path.py`
- Test: `backend/tests/test_attachment_storage_paths.py`

**Interfaces:**
- Consumes: 없음
- Produces: `extracted_content.sources[]`의 각 원소가 `storage_path`를 갖고 `public_url`을 갖지 않는다. Task 7의 라우트가 `storage_path`로 서명 URL을 만든다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_attachment_storage_paths.py` 생성:

```python
import unittest

from app.services import attachment_storage


class ObjectKeyTest(unittest.TestCase):
    def test_upload_result_has_no_public_url(self):
        """업로드 결과에 public_url 이 있으면 안 된다.

        URL 은 저장하지 않고 읽는 시점에 서명 URL 로 발급한다.
        저장된 URL 은 만료 개념이 없어 '학부모만 열람' 목표와 모순된다.
        """
        result_keys = attachment_storage.UPLOAD_RESULT_KEYS
        self.assertIn("storage_path", result_keys)
        self.assertNotIn("public_url", result_keys)

    def test_bucket_is_private(self):
        """버킷 자동 생성 시 공개로 만들면 안 된다."""
        self.assertFalse(attachment_storage.BUCKET_PUBLIC)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_attachment_storage_paths -v
```

Expected: FAIL — `AttributeError: module has no attribute 'UPLOAD_RESULT_KEYS'`

- [ ] **Step 3: 최소 구현**

`backend/app/services/attachment_storage.py` 상단, `BUCKET` 정의 아래에 추가:

```python
BUCKET_PUBLIC = False
UPLOAD_RESULT_KEYS = ("storage_path",)
```

`ensure_bucket` 의 생성 옵션을 바꾼다:

```python
        client.storage.create_bucket(BUCKET, options={"public": BUCKET_PUBLIC})
```

`_upload_sync` 의 마지막 두 줄을 바꾼다:

```python
    # public_url 은 저장하지 않는다. 읽는 시점에 서명 URL 로 발급한다(Task 7).
    return {"storage_path": object_path}
```

`_upload_bytes_sync` 도 동일하게:

```python
    return {"storage_path": object_path}
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_attachment_storage_paths -v
```

Expected: PASS (2 tests)

- [ ] **Step 5: 기존 백엔드 테스트가 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend python -m unittest discover backend/tests
```

Expected: 전부 통과. `public_url`을 기대하는 테스트가 있으면 그 테스트도 `storage_path` 기준으로 고친다.

- [ ] **Step 6: 이행 스크립트를 쓴다**

`scripts/backfill_attachment_storage_path.py`:

```python
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
```

- [ ] **Step 7: 미리보기로 돌려 규모를 확인한다**

```bash
export SUPABASE_URL="$(gh variable get NEXT_PUBLIC_SUPABASE_URL)"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python scripts/backfill_attachment_storage_path.py
```

Expected: `public_url 있음 53` 근처, `역산 성공` + `역산 실패 → 포기` 합이 그 수와 일치. **역산 실패가 15건을 넘으면 중단하고 보고할 것** — URL 형식 가정이 틀렸다는 뜻이다.

- [ ] **Step 8: 실제로 적용한다**

```bash
APPLY=1 python scripts/backfill_attachment_storage_path.py
```

Expected: `N건 갱신 완료`

- [ ] **Step 9: `public_url` 이 남지 않았는지 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notices?select=extracted_content&extracted_content=not.is.null&limit=1000')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=120).read().decode())
pub=sum(1 for x in rows for s in (x.get('extracted_content') or {}).get('sources') or [] if s.get('public_url'))
sp=sum(1 for x in rows for s in (x.get('extracted_content') or {}).get('sources') or [] if s.get('storage_path'))
print('public_url 남은 수:', pub, '| storage_path 보유:', sp)
"
```

Expected: `public_url 남은 수: 0`

- [ ] **Step 10: 커밋**

```bash
git add backend/app/services/attachment_storage.py backend/tests/test_attachment_storage_paths.py scripts/backfill_attachment_storage_path.py
git commit -m "feat(attachments): public_url 저장 중단, storage_path 만 남긴다

저장된 공개 URL 은 만료 개념이 없어 '해당 학교 학부모만 열람' 목표와 모순된다.
URL 은 읽는 시점에 서명 URL 로 발급한다(다음 Task).

버킷 자동 생성도 비공개로 바꾼다.

기존 데이터는 public_url 에서 오브젝트 키를 역산해 storage_path 를 채운다.
역산 실패분은 재추출하지 않고 포기한다(사용자 결정) — public_url 을 제거해
깨진 링크가 아니라 '첨부 없음' 으로 보이게 하고 errors 에 사유를 남긴다."
```

---

## Task 7: 첨부 서명 URL 라우트 + 버킷 잠금

**Files:**
- Create: `app/api/notices/[noticeId]/attachments/[sourceId]/route.ts`
- Modify: `lib/notices.ts` (`buildAttachmentFiles` 370~388행, 첨부 카드 `publicUrl` 334행)
- Create: `supabase/migrations/0037_notice_attachments_private.sql`

**Interfaces:**
- Consumes: Task 6이 채운 `sources[].storage_path`, Task 3~5가 복구한 로그인 세션
- Produces: `GET /api/notices/{noticeId}/attachments/{sourceId}` → 302 리다이렉트(서명 URL). 권한 없으면 404.

- [ ] **Step 1: 라우트를 쓴다**

`app/api/notices/[noticeId]/attachments/[sourceId]/route.ts`:

```typescript
import { NextResponse, type NextRequest } from 'next/server'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'

const BUCKET = 'notice-attachments'
const SIGNED_URL_TTL_SECONDS = 300

/** 첨부 다운로드. 로그인한 사용자가 해당 학교에 자녀를 등록한 경우에만
 *  단명 서명 URL 로 302 리다이렉트한다. 권한이 없으면 존재 여부도 알리지 않는다(404). */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ noticeId: string; sourceId: string }> },
) {
  const { noticeId, sourceId } = await params

  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'not_found' }, { status: 404 })

  const service = createSupabaseServiceClient()

  const { data: notice } = await service
    .from('notices')
    .select('id,school_id,extracted_content')
    .eq('id', noticeId)
    .maybeSingle()
  if (!notice?.school_id) return NextResponse.json({ error: 'not_found' }, { status: 404 })

  const { data: children } = await service
    .from('children')
    .select('school_id')
    .eq('user_id', user.id)
    .eq('school_id', notice.school_id)
    .limit(1)
  if (!children || children.length === 0) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 })
  }

  const extracted = notice.extracted_content as Record<string, unknown> | null
  const sources = Array.isArray(extracted?.sources) ? extracted.sources : []
  const source = sources.find(
    (s) => s && typeof s === 'object' && (s as Record<string, unknown>).source_id === sourceId,
  ) as Record<string, unknown> | undefined

  const storagePath = typeof source?.storage_path === 'string' ? source.storage_path : ''
  if (!storagePath) return NextResponse.json({ error: 'not_found' }, { status: 404 })

  const filename = typeof source?.filename === 'string' ? source.filename : undefined
  const { data: signed, error } = await service.storage
    .from(BUCKET)
    .createSignedUrl(storagePath, SIGNED_URL_TTL_SECONDS, filename ? { download: filename } : undefined)

  if (error || !signed?.signedUrl) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 })
  }
  return NextResponse.redirect(signed.signedUrl)
}
```

- [ ] **Step 2: 읽기 경로를 라우트 주소로 바꾼다**

`lib/notices.ts`의 `buildAttachmentFiles` 를 아래로 교체한다 (기존 `public_url` 기반 구현을 지운다):

```typescript
/** extracted_content.sources[] → 첨부 다운로드 경로(중복 제거).
 *  실제 URL 은 저장하지 않는다. 접근 검사를 거쳐 서명 URL 을 내주는 라우트를 가리킨다. */
function buildAttachmentFiles(
  extracted: Record<string, unknown> | null,
  noticeId: string,
): NoticeAttachmentFile[] {
  if (!extracted) return []
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const seen = new Set<string>()
  const files: NoticeAttachmentFile[] = []
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    const storagePath = typeof obj.storage_path === 'string' ? obj.storage_path.trim() : ''
    const sourceId = typeof obj.source_id === 'string' ? obj.source_id.trim() : ''
    if (!storagePath || !sourceId || seen.has(sourceId)) continue
    seen.add(sourceId)
    const filename = typeof obj.filename === 'string' && obj.filename.trim() ? obj.filename.trim() : 'attachment'
    files.push({
      filename,
      publicUrl: `/api/notices/${noticeId}/attachments/${encodeURIComponent(sourceId)}`,
      previewable: isPreviewable(obj),
    })
  }
  return files
}
```

`buildAttachmentFiles(...)` 호출부에 `noticeId`를 넘기도록 고친다. 그리고 334행 부근의 첨부 카드도 같은 방식으로 바꾼다:

```typescript
      publicUrl: typeof obj.source_id === 'string' && typeof obj.storage_path === 'string'
        ? `/api/notices/${noticeId}/attachments/${encodeURIComponent(obj.source_id)}`
        : null,
```

- [ ] **Step 3: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공. `noticeId` 인자 누락이 있으면 여기서 잡힌다.

- [ ] **Step 4: 로그인 없이 접근하면 막히는지 확인한다**

dev 서버를 띄운 뒤 실제 공지 ID와 source_id 를 하나 골라:

```bash
NID=$(python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notices?select=id,extracted_content&extracted_content=not.is.null&limit=20')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
for x in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()):
    for s in (x.get('extracted_content') or {}).get('sources') or []:
        if s.get('storage_path'): print(x['id'], s['source_id']); raise SystemExit
")
set -- $NID
curl -s -o /dev/null -w "비로그인 → HTTP %{http_code}\n" "http://localhost:3000/api/notices/$1/attachments/$2"
```

Expected: `HTTP 404`

- [ ] **Step 5: 로그인 후 접근하면 되는지 확인한다**

```bash
curl -s -c /tmp/c.txt -o /dev/null "http://localhost:3000/home"
curl -s -b /tmp/c.txt -o /dev/null -w "로그인 → HTTP %{http_code} → %{redirect_url}\n" \
  "http://localhost:3000/api/notices/$1/attachments/$2"
```

Expected: `HTTP 307` 또는 `302`, redirect_url 이 `.../object/sign/notice-attachments/...` 형태

> 개발 계정의 자녀가 그 학교에 등록되어 있지 않으면 404 가 나온다. 그건 **정상 동작**이다.
> 확인하려면 개발 계정으로 온보딩을 마쳐 해당 학교에 자녀를 등록한 뒤 다시 시도한다.

- [ ] **Step 6: 버킷 잠금 마이그레이션을 쓴다**

`supabase/migrations/0037_notice_attachments_private.sql`:

```sql
-- 0011 이 이 버킷을 public 으로 만들면서 주석에 "보안 미적용" 이라고 스스로 적어 두었다.
-- 이제 앱이 접근 검사를 거쳐 단명 서명 URL 을 발급하므로(app/api/notices/[noticeId]/attachments)
-- 버킷을 비공개로 돌린다.
--
-- storage.objects 정책은 추가하지 않는다(현재 0개 = service_role 전용 유지).
-- 서명 URL 발급이 service_role 로 이뤄지므로 정책이 필요 없다.

update storage.buckets
set public = false
where id = 'notice-attachments';
```

- [ ] **Step 7: 번호 검사를 통과하는지 확인한다**

```bash
python scripts/check_migration_numbers.py
```

Expected: `마이그레이션 38개, 번호 중복 없음`

- [ ] **Step 8: 커밋 (적용은 머지 시 Task 2 워크플로가 한다)**

```bash
git add app/api/notices lib/notices.ts supabase/migrations/0037_notice_attachments_private.sql
git commit -m "feat(attachments): 서명 URL 라우트 + 학부모 스코프 검사, 버킷 비공개 전환

첨부 URL 을 저장하지 않고, 요청 시 접근 검사를 거쳐 5분짜리 서명 URL 로
302 리다이렉트한다. 검사는 '로그인한 사용자가 그 학교에 자녀를 등록했는가' 다.
권한이 없으면 존재 여부도 알리지 않고 404 를 낸다.

데모 학교를 예외로 두지 않는다(데모 종료 결정). 데모 학교 첨부가 막히는 것은
의도된 동작이다.

버킷 잠금 마이그레이션은 읽기 경로 전환과 같은 커밋에 들어가지만,
실제 적용은 머지 시 db-migrate 워크플로가 수행한다."
```

- [ ] **Step 9: 머지 후 실제로 잠겼는지 확인한다**

머지되어 워크플로가 `0037`을 적용한 뒤:

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notices?select=extracted_content&extracted_content=not.is.null&limit=5')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
for x in rows:
    for s in (x.get('extracted_content') or {}).get('sources') or []:
        if s.get('storage_path'):
            print(u+'/storage/v1/object/public/notice-attachments/'+s['storage_path']); raise SystemExit
" > /tmp/oldurl.txt
curl -s -o /dev/null -w "옛 공개 URL 직접 접근 → HTTP %{http_code}\n" "$(cat /tmp/oldurl.txt)"
```

Expected: `HTTP 400` 또는 `404` (공개 접근 거부). `200`이 나오면 마이그레이션이 적용되지 않은 것이다.

---

## 자체 검토

**1. 스펙 커버리지**

| 스펙 항목 | 담당 Task |
|---|---|
| A1 작업 큐 접근 차단 | Task 1 |
| A2(a) 우회 스위치 통합 | Task 3 |
| A2(b) `/home` 개발 진입로 | Task 4 |
| A2(c) 14일 세션 | Task 5 |
| A2(d) 데모 진입 경로 제거 | Task 3 Step 4 |
| A3(a) `public_url` 저장 중단 | Task 6 Step 3 |
| A3(b) 발급 지점 단일화 | Task 7 Step 1 |
| A3(c) 서명 URL 5분 | Task 7 Step 1 (`SIGNED_URL_TTL_SECONDS`) |
| A3(d) 기존 데이터 이행 | Task 6 Step 6~9 |
| A3(e) 데모 예외 없음 | Task 7 Step 1 (예외 분기 자체가 없음) |
| A3(f) 실패분 포기 | Task 6 Step 6 (`ORPHAN_ERROR`) |
| A3 버킷 비공개 | Task 7 Step 6 |
| A4 이력 정합 | Task 1 Step 3~7 |
| A4 워크플로 | Task 2 |
| A4 번호 규율 | Task 2 Step 1~5 |

**빠진 것 없음.** 스펙 §5.2(a)가 `middleware.ts` 분기를 "남긴다"고 했다가 자체검토에서 "제거"로 정정된 이력이 있는데, 이 계획은 **제거**를 따른다.

**2. 자리표시자 점검** — "TBD"·"적절히 처리"·"비슷하게" 없음. 모든 코드 단계에 실제 코드가 들어 있다.

**3. 타입 일관성**

- `UPLOAD_RESULT_KEYS`, `BUCKET_PUBLIC` — Task 6 Step 1에서 테스트가 참조, Step 3에서 정의. 일치.
- `AUTH_COOKIE_MAX_AGE_SECONDS` — Task 5 Step 1에서 정의, Step 2·3에서 사용. 일치.
- `ORPHAN_ERROR` — Task 6 Step 6에서만 쓰인다.
- `buildAttachmentFiles(extracted, noticeId)` — Task 7 Step 2에서 시그니처가 바뀌므로 호출부 수정이 같은 Step에 포함되어 있다.
- `storage_path` / `source_id` — Task 6이 생산, Task 7이 소비. 키 이름 일치.
- `SIGNED_URL_TTL_SECONDS = 300` — 스펙의 "기본 5분"과 일치.

---

## 선행 준비물

Task 착수 전에 사람이 해둬야 하는 것:

| | 항목 | 필요한 Task |
|---|---|---|
| ✅ | Supabase CLI 로그인 | Task 1, 2 (완료) |
| ⬜ | GitHub Secret `SUPABASE_ACCESS_TOKEN` | Task 2 |
| ⬜ | GitHub Variable `SUPABASE_PROJECT_REF` = `aoihmzewthgyoxtejfwo` | Task 2 |
| ⬜ | Supabase Auth 에 개발용 계정 생성 | Task 4 |
| ⬜ | GCP Secret `dev-login-email`, `dev-login-password` | Task 4 |
| ⬜ | Google OAuth 리디렉션 URI 확인 (`https://aoihmzewthgyoxtejfwo.supabase.co/auth/v1/callback`) | Task 3 이후 실사용 |

`SUPABASE_DB_PASSWORD`는 **필요 없다** (검증 완료).
