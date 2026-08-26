# 관리자 콘솔 · 운영 화면화 · 관측 기반 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 운영자가 손으로 하던 일(잡 큐 조회·학교 수집 상태 확인·재크롤·강제 재추출·스케줄러 정지/재개)을 화면에서 하게 만든다. 그 화면이 보여줄 데이터가 실제로 생기도록 구조화 로깅·실행 이력·검토 신호를 먼저 세운다. 관리자 인증은 학부모 인증과 **물리적으로 분리된 체계**로 만든다 — `/home` 개발 진입로가 프로덕션에서 열려 있어도 관리자 표면에 한 걸음도 못 들어가야 한다.

**Architecture:** 네 층을 순서대로 쌓는다. ① 관리자 자격 저장소를 별도 테이블(RLS 활성·정책 0개)에 만들고 pgcrypto 해시 + 자체 세션 쿠키로 게이트를 세운다 ② 화면이 읽을 데이터를 만든다 — 구조화 JSON 로깅, `crawl_run_history` 실행 이력, `needs_review` 검토 신호 ③ 읽기 전용 화면(잡 큐·학교 수집 상태)을 올려 «쓰기 조작의 결과를 확인할 창»을 먼저 확보한다 ④ GCP 제어를 FastAPI `/admin/*` 에 붙이고 그 위에 쓰기 화면(스케줄러·재크롤·재추출)을 올린다. 각 층은 단독 롤백이 가능하다.

**Tech Stack:** Next.js 16.2.4 App Router (React 19), `@supabase/ssr` + `@supabase/supabase-js`, Supabase(Postgres + pgcrypto, 도쿄 리전), Python 3.12 FastAPI, `httpx`, `google-auth`(ADC), Cloud Run Jobs v2 / Cloud Scheduler v1 Admin API, Supabase CLI, GitHub Actions

**Spec:** [docs/superpowers/specs/2026-08-27-F-admin-console-design.md](../specs/2026-08-27-F-admin-console-design.md)

**선행 사업:** [docs/superpowers/plans/2026-08-27-security-foundation.md](2026-08-27-security-foundation.md) (사업 A) — **Task 1~7 전부 완료·머지된 뒤에 착수한다.**

## Global Constraints

- **사업 A 가 남긴 상태를 전제로 한다.** 이 계획은 아래를 사실로 놓고 설계됐다. 착수 시 하나라도 다르면 **중단하고 보고할 것.**
  - `middleware.ts` 에 `TEST_ENTRY_BYPASS` 분기와 `isPreview`(`ui_preview` 쿠키) 분기가 **없다**. `app/demo/route.ts` 와 `lib/test-entry-bypass.ts` 가 **삭제됐다**.
  - 남은 우회 스위치는 `DEV_LOGIN_ENABLED` 하나이고, **프로덕션에서 `true`** 다. 즉 `/home` 한 번으로 누구나 유효한 학부모 세션을 얻는다.
  - `.github/workflows/db-migrate.yml` 이 있고 `main` 머지 시 `supabase db push --include-all` 을 돌린다. `scripts/check_migration_numbers.py` 가 PR 에서 번호 중복을 막는다.
  - `supabase/migrations/0036_app_jobs_rls.sql`(app_jobs RLS)·`0037_notice_attachments_private.sql` 이 적용됐고 `supabase migration list` 가 정합하다.
- **마이그레이션 번호**: 이 사업은 **`0038`(관리자 자격)과 `0041`(관측)** 을 쓴다. 형제 계획서를 실측한 배정표는 다음과 같다.

  | 번호 | 주인 | 근거 |
  |---|---|---|
  | `0035` | (예약, 미사용) | `docs/기능명세서-자녀-개인일정.md` — `child_personal_schedules` |
  | `0036`·`0037` | 사업 A | `2026-08-27-security-foundation.md:15` (`app_jobs` RLS, 첨부 비공개) |
  | **`0038`** | **이 사업** | 관리자 자격 (사업 E 계획서 `:15` 도 «0038은 사업 F» 로 비워 둠) |
  | `0039`·`0040` | 사업 E | `2026-08-27-E-rss-official-api.md:40,46` — `school_events_source`, `school_crawl_state_rss_feed` |
  | **`0041`** | **이 사업** | 관측 |
  | `0045`~`0052` | 사업 D | `2026-08-27-D-db-cleanup.md:44-63` |

  **스펙 §5.3 은 이 사업에 `0039` 를 배정했지만 그 자리는 사업 E 가 이미 가져갔다.** 관측 마이그레이션을 `0041` 로 옮긴다. `0042`~`0044` 는 비어 있으므로 이 사업이 마이그레이션을 하나 더 만들어야 하면 거기서 잇는다. 번호가 겹치면 사업 A 의 `check_migration_numbers.py` 가 PR 에서 잡지만, 잡힌 뒤 파일명을 바꾸면 CLI 가 미적용으로 보고 재실행하므로 **처음부터 겹치지 않게 잡는다.**
- **마이그레이션 적용 통로**: `supabase db push` 를 손으로 돌리지 않는다. 마이그레이션 파일을 커밋하고 **머지하면 사업 A 의 `db-migrate` 워크플로가 적용**한다. 적용 확인 Step 은 «머지 후» 라고 명시한다.
- **관리자 규모 기본값 — 1명 / 학교 관계자 없음 / 2단계 인증 없음.** 스펙 §15 Q1·Q2·Q3 이 미결이므로 이 값을 기본값으로 잡는다. 단 **스키마는 확장 가능하게** 만든다:
  - `admin_users` 는 사람별 행이다(계정 1개여도 테이블). 사람이 늘면 `admin_set_password` RPC 를 한 번 더 부르면 끝이고, 감사 로그에 «누가» 가 남는다.
  - `admin_users.totp_secret` 컬럼 자리를 만들되 **읽지도 쓰지도 않는다.** 2단계 인증이 필요해지면 컬럼 추가 없이 검증 코드만 붙인다.
  - `profiles.role` 은 **복원하지 않는다.** `0001_initial_schema.sql:138-141` 의 `"profiles update own"` 정책이 행 단위라 `role` 컬럼까지 열려 있고, `/home` 세션의 anon 키로 `PATCH /rest/v1/profiles {"role":"admin"}` 이 통한다. 학교 관계자 권한이 «준다» 로 답해질 때 별건으로 복원하며, 그때 `revoke update (role) on public.profiles from authenticated` 가 동반되어야 한다.
- **🔴 비밀번호는 어디에도 기록하지 않는다.** 이 계획서에 값이 없고, Step 도 값을 만들지 않는다. 무작위 생성 → GCP Secret Manager 저장 → DB 에는 pgcrypto 해시만. 화면·stdout·git·명령줄 인자·URL 어디에도 원본이 나오지 않는다. 출력은 **길이만** 찍는다. 프로비저닝 스크립트는 **저장소에 커밋하지 않는다**(일회성). 회전은 같은 절차를 다시 밟는 것이다.
- **쿠키 접두 결정 — 스펙 §3.5 의 모순을 정정한다.** 스펙은 «`Path=/admin`, `__Host-` 접두» 를 함께 요구하지만 **둘은 배타적이다**: `__Host-` 접두는 `Secure` + `Domain` 없음 + **`Path=/`** 를 강제한다. 이 계획은 **`__Host-naranhi_admin` + `Path=/`** 를 택한다. 쿠키가 `HttpOnly` 라 어차피 스크립트가 읽을 수 없으므로 `Path` 격리가 주는 이득은 없고, `__Host-` 가 주는 «형제 호스트가 이 쿠키를 덮어쓸 수 없다» 는 실질 이득이 더 크다. 나머지 속성은 스펙대로 `HttpOnly` + `Secure` + `SameSite=Strict`, 수명 8시간 절대 만료·갱신 없음.
- **middleware 게이트는 «쿠키 존재» 만 본다.** middleware 는 Edge 런타임이고 `service_role` 키도 `node:crypto` 도 쓸 수 없다. 매 요청 DB 왕복도 부적절하다. 따라서 middleware 의 관리자 판정은 **모든 분기보다 앞에서 «관리자 쿠키가 있는가»** 만 보고, **실제 세션 검증은 레이아웃과 모든 `app/api/admin/**` 핸들러가 `requireAdminSession()` 으로 다시 한다**(이중 방어 ②). 이 배치의 핵심 성질은 그대로다 — 학부모 세션 쿠키(`sb-…`)로도, `ui_preview` 쿠키로도 게이트를 통과할 수 없다.
- **관리자 조회는 Next.js, GCP 제어만 FastAPI.** FastAPI 는 `--allow-unauthenticated` 로 뜬 사실상 공개 표면이다. 반대로 `run.jobs.run` / Cloud Scheduler 는 이미 `naranhi-api` 런타임 SA 가 ADC 권한을 갖고 있으므로 그쪽에 라우터를 얹는 편이 권한 확산이 적다. **`ADMIN_API_TOKEN` 은 브라우저에 절대 내려가지 않는다** — 호출자는 Next.js 서버뿐이다.
- **`_require_internal_token` 을 재사용하지 않는다.** 그것은 토큰 미설정 + `ENVIRONMENT=local` 이면 통과시킨다(`backend/app/api/crawler.py:25-26`). 새 `_require_admin_token` 은 **local 예외 없이** 토큰 미설정 시 환경 불문 503, 불일치 시 401 이다.
- **페이징을 만들지 않는다.** 운영 실측(2026-08-26)이 notices 38 / schools 8 / app_jobs 230 이다. 커서 페이징·가상 스크롤·서버 집계 캐시를 넣지 않는다. 필터와 정렬뿐이다.
- **범위 최소 예외 1건**: `lib/supabase/server.ts` 에 `import 'server-only'` **한 줄**을 추가한다. `createSupabaseServiceClient()` 가 클라이언트 번들로 새어나갈 수 있는 상태이고, 이 사업이 그 함수를 관리자 경로 전반에서 쓰기 때문이다. 다른 수정은 하지 않는다.
- **실패 알림(§9.4)은 이 계획에 Step 이 없다.** 스펙 §15 Q7(«알림을 어디로 보내는가»)이 미결이라 Cloud Monitoring notification channel 을 만들 수 없다. Task 8 이 `crawl_run_history.outcome` 을, Task 10 이 잡 큐 적체를 **화면에 드러내는** 데까지 하고, 채널이 정해지면 별건으로 붙인다.
- **스크립트를 지우지 않는다.** `scripts/recrawl_trigger.py`, `scripts/probe_school_state.py`, `scripts/_hambak_jobstatus.py` 는 화면이 고장 났을 때 돌아갈 곳이다. 최소 한 분기 병행 유지한다.
- **테스트 실행**:
  - 백엔드: `PYTHONPATH=backend python -m unittest discover backend/tests`
  - 프론트: `npm run typecheck` + `npm run build` (**프론트 테스트 러너가 없다** — `package.json:5-11` 에 test 스크립트 없음. 검증은 타입체크·빌드·실제 HTTP 확인으로 한다)
- **커밋 메시지**: 한국어, `type(scope): 요약` 형식.

---

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `supabase/migrations/0038_admin_console_auth.sql` | `admin_users`/`admin_sessions`/`admin_audit_log` + 검증·설정 RPC | 신규 (Task 1) |
| `scripts/verify_admin_tables_rls.py` | anon 키로 관리자 테이블이 보이는지 검사 | 신규 (Task 1) |
| `types/database.ts` | Supabase 타입 정의 | 수정 (Task 3, 7) |
| `lib/supabase/server.ts` | Supabase 클라이언트 팩토리 | 수정 (Task 3 — `server-only` 한 줄) |
| `lib/school-crawl-state.ts` | 학교 수집 상태 조회 | 수정 (Task 3 — `board_watermarks` 누락 보강) |
| `lib/admin/cookie.ts` | 관리자 쿠키 상수 (Edge 안전, import 0개) | 신규 (Task 4) |
| `lib/admin/session.ts` | 자격 검증·세션 발급/검증/폐기·감사 로그 | 신규 (Task 4) |
| `middleware.ts` | 인증 게이트 | 수정 (Task 5 — 맨 앞에 `adminGate`) |
| `app/(admin)/layout.tsx` | 관리자 셸 (학부모 레이아웃 비상속) | 신규 (Task 5) |
| `app/(admin)/admin/login/page.tsx` | 로그인 화면 — 유일한 미인증 관리자 경로 | 신규 (Task 5) |
| `app/(admin)/admin/login/AdminLoginForm.tsx` | 로그인 폼 (클라이언트) | 신규 (Task 5) |
| `app/(admin)/admin/(protected)/layout.tsx` | `requireAdminSession()` 재검사 — 이중 방어 ② | 신규 (Task 5) |
| `app/(admin)/admin/(protected)/page.tsx` | 대시보드 | 신규 (Task 5), 수정 (Task 8, 13) |
| `app/api/admin/login/route.ts` | 자격 검증 → 세션 발급 → 쿠키 | 신규 (Task 5) |
| `app/api/admin/logout/route.ts` | 세션 `revoked_at` | 신규 (Task 5) |
| `backend/app/core/logging_setup.py` | 구조화 JSON 로깅 | 신규 (Task 6) |
| `backend/tests/test_logging_setup.py` | 로깅 포매터 테스트 | 신규 (Task 6) |
| `backend/app/main.py` · `worker_main.py` · `jobs/*.py` (4) | 로깅 진입점 6개 | 수정 (Task 6) |
| `supabase/migrations/0041_admin_console_observability.sql` | `crawl_run_history` + `needs_review`/`review_reason` | 신규 (Task 7) |
| `backend/app/services/crawl_run_history_service.py` | 실행 이력 적재 + `outcome` 판정 | 신규 (Task 8) |
| `backend/tests/test_crawl_run_history.py` | `outcome` 판정 테스트 | 신규 (Task 8) |
| `backend/app/jobs/scheduled_school_crawler.py` | 정기 크롤 진입점 | 수정 (Task 8) |
| `backend/app/services/notice_service.py` | 번역 저장 (`_save_translation_result`) | 수정 (Task 9) |
| `backend/tests/test_translation_review_signal.py` | 검토 신호 테스트 | 신규 (Task 9) |
| `lib/admin/jobs.ts` | `app_jobs` 조회·재시도·포기 | 신규 (Task 10) |
| `app/api/admin/jobs/route.ts` · `jobs/[jobId]/route.ts` | 잡 큐 API | 신규 (Task 10) |
| `app/(admin)/admin/(protected)/jobs/page.tsx` + `JobActions.tsx` | 잡 큐 콘솔 | 신규 (Task 10) |
| `lib/admin/schools.ts` | 학교 + 수집 상태 + 공지 수 | 신규 (Task 11) |
| `app/(admin)/admin/(protected)/schools/page.tsx` | 학교 수집 상태 화면 | 신규 (Task 11) |
| `backend/app/services/gcp_admin_service.py` | Scheduler 제어 + `run_job_with_args` | 신규 (Task 12) |
| `backend/app/api/admin.py` | FastAPI `/admin/*` + `_require_admin_token` | 신규 (Task 12) |
| `backend/tests/test_admin_api.py` | 토큰 게이트·overrides·화이트리스트 | 신규 (Task 12) |
| `backend/app/core/config.py` | `ADMIN_API_TOKEN`, `SCHEDULER_LOCATION` | 수정 (Task 12) |
| `backend/app/main.py` | 라우터 등록 | 수정 (Task 12) |
| `.github/workflows/deploy-api-cloud-run.yml` | API 배포 env/secret | 수정 (Task 12) |
| `.github/workflows/deploy-cloud-run.yml` | 웹 배포 secret | 수정 (Task 12) |
| `lib/admin/gcp.ts` | Next.js → FastAPI `/admin/*` 서버 호출 | 신규 (Task 13) |
| `app/api/admin/schedulers/route.ts` · `[name]/route.ts` | 스케줄러 API | 신규 (Task 13) |
| `app/(admin)/admin/(protected)/schedulers/page.tsx` + `SchedulerActions.tsx` | 스케줄러 화면 | 신규 (Task 13) |
| `lib/admin/recrawl.ts` | 재크롤 미리보기·실행 | 신규 (Task 14) |
| `app/api/admin/schools/[schoolId]/recrawl/route.ts` | 미리보기(GET)·실행(POST) | 신규 (Task 14) |
| `app/(admin)/admin/(protected)/schools/RecrawlButton.tsx` | 확인 다이얼로그 | 신규 (Task 14) |
| `app/api/admin/notices/[noticeId]/reextract/route.ts` | 강제 재추출 | 신규 (Task 15) |
| `app/(admin)/admin/(protected)/notices/page.tsx` + `ReextractButton.tsx` | 공지 검수 화면 | 신규 (Task 15) |
| `lib/admin/reviews.ts` · `lib/admin/runs.ts` | 검토 큐 · 실행 이력 조회 | 신규 (Task 16) |
| `app/(admin)/admin/(protected)/reviews/page.tsx` · `runs/page.tsx` | 검토 큐 · 실행 이력 화면 | 신규 (Task 16) |

---

## 실행 순서 (스펙 §11 정정)

스펙 §11 은 읽기 화면(배포 4·5)을 관측 기반(배포 6·7)보다 **앞**에 둔다. 이 계획은 **뒤집는다.**

근거: 스펙 §11 이 4·5 를 앞에 둔 이유는 «쓰기 조작의 결과를 볼 창이 먼저 있어야 한다» 인데, 그 논거는 **쓰기 화면(9·10·11)에 대한 것**이지 관측 기반에 대한 것이 아니다. 관측 기반은 반대로 **지연이 곧 데이터 손실**이다 — 구조화 로깅과 `crawl_run_history` 가 늦게 들어가면 그 사이 실행분의 이력이 영영 없다. 스펙 §9 머리말도 «화면이 보여줄 데이터가 없으면 화면도 없다» 고 적었다. 읽기 화면과 쓰기 화면의 상대 순서는 그대로 지킨다.

```
Task 1   0038 관리자 자격 스키마              (RLS 활성·정책 0개)
Task 2   관리자 계정 프로비저닝               (무작위 → Secret Manager)
Task 3   프론트 데이터 접근 기반              (server-only / 타입 / board_watermarks)
Task 4   lib/admin/session.ts
Task 5   middleware 게이트 + 로그인 + 이중 방어  ← 여기까지 인증 완료
Task 6   구조화 로깅 (진입점 6개)
Task 7   0041 관측 스키마
Task 8   실행 이력 적재 (outcome 구분)
Task 9   번역 검토 신호 복구                  ← 여기까지 관측 기반 완료
Task 10  P0-2 잡 큐 콘솔
Task 11  P0-3 학교 수집 상태                  ← 여기까지 읽기 화면
Task 12  FastAPI /admin 라우터 + IAM
Task 13  P1-1 스케줄러 정지/재개
Task 14  P1-2 재크롤 (미리보기 → 확인 → 실행)
Task 15  P1-3 강제 재추출
Task 16  P2-1 검토 큐 + P2-2 실행 이력 화면
```

---

## Task 1: `0038` 관리자 자격 스키마

관리자 자격 저장소를 학부모 인증과 **물리적으로 단절**시킨다. 세 테이블 모두 RLS 활성 + 정책 0개다 — 선례는 `0013_school_crawl_state.sql:72`, `0036_app_jobs_rls.sql`. 이 상태에서 anon/authenticated 는 테이블의 존재조차 확인할 수 없고, `/home` 이 발급하는 세션은 전부 anon 키 위에서 돈다.

비밀번호 해시에 새 의존성이 없다 — `0001_initial_schema.sql:1` 이 `create extension if not exists "pgcrypto"` 를 이미 실행했다. `crypt()` / `gen_salt('bf')` 를 `security definer` 함수 안에서 쓰면 해시도 원본도 애플리케이션 메모리로 나오지 않는다.

**Files:**
- Create: `supabase/migrations/0038_admin_console_auth.sql`
- Create: `scripts/verify_admin_tables_rls.py`

**Interfaces:**
- Consumes: 사업 A 가 남긴 `db-migrate` 워크플로, `0037` 까지 정합한 원격 이력
- Produces:
  - 테이블 `public.admin_users(id, username, password_hash, display_name, is_active, totp_secret, failed_attempts, locked_until, last_login_at, created_at, updated_at)`
  - 테이블 `public.admin_sessions(id, admin_user_id, token_hash, expires_at, revoked_at, created_at)`
  - 테이블 `public.admin_audit_log(id, admin_user_id, action, target, detail, created_at)`
  - `public.admin_verify_password(p_username text, p_password text) → table(admin_user_id uuid, display_name text, outcome text)` — `outcome ∈ {'ok','invalid','locked'}`
  - `public.admin_set_password(p_username text, p_password text, p_display_name text) → uuid`
  - 두 함수 모두 `security definer`, `anon`/`authenticated`/`public` 에서 실행 권한 회수됨. 호출자는 service_role 뿐.

- [ ] **Step 1: anon 노출 검사 스크립트를 쓴다**

`scripts/verify_admin_tables_rls.py`:

```python
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
```

- [ ] **Step 2: 적용 전 상태를 확인한다 (실패를 먼저 본다)**

```bash
export SUPABASE_URL="$(gh variable get NEXT_PUBLIC_SUPABASE_URL)"
export SUPABASE_ANON_KEY="$(gh variable get NEXT_PUBLIC_SUPABASE_ANON_KEY)"
python scripts/verify_admin_tables_rls.py; echo "종료코드: $?"
```

Expected: 세 줄 모두 `HTTP 404` + `결과: 테이블 없음` + 종료코드 2

- [ ] **Step 3: 마이그레이션을 쓴다**

`supabase/migrations/0038_admin_console_auth.sql`:

```sql
-- 관리자 자격·세션·감사 추적. 학부모 인증(Supabase Auth)과 분리된 별도 체계다.
--
-- 왜 profiles.role 을 되살리지 않는가:
--   0001_initial_schema.sql:138-141 의 "profiles update own" 정책은 행 단위라
--   role 컬럼까지 갱신을 허용한다. /home 개발 진입로가 프로덕션에서 켜져 있으므로
--   (사업 A 결정) 누구나 세션을 얻어 anon 키로 PATCH /rest/v1/profiles {"role":"admin"}
--   을 던져 스스로 관리자가 될 수 있다. 자격 저장소 자체를 분리한다.
--
-- 세 테이블 모두 RLS 활성 + 정책 0개 = anon/authenticated 전면 차단.
-- 선례: 0013_school_crawl_state.sql:72, 0036_app_jobs_rls.sql
-- 접근 경로는 service_role(Next.js 관리자 라우트)뿐이고, service_role 은 RLS 를 우회한다.
--
-- 비밀번호 해시에 새 의존성이 없다 — pgcrypto 는 0001_initial_schema.sql:1 이 이미 켰다.

create table if not exists public.admin_users (
  id uuid primary key default gen_random_uuid(),
  username text not null unique,
  password_hash text not null,
  display_name text,
  is_active boolean not null default true,
  -- 2단계 인증은 1단계에서 하지 않는다. 컬럼 자리만 남긴다 — 필요해지면
  -- 마이그레이션 없이 검증 코드만 붙일 수 있다.
  totp_secret text,
  failed_attempts integer not null default 0,
  locked_until timestamptz,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.admin_sessions (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid not null references public.admin_users(id) on delete cascade,
  -- 원본 토큰은 쿠키에만 있다. DB 에는 sha256 해시만 둔다.
  token_hash text not null unique,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists admin_sessions_expires_idx
  on public.admin_sessions (expires_at);

create table if not exists public.admin_audit_log (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid references public.admin_users(id) on delete set null,
  action text not null,
  target text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists admin_audit_log_created_idx
  on public.admin_audit_log (created_at desc);

alter table public.admin_users     enable row level security;
alter table public.admin_sessions  enable row level security;
alter table public.admin_audit_log enable row level security;

-- 자격 검증은 security definer 함수 하나로 감싼다. 앱은 «맞다/틀리다» 와 계정 id 만 받는다.
-- 실패 카운터와 잠금도 여기서 갱신한다 — 앱이 잊어버릴 여지를 없앤다.
-- search_path 에 extensions 를 넣는 이유: Supabase 는 pgcrypto 를 extensions 스키마에
-- 두는 경우가 있어 crypt/gen_salt 를 무자격 이름으로 못 찾을 수 있다.
create or replace function public.admin_verify_password(
  p_username text,
  p_password text
)
returns table (admin_user_id uuid, display_name text, outcome text)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_user public.admin_users%rowtype;
  v_next_attempts integer;
begin
  select * into v_user from public.admin_users where username = p_username;

  if not found or not v_user.is_active then
    return query select null::uuid, null::text, 'invalid'::text;
    return;
  end if;

  if v_user.locked_until is not null and v_user.locked_until > now() then
    return query select null::uuid, null::text, 'locked'::text;
    return;
  end if;

  if v_user.password_hash = crypt(p_password, v_user.password_hash) then
    update public.admin_users
       set failed_attempts = 0,
           locked_until = null,
           last_login_at = now(),
           updated_at = now()
     where id = v_user.id;
    return query select v_user.id, v_user.display_name, 'ok'::text;
    return;
  end if;

  -- 5회 실패 → 15분 잠금.
  v_next_attempts := v_user.failed_attempts + 1;
  update public.admin_users
     set failed_attempts = v_next_attempts,
         locked_until = case
           when v_next_attempts >= 5 then now() + interval '15 minutes'
           else v_user.locked_until
         end,
         updated_at = now()
   where id = v_user.id;

  return query select null::uuid, null::text, 'invalid'::text;
end;
$$;

-- 계정 생성·비밀번호 회전. 원본은 이 함수 안에서만 존재하고 해시만 남는다.
create or replace function public.admin_set_password(
  p_username text,
  p_password text,
  p_display_name text default null
)
returns uuid
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_id uuid;
begin
  insert into public.admin_users (username, password_hash, display_name)
  values (p_username, crypt(p_password, gen_salt('bf', 12)), p_display_name)
  on conflict (username) do update
     set password_hash = crypt(p_password, gen_salt('bf', 12)),
         display_name = coalesce(excluded.display_name, public.admin_users.display_name),
         failed_attempts = 0,
         locked_until = null,
         is_active = true,
         updated_at = now()
  returning id into v_id;
  return v_id;
end;
$$;

-- security definer 함수는 기본적으로 public 에 EXECUTE 가 있다. 회수하지 않으면
-- anon 키로 자격 검증기와 비밀번호 설정기가 그대로 공개된다.
revoke all on function public.admin_verify_password(text, text) from public;
revoke all on function public.admin_verify_password(text, text) from anon;
revoke all on function public.admin_verify_password(text, text) from authenticated;
revoke all on function public.admin_set_password(text, text, text) from public;
revoke all on function public.admin_set_password(text, text, text) from anon;
revoke all on function public.admin_set_password(text, text, text) from authenticated;
```

- [ ] **Step 4: 번호 검사를 통과하는지 확인한다**

```bash
python scripts/check_migration_numbers.py
```

Expected: `마이그레이션 N개, 번호 중복 없음` + 종료코드 0. N 은 이 시점에 머지된 형제 사업 마이그레이션 수에 따라 달라진다 — 사업 A 만 섰다면 **39**, 사업 E 가 먼저 섰다면 **41** 이다. 중요한 것은 개수가 아니라 **`번호 중복` 이 한 줄도 없는 것**이다. `번호 중복 0038` 이 나오면 다른 사업이 그 번호를 가져간 것이니 **중단하고 보고할 것** (사업 E 계획서 `:15` 는 `0038` 을 이 사업 몫으로 비워 두었다).

- [ ] **Step 5: 커밋**

```bash
git add supabase/migrations/0038_admin_console_auth.sql scripts/verify_admin_tables_rls.py
git commit -m "feat(admin): 관리자 자격·세션·감사 테이블과 검증 RPC 추가

관리자 자격을 학부모 인증(Supabase Auth)과 분리된 별도 저장소에 둔다.
/home 개발 진입로가 프로덕션에서 켜져 있어 «로그인한 사용자인가» 는 관리자
판정에 아무 정보도 주지 못하기 때문이다.

profiles.role 은 복원하지 않는다 — 0001:138-141 의 \"profiles update own\" 이
행 단위라 role 컬럼까지 열려 있고, anon 키 PATCH 로 자기 승격이 된다.

세 테이블 모두 RLS 활성 + 정책 0개(0013:72, 0036 선례)라 anon 키로는
존재조차 확인할 수 없다. 비밀번호는 pgcrypto crypt/gen_salt 로 DB 안에서만
다루고, security definer 함수의 EXECUTE 를 public/anon/authenticated 에서 회수한다.

적용은 머지 시 db-migrate 워크플로가 수행한다."
```

- [ ] **Step 6: 머지 후 적용됐는지 확인한다**

`main` 에 머지되어 `db-migrate` 워크플로가 `0038` 을 적용한 뒤:

```bash
supabase migration list | tail -8
python scripts/verify_admin_tables_rls.py; echo "종료코드: $?"
```

Expected: `migration list` 의 Local/Remote 가 `0038` 행에서 일치. 검사 스크립트가 세 테이블 모두 `전체 0` 또는 4xx + `rpc:verify … 차단됨` + `결과: 차단됨` + 종료코드 0

- [ ] **Step 7: service_role 로는 보이는지 확인한다 (테이블이 «없어서» 차단된 게 아님을 증명)**

```bash
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
for t in ['admin_users','admin_sessions','admin_audit_log']:
    r=urllib.request.Request(f'{u}/rest/v1/{t}?select=id&limit=1')
    r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k); r.add_header('Prefer','count=exact')
    x=urllib.request.urlopen(r,timeout=60)
    print(t, x.status, x.headers.get('Content-Range'))
"
```

Expected: 세 줄 모두 `200` + `*/0` (테이블은 존재하고 비어 있다). `404` 가 나오면 마이그레이션이 적용되지 않은 것이다.

---

## Task 2: 관리자 계정 프로비저닝

**이 Task 는 커밋 산출물이 없다.** 계정은 DB 에, 비밀번호는 GCP Secret Manager 에 생긴다. 프로비저닝 스크립트는 **저장소 밖에서 일회성으로** 돌리고 지운다 — 저장소에 두면 «관리자 계정을 만드는 도구» 가 코드 리뷰·CI·아티팩트를 타고 다니게 되고, 회전은 어차피 같은 절차를 다시 밟는 일이라 상시 도구가 필요 없다.

**비밀번호는 사람이 고르지 않는다.** 32자 무작위를 만들어 Secret Manager 에 넣고, DB 에는 해시만 남긴다. 화면·stdout·git·명령줄 인자 어디에도 원본이 나오지 않는다.

**Files:**
- 없음 (저장소 변경 없음)
- 임시: `$SCRATCH/provision_admin_user.py` — 실행 후 삭제

**Interfaces:**
- Consumes: Task 1 이 만든 `admin_set_password` / `admin_verify_password` RPC
- Produces:
  - `admin_users` 에 `username='naranhi'` 행 1개
  - GCP Secret Manager 시크릿 `admin-console-password` (Task 5 의 사람 로그인에 쓴다. 애플리케이션은 이 값을 읽지 않는다)

- [ ] **Step 1: 스크립트를 저장소 밖에 쓴다**

```bash
SCRATCH="$(mktemp -d)"
cat > "$SCRATCH/provision_admin_user.py" <<'PY'
"""관리자 계정 1개를 만든다. 일회성 — 저장소에 커밋하지 않는다.

비밀번호를 무작위로 만들어 GCP Secret Manager 에 먼저 넣고, 그 다음 DB 에
pgcrypto 해시를 남긴다. 순서가 중요하다 — 반대로 하면 Secret 저장이 실패했을 때
'DB 에 해시는 있는데 원본을 아무도 모르는' 계정이 남는다.

값은 stdout·로그·명령줄 인자 어디에도 나오지 않는다. 길이만 찍는다.
"""
import json
import os
import secrets
import string
import subprocess
import sys
import tempfile
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
USERNAME = "naranhi"
DISPLAY_NAME = "운영자"
SECRET_NAME = "admin-console-password"

ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
password = "".join(secrets.choice(ALPHABET) for _ in range(32))
print(f"비밀번호 생성: {len(password)}자")

# 1) Secret Manager 먼저. 값은 임시 파일 경유 — 명령줄 인자에 넣지 않는다.
handle = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt")
handle.write(password)
handle.close()
try:
    exists = subprocess.run(
        ["gcloud", "secrets", "describe", SECRET_NAME],
        capture_output=True,
    ).returncode == 0
    verb = ["versions", "add", SECRET_NAME] if exists else ["create", SECRET_NAME]
    subprocess.run(
        ["gcloud", "secrets", *verb, f"--data-file={handle.name}"],
        check=True,
    )
finally:
    os.remove(handle.name)
print(f"Secret Manager 저장 완료: {SECRET_NAME} ({'새 버전' if exists else '신규 생성'})")

# 2) DB. 원본은 요청 본문으로만 가고 응답에는 id 만 온다.
request = urllib.request.Request(
    f"{URL}/rest/v1/rpc/admin_set_password",
    method="POST",
    data=json.dumps(
        {"p_username": USERNAME, "p_password": password, "p_display_name": DISPLAY_NAME}
    ).encode(),
)
request.add_header("apikey", KEY)
request.add_header("Authorization", "Bearer " + KEY)
request.add_header("Content-Type", "application/json")
with urllib.request.urlopen(request, timeout=60) as response:
    admin_id = json.loads(response.read().decode())

print(f"관리자 계정 생성 완료: username={USERNAME} id={admin_id}")
print("원본 비밀번호는 이 프로세스와 함께 사라진다. 필요하면 Secret Manager 에서 읽는다.")
PY
echo "작성됨: $SCRATCH/provision_admin_user.py"
```

- [ ] **Step 2: 실행한다**

```bash
export SUPABASE_URL="$(gh variable get NEXT_PUBLIC_SUPABASE_URL)"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python "$SCRATCH/provision_admin_user.py"
```

Expected:
```
비밀번호 생성: 32자
Created version [1] of the secret [admin-console-password].
Secret Manager 저장 완료: admin-console-password (신규 생성)
관리자 계정 생성 완료: username=naranhi id=<uuid>
```

- [ ] **Step 3: 스크립트를 지운다**

```bash
rm -rf "$SCRATCH"
git status --short
```

Expected: `git status` 출력에 새 파일이 **없다.** 프로비저닝 흔적이 저장소에 남지 않았음을 확인한다.

- [ ] **Step 4: 저장된 자격으로 검증이 통과하는지 확인한다**

```bash
PWFILE="$(mktemp)"
gcloud secrets versions access latest --secret=admin-console-password > "$PWFILE"
python -c "
import json,os,sys,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
pw=open(sys.argv[1],encoding='utf-8').read()
r=urllib.request.Request(u+'/rest/v1/rpc/admin_verify_password', method='POST',
    data=json.dumps({'p_username':'naranhi','p_password':pw}).encode())
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k); r.add_header('Content-Type','application/json')
rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
row=rows[0] if rows else {}
print('outcome =', row.get('outcome'), '| id 있음 =', bool(row.get('admin_user_id')))
" "$PWFILE"
rm -f "$PWFILE"
```

Expected: `outcome = ok | id 있음 = True`

- [ ] **Step 5: 틀린 비밀번호가 거부되는지 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
def rpc(user,pw):
    r=urllib.request.Request(u+'/rest/v1/rpc/admin_verify_password', method='POST',
        data=json.dumps({'p_username':user,'p_password':pw}).encode())
    r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k); r.add_header('Content-Type','application/json')
    rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
    return (rows[0] if rows else {}).get('outcome')
print('없는 계정 :', rpc('nobody','x'))
print('오답 1회  :', rpc('naranhi','wrong-password'))
"
```

Expected: 둘 다 `invalid`. **응답이 구별되지 않아야 한다** (스펙 §12.1 #13).

- [ ] **Step 6: 5회 실패 잠금이 동작하는지 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
def rpc(pw):
    r=urllib.request.Request(u+'/rest/v1/rpc/admin_verify_password', method='POST',
        data=json.dumps({'p_username':'naranhi','p_password':pw}).encode())
    r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k); r.add_header('Content-Type','application/json')
    rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
    return (rows[0] if rows else {}).get('outcome')
for i in range(1,6):
    print(f'오답 {i}회:', rpc('wrong-password'))
print('6회째(정답이어도):', rpc('wrong-password'))
"
```

Expected: 1~4회 `invalid`, 5회째 `invalid`, 6회째 **`locked`**. 앞선 Step 4 에서 이미 1회 성공했으므로 카운터는 0에서 시작한다.

- [ ] **Step 7: 잠금을 푼다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/admin_users?username=eq.naranhi', method='PATCH',
    data=json.dumps({'failed_attempts':0,'locked_until':None}).encode())
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
r.add_header('Content-Type','application/json'); r.add_header('Prefer','return=minimal')
print('HTTP', urllib.request.urlopen(r,timeout=60).status)
"
```

Expected: `HTTP 204`. 15분을 기다리지 않고 카운터만 되돌린다 — 잠금 자체는 Step 6 에서 이미 검증됐다.

---

## Task 3: 프론트 데이터 접근 기반

관리자 화면이 읽어야 할 테이블 중 **`app_jobs` 가 `types/database.ts` 에 아예 없다.** `createSupabaseServiceClient()` 는 `createClient<Database>` 이므로 `.from('app_jobs')` 가 타입 오류다. `school_crawl_state` 는 있지만 `0033` 이 추가한 `board_watermarks` 가 타입에도 `lib/school-crawl-state.ts` 의 select 문자열에도 빠져 있어 **프론트가 watermark 를 아예 못 본다.**

그리고 `lib/supabase/server.ts` 에는 `import 'server-only'` 가 없다 — `lib/school-crawl-state.ts:1`, `lib/school-crawler-trigger.ts:1` 은 선언하는데 정작 service_role 팩토리를 가진 파일이 빠져 있다. 이 사업이 그 함수를 관리자 경로 전반에서 쓰므로 여기서 한 줄 추가한다(범위 최소 예외).

**Files:**
- Modify: `lib/supabase/server.ts` (1행 추가)
- Modify: `types/database.ts` (`school_crawl_state` 에 `board_watermarks`, 신규 테이블 4개, 신규 Functions 2개)
- Modify: `lib/school-crawl-state.ts` (`board_watermarks` 를 행 타입·select 2곳·매핑에 추가)

**Interfaces:**
- Consumes: Task 1 이 만든 테이블·함수 시그니처
- Produces:
  - `Database['public']['Tables']['app_jobs' | 'admin_users' | 'admin_sessions' | 'admin_audit_log']`
  - `Database['public']['Functions']['admin_verify_password' | 'admin_set_password']`
  - `SchoolCrawlerStateDetails.board_watermarks: Json`
  - `AppJobStatus = 'queued' | 'processing' | 'completed' | 'failed'`

- [ ] **Step 1: 지금 타입이 없어서 깨지는 것을 확인한다 (실패를 먼저 본다)**

```bash
cat > /tmp/probe_app_jobs.ts <<'TS'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
export async function probe() {
  const service = createSupabaseServiceClient()
  const { data } = await service.from('app_jobs').select('id,status').limit(1)
  return data
}
TS
cp /tmp/probe_app_jobs.ts lib/_probe_app_jobs.ts
npm run typecheck; echo "종료코드: $?"
rm lib/_probe_app_jobs.ts
```

Expected: `lib/_probe_app_jobs.ts` 에서 `Argument of type '"app_jobs"' is not assignable` 계열 오류 + 종료코드 1. 이것이 «관리자 화면을 지금 코드 위에 못 올린다» 의 구체적 형태다.

- [ ] **Step 2: `server-only` 한 줄을 추가한다**

`lib/supabase/server.ts` 의 1행 위에 추가:

```typescript
import 'server-only'
```

결과적으로 파일 상단은 이렇게 된다:

```typescript
import 'server-only'

import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { createClient } from "@supabase/supabase-js";
import type { Database } from "@/types/database";
```

- [ ] **Step 3: `school_crawl_state` 타입에 `board_watermarks` 를 넣는다**

`types/database.ts` 의 `school_crawl_state` 블록에서 `Row` / `Insert` / `Update` 각각에 한 줄씩 추가한다. `crawl_last_checked_at` 다음 자리다:

```typescript
          crawl_last_checked_at: string | null
          board_watermarks: Json
          created_at: string
```

```typescript
          crawl_last_checked_at?: string | null
          board_watermarks?: Json
          created_at?: string
```

```typescript
          crawl_last_checked_at?: string | null
          board_watermarks?: Json
          updated_at?: string
```

- [ ] **Step 4: 신규 테이블 4개를 `Tables` 에 넣는다**

`types/database.ts` 의 `SchoolCrawlBoardKind` 선언 아래에 상태 타입을 추가한다:

```typescript
export type AppJobStatus = 'queued' | 'processing' | 'completed' | 'failed'
```

그리고 `Tables` 블록 끝(`claim_notice_extractions` 앞의 마지막 테이블 뒤)에 추가한다:

```typescript
      app_jobs: {
        Row: {
          id: string
          job_type: string
          job_key: string
          payload: Json
          status: AppJobStatus
          attempts: number
          max_attempts: number
          available_at: string
          started_at: string | null
          finished_at: string | null
          result: Json | null
          last_error: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          job_type: string
          job_key: string
          payload?: Json
          status?: AppJobStatus
          attempts?: number
          max_attempts?: number
          available_at?: string
          started_at?: string | null
          finished_at?: string | null
          result?: Json | null
          last_error?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          status?: AppJobStatus
          attempts?: number
          max_attempts?: number
          available_at?: string
          started_at?: string | null
          finished_at?: string | null
          result?: Json | null
          last_error?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      admin_users: {
        Row: {
          id: string
          username: string
          password_hash: string
          display_name: string | null
          is_active: boolean
          totp_secret: string | null
          failed_attempts: number
          locked_until: string | null
          last_login_at: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          username: string
          password_hash: string
          display_name?: string | null
          is_active?: boolean
          totp_secret?: string | null
          failed_attempts?: number
          locked_until?: string | null
          last_login_at?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          display_name?: string | null
          is_active?: boolean
          failed_attempts?: number
          locked_until?: string | null
          last_login_at?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      admin_sessions: {
        Row: {
          id: string
          admin_user_id: string
          token_hash: string
          expires_at: string
          revoked_at: string | null
          created_at: string
        }
        Insert: {
          id?: string
          admin_user_id: string
          token_hash: string
          expires_at: string
          revoked_at?: string | null
          created_at?: string
        }
        Update: {
          revoked_at?: string | null
        }
        Relationships: []
      }
      admin_audit_log: {
        Row: {
          id: string
          admin_user_id: string | null
          action: string
          target: string | null
          detail: Json
          created_at: string
        }
        Insert: {
          id?: string
          admin_user_id?: string | null
          action: string
          target?: string | null
          detail?: Json
          created_at?: string
        }
        Update: {
          detail?: Json
        }
        Relationships: []
      }
```

- [ ] **Step 5: 신규 RPC 2개를 `Functions` 에 넣는다**

`types/database.ts` 의 `Functions` 블록에서 `claim_notice_extractions` 뒤에 추가:

```typescript
      admin_verify_password: {
        Args: {
          p_username: string
          p_password: string
        }
        Returns: {
          admin_user_id: string | null
          display_name: string | null
          outcome: 'ok' | 'invalid' | 'locked'
        }[]
      }
      admin_set_password: {
        Args: {
          p_username: string
          p_password: string
          p_display_name?: string | null
        }
        Returns: string
      }
```

- [ ] **Step 6: `lib/school-crawl-state.ts` 의 select 를 늘린다**

행 타입에 한 줄:

```typescript
interface SchoolCrawlerStateRow {
  school_id: string
  crawl_board_url: string | null
  crawl_board_kind: SchoolCrawlBoardKind
  crawl_status: string
  crawl_error_message: string | null
  crawl_result: Json
  crawl_last_checked_at: string | null
  board_watermarks: Json
  created_at: string
  updated_at: string
}
```

외부 타입에도 한 줄:

```typescript
export interface SchoolCrawlerStateDetails extends SchoolCrawlerState {
  crawl_board_kind: SchoolCrawlBoardKind
  crawl_error_message: string | null
  crawl_result: Json
  board_watermarks: Json
}
```

매핑에도 한 줄 (`mapStateRow` 의 반환 객체):

```typescript
    crawl_result: row.crawl_result,
    board_watermarks: row.board_watermarks ?? {},
  }
```

그리고 **select 문자열 두 곳**(`getSchoolCrawlerState` 안 1곳, `ensureSchoolCrawlerState` 안 1곳)을 동일하게 교체한다:

```typescript
      'school_id,crawl_board_url,crawl_board_kind,crawl_status,crawl_error_message,crawl_result,crawl_last_checked_at,board_watermarks,created_at,updated_at',
```

- [ ] **Step 7: 타입체크·빌드가 통과하는지 확인한다**

```bash
npm run typecheck && npm run build
```

Expected: 둘 다 성공

- [ ] **Step 8: select 문자열이 실제로 둘 다 늘었는지 확인한다**

```bash
grep -c "board_watermarks" lib/school-crawl-state.ts
grep -n "board_watermarks" types/database.ts | head
```

Expected: `lib/school-crawl-state.ts` 에서 **5** (행 타입 1 + 외부 타입 1 + 매핑 1 + select 2), `types/database.ts` 에 3줄(Row/Insert/Update)

- [ ] **Step 9: 실제 데이터에 값이 실려 오는지 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/school_crawl_state?select=school_id,crawl_board_kind,board_watermarks&limit=8')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
for row in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()):
    wm=row.get('board_watermarks') or {}
    print(row['school_id'][:8], row['crawl_board_kind'], f'watermark 게시판 {len(wm)}개')
"
```

Expected: 학교 8행. `crawl_board_kind` 가 `family_notice` / `announcement_fallback` / `unknown` 중 하나. watermark 개수가 0 이상. 이 값들이 Task 11 화면의 원본이다.

- [ ] **Step 10: 커밋**

```bash
git add lib/supabase/server.ts lib/school-crawl-state.ts types/database.ts
git commit -m "fix(admin): 관리자 화면이 읽을 테이블 타입 보강 + server-only 선언

app_jobs 가 types/database.ts 에 아예 없어서 createSupabaseServiceClient()
로는 .from('app_jobs') 가 타입 오류였다. 관리자 자격 테이블 3개와 함께 넣는다.

school_crawl_state.board_watermarks(0033 추가분)가 타입에도 lib 의 select
문자열 2곳에도 빠져 있어 프론트가 watermark 를 아예 못 봤다. 셋 다 채운다.

lib/supabase/server.ts 에 import 'server-only' 를 추가한다. service_role
팩토리를 가진 파일인데 school-crawl-state.ts:1 과 달리 선언이 없었다."
```

---

## Task 4: 관리자 세션 라이브러리

세션 검증을 **한 파일**에 모은다. 나중에 관리자 콘솔을 별도 도메인으로 뗄 때 바뀌는 것은 이 파일의 쿠키 설정뿐이어야 한다.

쿠키 상수는 **별도 파일**(`lib/admin/cookie.ts`)에 둔다. `middleware.ts` 가 Edge 런타임에서 이 상수를 import 하는데, `session.ts` 는 `server-only` · `node:crypto` · `@supabase/supabase-js` 를 끌고 오므로 middleware 번들에 들어가면 안 되기 때문이다.

**Files:**
- Create: `lib/admin/cookie.ts`
- Create: `lib/admin/session.ts`

**Interfaces:**
- Consumes: Task 1 의 `admin_verify_password` RPC, `admin_sessions`/`admin_audit_log` 테이블, Task 3 의 타입
- Produces:
  - `ADMIN_COOKIE_NAME = '__Host-naranhi_admin'`, `ADMIN_SESSION_MAX_AGE_SECONDS = 28800` (`lib/admin/cookie.ts`, import 0개)
  - `verifyAdminPassword(username: string, password: string): Promise<VerifyOutcome>` — `{status:'ok', adminUserId, displayName} | {status:'invalid'} | {status:'locked'}`
  - `createAdminSession(adminUserId: string): Promise<{ token: string; expiresAt: string }>`
  - `getAdminSession(): Promise<AdminSession | null>` — `AdminSession = { adminUserId, username, displayName, expiresAt }`
  - `requireAdminSession(): Promise<AdminSession>` — 없으면 `AdminUnauthorizedError`
  - `revokeCurrentAdminSession(): Promise<void>`
  - `writeAdminAudit(session: AdminSession, action: string, target: string | null, detail?: Record<string, unknown>): Promise<void>`

- [ ] **Step 1: 쿠키 상수 파일을 쓴다**

`lib/admin/cookie.ts`:

```typescript
/** 관리자 세션 쿠키 상수.
 *
 *  middleware(Edge 런타임)와 서버 라우트가 함께 쓴다. 그래서 이 파일에는
 *  import 를 하나도 두지 않는다 — session.ts 를 middleware 에서 import 하면
 *  server-only / node:crypto / supabase-js 가 Edge 번들로 끌려 들어간다.
 *
 *  __Host- 접두는 Secure + Domain 없음 + Path=/ 를 강제한다. 설계 스펙 §3.5 는
 *  Path=/admin 과 __Host- 를 함께 적었지만 둘은 배타적이다. 쿠키가 HttpOnly 라
 *  경로 격리가 주는 이득이 없는 반면, __Host- 는 형제 호스트가 이 쿠키를
 *  덮어쓰지 못하게 한다 — 그래서 __Host- 를 택했다.
 */
export const ADMIN_COOKIE_NAME = '__Host-naranhi_admin'

/** 8시간 절대 만료. 슬라이딩 갱신을 붙이지 않는다 —
 *  «훔친 쿠키의 최대 수명 = 8시간» 이 보장되어야 한다.
 *  학부모 세션(14일, 사업 A Task 5)과 의도적으로 반대다. */
export const ADMIN_SESSION_MAX_AGE_SECONDS = 60 * 60 * 8
```

- [ ] **Step 2: 세션 라이브러리를 쓴다**

`lib/admin/session.ts`:

```typescript
import 'server-only'

import { createHash, randomBytes } from 'node:crypto'
import { cookies } from 'next/headers'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { ADMIN_COOKIE_NAME, ADMIN_SESSION_MAX_AGE_SECONDS } from '@/lib/admin/cookie'

export { ADMIN_COOKIE_NAME, ADMIN_SESSION_MAX_AGE_SECONDS }

export interface AdminSession {
  adminUserId: string
  username: string
  displayName: string | null
  expiresAt: string
}

export type VerifyOutcome =
  | { status: 'ok'; adminUserId: string; displayName: string | null }
  | { status: 'invalid' }
  | { status: 'locked' }

export class AdminUnauthorizedError extends Error {
  constructor() {
    super('admin_unauthorized')
    this.name = 'AdminUnauthorizedError'
  }
}

/** 쿠키에는 원본 토큰이, DB 에는 이 해시가 들어간다.
 *  DB 가 유출돼도 세션을 재현할 수 없고, 서버는 해시로 즉시 조회할 수 있다. */
function hashToken(token: string): string {
  return createHash('sha256').update(token).digest('hex')
}

/** 자격 검증. 실패 카운터·잠금은 DB 함수가 갱신한다(0038).
 *  앱은 «맞다/틀리다/잠김» 과 계정 id 만 받는다 — 해시가 앱 메모리로 나오지 않는다. */
export async function verifyAdminPassword(
  username: string,
  password: string,
): Promise<VerifyOutcome> {
  const service = createSupabaseServiceClient()
  const { data, error } = await service.rpc('admin_verify_password', {
    p_username: username,
    p_password: password,
  })
  if (error) {
    throw new Error(`관리자 자격 검증 실패: ${error.message}`)
  }
  const row = Array.isArray(data) ? data[0] : null
  if (!row) return { status: 'invalid' }
  if (row.outcome === 'locked') return { status: 'locked' }
  if (row.outcome !== 'ok' || !row.admin_user_id) return { status: 'invalid' }
  return {
    status: 'ok',
    adminUserId: row.admin_user_id,
    displayName: row.display_name ?? null,
  }
}

export async function createAdminSession(
  adminUserId: string,
): Promise<{ token: string; expiresAt: string }> {
  const token = randomBytes(32).toString('base64url')
  const expiresAt = new Date(Date.now() + ADMIN_SESSION_MAX_AGE_SECONDS * 1000).toISOString()
  const service = createSupabaseServiceClient()
  const { error } = await service.from('admin_sessions').insert({
    admin_user_id: adminUserId,
    token_hash: hashToken(token),
    expires_at: expiresAt,
  })
  if (error) {
    throw new Error(`관리자 세션 생성 실패: ${error.message}`)
  }
  return { token, expiresAt }
}

/** 세션 검증. 이 함수만이 «관리자인가» 의 답을 안다.
 *  middleware 는 쿠키 존재만 보므로(Edge 런타임 제약), 실제 판정은 전부 여기를 지난다. */
export async function getAdminSession(): Promise<AdminSession | null> {
  const cookieStore = await cookies()
  const token = cookieStore.get(ADMIN_COOKIE_NAME)?.value
  if (!token) return null

  const service = createSupabaseServiceClient()
  const { data: session, error } = await service
    .from('admin_sessions')
    .select('admin_user_id,expires_at,revoked_at')
    .eq('token_hash', hashToken(token))
    .maybeSingle()
  if (error || !session) return null
  if (session.revoked_at) return null
  if (new Date(session.expires_at).getTime() <= Date.now()) return null

  const { data: user } = await service
    .from('admin_users')
    .select('username,display_name,is_active')
    .eq('id', session.admin_user_id)
    .maybeSingle()
  if (!user || !user.is_active) return null

  return {
    adminUserId: session.admin_user_id,
    username: user.username,
    displayName: user.display_name,
    expiresAt: session.expires_at,
  }
}

export async function requireAdminSession(): Promise<AdminSession> {
  const session = await getAdminSession()
  if (!session) throw new AdminUnauthorizedError()
  return session
}

/** 로그아웃. JWT 가 아니라 DB 세션이라 서버 측에서 즉시 회수된다. */
export async function revokeCurrentAdminSession(): Promise<void> {
  const cookieStore = await cookies()
  const token = cookieStore.get(ADMIN_COOKIE_NAME)?.value
  if (!token) return
  const service = createSupabaseServiceClient()
  await service
    .from('admin_sessions')
    .update({ revoked_at: new Date().toISOString() })
    .eq('token_hash', hashToken(token))
    .is('revoked_at', null)
}

/** 파괴적 작업의 사람별 추적. 실패해도 조작을 되돌리지 않는다 —
 *  감사 기록 실패로 «이미 지운 공지» 를 되살릴 수는 없기 때문이다. 대신 크게 남긴다. */
export async function writeAdminAudit(
  session: AdminSession,
  action: string,
  target: string | null,
  detail: Record<string, unknown> = {},
): Promise<void> {
  const service = createSupabaseServiceClient()
  const { error } = await service.from('admin_audit_log').insert({
    admin_user_id: session.adminUserId,
    action,
    target,
    detail: detail as never,
  })
  if (error) {
    console.error(
      `관리자 감사 로그 기록 실패: action=${action} target=${target ?? '-'} error=${error.message}`,
    )
  }
}
```

- [ ] **Step 3: 타입체크가 통과하는지 확인한다**

```bash
npm run typecheck
```

Expected: 성공. 실패하면 Task 3 Step 4~5 의 타입 추가가 빠진 것이다.

- [ ] **Step 4: 쿠키 상수 파일에 import 가 없는지 확인한다**

```bash
grep -c "^import\|require(" lib/admin/cookie.ts
```

Expected: `0`. 하나라도 있으면 middleware 번들이 오염된다.

- [ ] **Step 5: 커밋**

```bash
git add lib/admin/cookie.ts lib/admin/session.ts
git commit -m "feat(admin): 관리자 세션 발급·검증·감사 로그 라이브러리

세션 검증을 한 파일에 모은다. 나중에 콘솔을 별도 도메인으로 뗄 때
바뀌는 것이 이 파일의 쿠키 설정뿐이 되도록.

쿠키 상수만 lib/admin/cookie.ts 로 분리한다. middleware 가 Edge 런타임에서
이 상수를 쓰는데, session.ts 를 import 하면 server-only·node:crypto·supabase-js
가 Edge 번들로 끌려 들어간다.

토큰 원본은 쿠키에만 두고 DB 에는 sha256 해시만 넣는다 — DB 가 유출돼도
세션을 재현할 수 없다. 8시간 절대 만료, 슬라이딩 갱신 없음.

쿠키 접두는 __Host- 로 간다. 스펙 §3.5 는 Path=/admin 과 __Host- 를 함께
적었지만 __Host- 는 Path=/ 를 강제해 둘이 배타적이다. HttpOnly 라 경로 격리
이득이 없는 반면 __Host- 는 형제 호스트의 쿠키 덮어쓰기를 막는다."
```

---

## Task 5: middleware 관리자 게이트 + 로그인

스펙 §3.2 의 요구를 그대로 구현한다 — **관리자 판정을 middleware 함수의 가장 앞에**, 그리고 **레이아웃·핸들러에서 다시 한 번.** 사업 A 가 `TEST_ENTRY_BYPASS` 와 `ui_preview` 분기를 지웠지만, middleware 하나에만 의존하지 않는다. `middleware.ts:70` 의 matcher 는 `.*\..*` 를 제외하므로 **점이 들어간 경로는 middleware 를 아예 타지 않는다.**

`PUBLIC_PATHS` 에 관리자 경로를 **넣지 않는다.** `/admin/login` 예외는 `adminGate` 안에서만 처리한다 — 공개 목록에 올리면 학부모 흐름의 `startsWith` 매칭(`middleware.ts:58`)과 섞인다.

**Files:**
- Modify: `middleware.ts`
- Create: `app/(admin)/layout.tsx`
- Create: `app/(admin)/admin/login/page.tsx`
- Create: `app/(admin)/admin/login/AdminLoginForm.tsx`
- Create: `app/(admin)/admin/(protected)/layout.tsx`
- Create: `app/(admin)/admin/(protected)/page.tsx`
- Create: `app/api/admin/login/route.ts`
- Create: `app/api/admin/logout/route.ts`

**Interfaces:**
- Consumes: Task 4 의 `ADMIN_COOKIE_NAME`, `verifyAdminPassword`, `createAdminSession`, `requireAdminSession`, `revokeCurrentAdminSession`, `writeAdminAudit`
- Produces:
  - `GET /admin/*` → 관리자 쿠키 없으면 `/admin/login` 리다이렉트
  - `GET|POST /api/admin/*` → 관리자 쿠키 없으면 **JSON 401** (HTML 리다이렉트 아님)
  - `POST /api/admin/login {username, password}` → 성공 `{ok:true, next:'/admin'}` + `Set-Cookie`, 실패 401 `{ok:false, error:'invalid_credentials'}` (고정 응답 시간)
  - `POST /api/admin/logout` → `{ok:true}` + 쿠키 삭제
  - 모든 관리자 페이지가 `app/(admin)/admin/(protected)/layout.tsx` 아래에 놓이면 자동으로 이중 방어를 받는다

- [ ] **Step 1: 지금은 `/admin` 이 아무 데도 없는 것을 확인한다 (실패를 먼저 본다)**

```bash
npm run dev &
sleep 8
curl -s -o /dev/null -w "GET /admin        → HTTP %{http_code} → %{redirect_url}\n" http://localhost:3000/admin
curl -s -o /dev/null -w "GET /api/admin/jobs → HTTP %{http_code}\n" http://localhost:3000/api/admin/jobs
```

Expected: 둘 다 `/login` 으로 리다이렉트(학부모 흐름) 또는 404. **관리자 게이트가 없다는 뜻이다.**

- [ ] **Step 2: middleware 맨 앞에 관리자 게이트를 넣는다**

`middleware.ts` 상단 import 에 한 줄 추가:

```typescript
import { ADMIN_COOKIE_NAME } from './lib/admin/cookie'
```

`PUBLIC_PATHS` 선언 아래에 게이트를 추가한다:

```typescript
/** 미인증으로 통과시키는 유일한 관리자 경로. PUBLIC_PATHS 에는 넣지 않는다 —
 *  학부모 흐름의 startsWith 매칭(:58)과 섞이면 실수가 생긴다. */
const ADMIN_LOGIN_PATHS = ['/admin/login', '/api/admin/login']

/** 관리자 1차 게이트. 여기서는 쿠키 «존재» 만 본다.
 *  middleware 는 Edge 런타임이라 service_role 도 node:crypto 도 쓸 수 없고,
 *  매 요청 DB 왕복도 부적절하다. 실제 세션 검증은 (protected)/layout.tsx 와
 *  app/api/admin/** 각 핸들러의 requireAdminSession() 이 다시 한다(이중 방어 ②).
 *
 *  중요한 성질: 학부모 세션 쿠키(sb-…)로도, 어떤 프리뷰 쿠키로도 여기를 통과할 수 없다.
 *  /home 이 열려 있어도 관리자 표면에 닿지 못한다는 보장이 이 한 줄에서 나온다. */
function adminGate(request: NextRequest): NextResponse {
  const pathname = request.nextUrl.pathname

  if (ADMIN_LOGIN_PATHS.includes(pathname)) {
    return NextResponse.next({ request })
  }

  if (request.cookies.get(ADMIN_COOKIE_NAME)?.value) {
    return NextResponse.next({ request })
  }

  if (pathname.startsWith('/api/admin')) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  return NextResponse.redirect(new URL('/admin/login', request.url))
}
```

그리고 `middleware` 함수의 **첫 문장 다음**, 학부모 흐름이 시작되기 전에 분기를 넣는다:

```typescript
export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname

  // ① 관리자 경로는 다른 어떤 분기보다 먼저 판정한다.
  //    이 아래는 전부 학부모 흐름이고, 학부모 흐름에 우회가 하나라도 생기면
  //    그 우회가 관리자 표면까지 닿게 된다. 순서가 곧 방어다.
  if (pathname.startsWith('/admin') || pathname.startsWith('/api/admin')) {
    return adminGate(request)
  }

  let response = NextResponse.next({ request })
  // ② 여기서부터 기존 학부모 흐름 (createServerClient, getUser, PUBLIC_PATHS …)
```

> matcher(`middleware.ts:70`)는 그대로 둔다. `/admin` 과 `/api/admin` 은 점이 없어 이미 걸린다.

- [ ] **Step 3: 관리자 셸과 로그인 화면을 만든다**

`app/(admin)/layout.tsx`:

```typescript
/** 관리자 셸. 학부모 레이아웃(app/(app)/layout.tsx)을 상속하지 않는다 —
 *  BottomNav·번역 배너 같은 학부모 UI 가 관리자 화면에 섞이면 안 되고,
 *  나중에 별도 서비스로 떼어낼 때 잘라낼 경계가 여기여야 한다. */
export default function AdminShellLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-slate-950 text-slate-100">{children}</div>
}
```

`app/(admin)/admin/login/AdminLoginForm.tsx`:

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function AdminLoginForm() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const response = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      // 계정 존재 여부·잠금 여부를 문구로 구별하지 않는다.
      setError('아이디 또는 비밀번호가 올바르지 않습니다.')
      return
    }
    router.replace(payload.next ?? '/admin')
    router.refresh()
  }

  return (
    <form onSubmit={onSubmit} className="flex w-full max-w-sm flex-col gap-3">
      <input
        className="rounded border border-slate-700 bg-slate-900 px-3 py-2"
        autoComplete="username"
        placeholder="아이디"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <input
        className="rounded border border-slate-700 bg-slate-900 px-3 py-2"
        type="password"
        autoComplete="current-password"
        placeholder="비밀번호"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-100 px-3 py-2 font-medium text-slate-900 disabled:opacity-50"
      >
        {busy ? '확인 중…' : '로그인'}
      </button>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}
    </form>
  )
}
```

`app/(admin)/admin/login/page.tsx`:

```typescript
import AdminLoginForm from './AdminLoginForm'

/** 유일한 미인증 관리자 경로. (protected) 그룹 밖에 두어야 레이아웃 검사에 걸리지 않는다. */
export default function AdminLoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <h1 className="text-lg font-semibold">나란히 운영 콘솔</h1>
      <AdminLoginForm />
    </main>
  )
}
```

- [ ] **Step 4: 이중 방어 ② 레이아웃과 대시보드를 만든다**

`app/(admin)/admin/(protected)/layout.tsx`:

```typescript
import { redirect } from 'next/navigation'
import { getAdminSession } from '@/lib/admin/session'

/** 이중 방어 ②. middleware 는 쿠키 «존재» 만 봤다 — 위조·만료·폐기된 쿠키는 여기서 걸린다.
 *  이 레이아웃 아래에 놓인 모든 페이지가 자동으로 검사를 받는다. */
export default async function AdminProtectedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const session = await getAdminSession()
  if (!session) {
    redirect('/admin/login')
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between border-b border-slate-800 pb-3">
        <nav className="flex gap-4 text-sm">
          <a href="/admin">대시보드</a>
          <a href="/admin/jobs">잡 큐</a>
          <a href="/admin/schools">학교 수집</a>
          <a href="/admin/schedulers">스케줄러</a>
          <a href="/admin/notices">공지 검수</a>
          <a href="/admin/reviews">번역 검토</a>
          <a href="/admin/runs">실행 이력</a>
        </nav>
        <form action="/api/admin/logout" method="post">
          <span className="mr-3 text-xs text-slate-400">
            {session.displayName ?? session.username}
          </span>
          <button type="submit" className="text-sm underline">로그아웃</button>
        </form>
      </header>
      {children}
    </div>
  )
}
```

`app/(admin)/admin/(protected)/page.tsx`:

```typescript
import { requireAdminSession } from '@/lib/admin/session'

export const dynamic = 'force-dynamic'

export default async function AdminDashboardPage() {
  const session = await requireAdminSession()
  return (
    <main className="flex flex-col gap-2">
      <h1 className="text-lg font-semibold">운영 대시보드</h1>
      <p className="text-sm text-slate-400">
        {session.displayName ?? session.username} · 세션 만료 {session.expiresAt}
      </p>
    </main>
  )
}
```

- [ ] **Step 5: 로그인·로그아웃 라우트를 만든다**

`app/api/admin/login/route.ts`:

```typescript
import { NextResponse, type NextRequest } from 'next/server'
import { ADMIN_COOKIE_NAME, ADMIN_SESSION_MAX_AGE_SECONDS } from '@/lib/admin/cookie'
import { createAdminSession, verifyAdminPassword, writeAdminAudit } from '@/lib/admin/session'

/** 성공·실패 모두 이 시간까지 붙잡는다. 계정 존재 여부를 소요 시간으로 유추하지 못하게. */
const FIXED_RESPONSE_MS = 700

async function holdUntil(deadline: number): Promise<void> {
  const remaining = deadline - Date.now()
  if (remaining > 0) {
    await new Promise((resolve) => setTimeout(resolve, remaining))
  }
}

export async function POST(request: NextRequest) {
  const startedAt = Date.now()
  const body = await request.json().catch(() => null)
  const username = typeof body?.username === 'string' ? body.username.trim() : ''
  const password = typeof body?.password === 'string' ? body.password : ''

  const outcome =
    username && password
      ? await verifyAdminPassword(username, password)
      : ({ status: 'invalid' } as const)

  if (outcome.status !== 'ok') {
    await holdUntil(startedAt + FIXED_RESPONSE_MS)
    // 'locked' 와 'invalid' 를 구별해 알리지 않는다 — 알리면 계정 존재가 드러난다.
    return NextResponse.json({ ok: false, error: 'invalid_credentials' }, { status: 401 })
  }

  const { token, expiresAt } = await createAdminSession(outcome.adminUserId)
  await writeAdminAudit(
    {
      adminUserId: outcome.adminUserId,
      username,
      displayName: outcome.displayName,
      expiresAt,
    },
    'admin_login',
    null,
  )
  await holdUntil(startedAt + FIXED_RESPONSE_MS)

  const response = NextResponse.json({ ok: true, next: '/admin' })
  response.cookies.set(ADMIN_COOKIE_NAME, token, {
    httpOnly: true,
    secure: true,
    sameSite: 'strict',
    path: '/',
    maxAge: ADMIN_SESSION_MAX_AGE_SECONDS,
  })
  return response
}
```

`app/api/admin/logout/route.ts`:

```typescript
import { NextResponse, type NextRequest } from 'next/server'
import { ADMIN_COOKIE_NAME } from '@/lib/admin/cookie'
import { revokeCurrentAdminSession } from '@/lib/admin/session'

export async function POST(request: NextRequest) {
  await revokeCurrentAdminSession()
  // 레이아웃의 form 은 HTML 폼 제출이라 리다이렉트를, fetch 호출은 JSON 을 기대한다.
  const wantsHtml = (request.headers.get('accept') ?? '').includes('text/html')
  const response = wantsHtml
    ? NextResponse.redirect(new URL('/admin/login', request.url), { status: 303 })
    : NextResponse.json({ ok: true })
  response.cookies.set(ADMIN_COOKIE_NAME, '', {
    httpOnly: true,
    secure: true,
    sameSite: 'strict',
    path: '/',
    maxAge: 0,
  })
  return response
}
```

- [ ] **Step 6: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공. 빌드 로그의 라우트 목록에 `/admin`, `/admin/login`, `/api/admin/login`, `/api/admin/logout` 이 나온다.

- [ ] **Step 7: 비인가 접근을 시험한다 (스펙 §12.1 #1·#3·#4·#7)**

dev 서버를 재기동하고:

```bash
rm -f /tmp/admin_cookies.txt
echo "--- #1 시크릿창 상태에서 /admin ---"
curl -s -o /tmp/body1.html -w "HTTP %{http_code} → %{redirect_url}\n" http://localhost:3000/admin
grep -c "운영 대시보드" /tmp/body1.html; echo "(0 이면 대시보드 내용이 한 글자도 안 샜다)"

echo "--- #3 프리뷰 쿠키를 심고 /admin ---"
curl -s -o /dev/null -b "ui_preview=true" -w "HTTP %{http_code} → %{redirect_url}\n" http://localhost:3000/admin

echo "--- #4 학부모 세션으로 /api/admin/jobs ---"
curl -s -c /tmp/parent.txt -o /dev/null http://localhost:3000/home
curl -s -b /tmp/parent.txt -w "HTTP %{http_code} | body=%{size_download}B\n" -o /tmp/body4.json http://localhost:3000/api/admin/jobs
cat /tmp/body4.json; echo

echo "--- #7 관리자 쿠키 없이 /api/admin/schedulers ---"
curl -s -w "HTTP %{http_code}\n" -o /dev/null http://localhost:3000/api/admin/schedulers
```

Expected:
- #1 `HTTP 307` → `/admin/login`, grep 결과 `0`
- #3 `HTTP 307` → `/admin/login` — **`ui_preview` 쿠키가 아무 효과가 없다**
- #4 `HTTP 401` + 본문이 **JSON** `{"ok":false,"error":"unauthorized"}` (HTML 리다이렉트가 아니다)
- #7 `HTTP 401`

> #7 은 아직 라우트가 없어도 middleware 가 먼저 401 을 낸다. 그것이 정답이다.

- [ ] **Step 8: 로그인 왕복을 시험한다 (스펙 §12.1 #2·#11)**

```bash
PWFILE="$(mktemp)"
gcloud secrets versions access latest --secret=admin-console-password > "$PWFILE"

echo "--- 틀린 비밀번호 ---"
curl -s -o /dev/null -w "HTTP %{http_code} | %{time_total}s\n" \
  -H 'content-type: application/json' \
  -d '{"username":"naranhi","password":"definitely-wrong"}' \
  http://localhost:3000/api/admin/login

echo "--- 맞는 비밀번호 (학부모 쿠키를 이미 들고 있는 상태로) ---"
python - "$PWFILE" <<'PY'
import json, subprocess, sys
pw = open(sys.argv[1], encoding="utf-8").read()
body = json.dumps({"username": "naranhi", "password": pw})
subprocess.run([
    "curl", "-s", "-b", "/tmp/parent.txt", "-c", "/tmp/admin_cookies.txt",
    "-o", "/tmp/login.json", "-w", "HTTP %{http_code} | %{time_total}s\\n",
    "-H", "content-type: application/json", "--data-binary", "@-",
    "http://localhost:3000/api/admin/login",
], input=body.encode(), check=True)
PY
rm -f "$PWFILE"
cat /tmp/login.json; echo
grep -o "naranhi_admin" /tmp/admin_cookies.txt | head -1

echo "--- #2 학부모 세션만으로 /admin (관리자 쿠키 없이) ---"
curl -s -o /dev/null -b /tmp/parent.txt -w "HTTP %{http_code} → %{redirect_url}\n" http://localhost:3000/admin

echo "--- 관리자 쿠키로 /admin ---"
curl -s -b /tmp/admin_cookies.txt -o /tmp/body_ok.html -w "HTTP %{http_code}\n" http://localhost:3000/admin
grep -c "운영 대시보드" /tmp/body_ok.html

echo "--- #11 로그아웃 후 같은 쿠키 재사용 ---"
curl -s -b /tmp/admin_cookies.txt -o /dev/null -X POST http://localhost:3000/api/admin/logout
curl -s -o /dev/null -b /tmp/admin_cookies.txt -w "HTTP %{http_code} → %{redirect_url}\n" http://localhost:3000/admin
```

Expected:
- 틀린 비밀번호 `HTTP 401`, 소요 시간 **0.7초 이상** (고정 지연)
- 맞는 비밀번호 `HTTP 200`, 쿠키 파일에 `naranhi_admin` 이 있다
- **#2 `HTTP 307` → `/admin/login`** — 학부모 세션은 관리자 판정에 아무 정보도 주지 못한다 (§1.4 핵심 제약 검증)
- 관리자 쿠키로는 `HTTP 200` + grep 결과 `1`
- **#11 로그아웃 후 같은 쿠키로 `HTTP 307` → `/admin/login`** — `revoked_at` 이 걸렸다

> `__Host-` 접두는 `Secure` 를 요구한다. `http://localhost` 는 브라우저가 신뢰하는 출처라 크롬·파이어폭스에서 동작하지만, **curl 은 `Secure` 쿠키를 http 응답에서 저장하지 않을 수 있다.** 위 확인이 쿠키 파일 문제로 실패하면 `--insecure` 가 아니라 `npm run build && npm run start` 후 https 프록시(예: `caddy reverse-proxy --to :3000 --from localhost:8443`)로 다시 시험한다. 프로덕션은 항상 https 이므로 이 문제는 로컬에만 있다.

- [ ] **Step 9: 커밋**

```bash
git add middleware.ts app/\(admin\) app/api/admin
git commit -m "feat(admin): /admin 관리자 게이트와 로그인 — 이중 방어

관리자 판정을 middleware 함수의 가장 앞에 둔다. 그 아래는 전부 학부모
흐름이고, 학부모 흐름에 우회가 하나라도 생기면 관리자 표면까지 닿는다.
사업 A 가 TEST_ENTRY_BYPASS·ui_preview 분기를 지웠지만 순서 자체가 방어다.

middleware 는 쿠키 존재만 본다 — Edge 런타임이라 service_role 도 node:crypto
도 못 쓰고 매 요청 DB 왕복도 부적절하다. 실제 세션 검증은 (protected)/layout.tsx
와 각 API 핸들러의 requireAdminSession() 이 다시 한다. matcher 가 점 포함
경로를 제외하므로 middleware 하나만 믿으면 안 된다.

관리자 경로를 PUBLIC_PATHS 에 넣지 않는다. /admin/login 예외는 adminGate
안에서만 처리한다 — 공개 목록에 올리면 학부모 흐름의 startsWith 와 섞인다.

로그인 실패는 계정 존재·잠금 여부를 문구로도 소요 시간으로도 구별시키지 않는다."
```

---

## Task 6: 구조화 로깅

Job 진입점 6개가 전부 평문 포맷이다 — `logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s")`. 평문이면 Cloud Logging 의 `severity` 매핑과 구조화 필드를 못 탄다. **로그 기반 지표를 만들 수 없고 심각도 필터도 못 건다.**

새 의존성 없이 `logging.Formatter` 서브클래스 하나로 해결한다.

**Files:**
- Create: `backend/app/core/logging_setup.py`
- Create: `backend/tests/test_logging_setup.py`
- Modify: `backend/app/main.py:14`, `backend/app/worker_main.py:77`, `backend/app/jobs/crawler_worker.py:175`, `backend/app/jobs/translation_worker.py:142`, `backend/app/jobs/scheduled_school_crawler.py:52`, `backend/app/jobs/scheduled_content_extractor.py:53`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `CloudLoggingFormatter(job_type: str | None = None)` — `logging.Formatter` 서브클래스, JSON 한 줄 출력
  - `setup_logging(*, job_type: str | None = None, level: str | None = None) -> None`
  - 출력 키: `severity`, `message`, `logger`, 선택적 `job_type`, `exception`, 그리고 `LOGGER.info(..., extra={...})` 로 붙인 임의 필드

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_logging_setup.py`:

```python
import json
import logging
import unittest

from app.core.logging_setup import CloudLoggingFormatter


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="naranhi.test",
        level=logging.WARNING,
        pathname="x.py",
        lineno=10,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class CloudLoggingFormatterTest(unittest.TestCase):
    def test_emits_single_json_line_with_severity(self):
        """Cloud Logging 은 stdout 한 줄을 하나의 로그로 읽는다.
        줄바꿈이 섞이면 한 사건이 여러 엔트리로 쪼개진다."""
        output = CloudLoggingFormatter().format(_record())
        self.assertNotIn("\n", output)
        payload = json.loads(output)
        self.assertEqual(payload["severity"], "WARNING")
        self.assertEqual(payload["message"], "hello world")
        self.assertEqual(payload["logger"], "naranhi.test")

    def test_job_type_and_extra_fields_are_included(self):
        """extra= 로 붙인 필드가 구조화 필드로 나가야 로그 기반 지표를 걸 수 있다."""
        payload = json.loads(
            CloudLoggingFormatter(job_type="school_crawl").format(_record(school_id="s-1"))
        )
        self.assertEqual(payload["job_type"], "school_crawl")
        self.assertEqual(payload["school_id"], "s-1")

    def test_exception_is_flattened_into_one_line(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _record()
            record.exc_info = sys.exc_info()
        output = CloudLoggingFormatter().format(record)
        self.assertNotIn("\n", output)
        payload = json.loads(output)
        self.assertIn("ValueError: boom", payload["exception"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_logging_setup -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.logging_setup'`

- [ ] **Step 3: 최소 구현**

`backend/app/core/logging_setup.py`:

```python
"""Cloud Logging 이 읽는 구조화 JSON 한 줄 로깅.

평문 포맷(%(asctime)s %(levelname)s …)은 severity 매핑과 구조화 필드를 못 태운다.
그래서 지금은 로그 기반 지표를 만들 수 없고 심각도 필터도 걸리지 않는다.
새 의존성 없이 Formatter 하나로 해결한다.
"""

from __future__ import annotations

import json
import logging
import os

# LogRecord 가 기본으로 갖는 속성들. 이 밖의 속성만 구조화 필드로 내보낸다
# (LOGGER.info(..., extra={"school_id": ...}) 로 붙인 것들).
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


class CloudLoggingFormatter(logging.Formatter):
    def __init__(self, *, job_type: str | None = None) -> None:
        super().__init__()
        self._job_type = job_type

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if self._job_type:
            payload["job_type"] = self._job_type
        if record.exc_info:
            # 여러 줄 traceback 을 한 필드에 담는다. json.dumps 가 \n 을 이스케이프하므로
            # 출력은 여전히 한 줄이다.
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = _jsonable(value)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(*, job_type: str | None = None, level: str | None = None) -> None:
    """진입점에서 한 번 부른다. basicConfig 를 대체한다."""
    resolved = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(CloudLoggingFormatter(job_type=job_type))
    logging.basicConfig(
        level=getattr(logging, resolved, logging.INFO),
        handlers=[handler],
        force=True,
    )
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_logging_setup -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: 진입점 6개를 교체한다**

각 파일에서 `logging.basicConfig(...)` 호출을 `setup_logging(...)` 으로 바꾸고 import 를 추가한다.

`backend/app/main.py:14` — `create_app()` 안:

```python
from app.core.logging_setup import setup_logging
...
    setup_logging(job_type="api", level=settings.log_level)
```

`backend/app/worker_main.py:77` — `lifespan()` 안:

```python
from app.core.logging_setup import setup_logging
...
    setup_logging(job_type="worker_service", level=get_settings().log_level)
```

(기존 `level_name = get_settings().log_level.upper()` 줄은 지운다.)

`backend/app/jobs/crawler_worker.py:175` — `main()` 안:

```python
from app.core.logging_setup import setup_logging
...
    setup_logging(job_type="crawler_worker")
```

`backend/app/jobs/translation_worker.py:142` — `main()` 안:

```python
    setup_logging(job_type="translation_worker")
```

`backend/app/jobs/scheduled_school_crawler.py:52` — `main()` 안:

```python
    setup_logging(job_type="scheduled_school_crawler")
```

`backend/app/jobs/scheduled_content_extractor.py:53` — `main()` 안:

```python
    setup_logging(job_type="scheduled_content_extractor")
```

- [ ] **Step 6: `basicConfig` 가 남지 않았는지 확인한다**

```bash
grep -rn "basicConfig" backend/app --include=*.py
echo "종료코드: $?  (1 이면 없음 = 정상)"
grep -rn "setup_logging" backend/app --include=*.py | wc -l
```

Expected: 첫 grep 출력 없음(종료코드 1). `setup_logging` 참조가 **12개** (import 6 + 호출 6)

- [ ] **Step 7: 실제로 JSON 이 나오는지 확인한다**

```bash
PYTHONPATH=backend python -c "
import logging
from app.core.logging_setup import setup_logging
setup_logging(job_type='probe')
logging.getLogger('naranhi.probe').warning('테스트 %s', 'ok', extra={'school_id': 's-1'})
try:
    raise RuntimeError('boom')
except RuntimeError:
    logging.getLogger('naranhi.probe').exception('죽었다')
" 2>&1 | python -c "
import json,sys
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    d=json.loads(line)
    print(d['severity'], '|', d['logger'], '|', d['message'], '|', sorted(k for k in d if k not in ('severity','logger','message')))
"
```

Expected:
```
WARNING | naranhi.probe | 테스트 ok | ['job_type', 'school_id']
ERROR | naranhi.probe | 죽었다 | ['exception', 'job_type']
```

- [ ] **Step 8: 기존 백엔드 테스트가 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend python -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 9: 커밋**

```bash
git add backend/app/core/logging_setup.py backend/tests/test_logging_setup.py \
        backend/app/main.py backend/app/worker_main.py backend/app/jobs
git commit -m "feat(observability): 진입점 6개를 구조화 JSON 로깅으로 전환

평문 포맷은 Cloud Logging 의 severity 매핑과 구조화 필드를 못 탄다.
그래서 지금은 severity=ERROR 필터도, 로그 기반 지표도 만들 수 없다.
관리자 화면의 실패 알림이 여기에 막혀 있었다.

새 의존성 없이 logging.Formatter 서브클래스 하나로 한 줄 JSON 을 찍는다.
extra= 로 붙인 필드가 그대로 구조화 필드가 되고, traceback 은 한 필드에
담겨 한 사건이 여러 엔트리로 쪼개지지 않는다.

각 진입점이 job_type 을 심으므로 어느 Job 의 로그인지 필터할 수 있다."
```

---

## Task 7: `0041` 관측 스키마

크롤 실행 요약이 지금 **stdout JSON 한 줄로만 나가고 사라진다** — `scheduled_school_crawler.py:46` 의 `print(json.dumps(...))` 가 전부다. 역사적 성공률을 볼 방법이 없다.

번역 검토 신호도 담을 곳이 없다. `0012:6-10` 이 `requires_admin_review` / `admin_review_reason` 를, `0020:1-2` 가 `metadata` 를 지웠다. 남은 `validation_status` 는 최종 번역문만 있으면 **무조건 `'passed'`** 로 덮어써지고(`notice_service.py:778-781`), 진짜 사유는 평문 `LOGGER.warning` 한 줄로만 존재한다.

**Files:**
- Create: `supabase/migrations/0041_admin_console_observability.sql`
- Modify: `types/database.ts` (`crawl_run_history` 추가, `notice_ai_translations` 에 2컬럼)

**Interfaces:**
- Consumes: 사업 A 의 `db-migrate` 워크플로
- Produces:
  - 테이블 `public.crawl_run_history` — `ScheduledCrawlerSummary`(`scheduled_crawler_service.py:57-78`) 14개 키 + `outcome` + `error_message`
  - `outcome text check in ('ok','idle','alarm','crashed')`
  - `notice_ai_translations.needs_review boolean not null default false`, `.review_reason text`
  - 부분 인덱스 `notice_ai_translations_needs_review_idx ... where needs_review`
  - 타입 `Database['public']['Tables']['crawl_run_history']`, `CrawlRunOutcome`

- [ ] **Step 1: 마이그레이션을 쓴다**

`supabase/migrations/0041_admin_console_observability.sql`:

```sql
-- 관측 기반: 크롤 실행 이력 + 번역 검토 신호.
--
-- 번호가 0039 가 아니라 0041 인 이유: 스펙 §5.3 은 이 사업에 0039 를 배정했지만
-- 사업 E(RSS·공식 API)가 0039(school_events_source)와 0040(school_crawl_state_rss_feed)을
-- 이미 가져갔다. 0042~0044 는 비어 있고 사업 D 는 0045 부터 쓴다.

-- ── ① 크롤 실행 이력 ─────────────────────────────────────────────
-- 지금은 요약이 stdout JSON 한 줄로만 나가고 사라진다
-- (scheduled_school_crawler.py:46). 역사적 성공률의 유일한 데이터 소스가 된다.
--
-- outcome 이 왜 필요한가 — 두 가지 함정이 실측된 코드 동작이다:
--   ① scheduled_crawler_service.py:335-336 은 processed_count == 0 이면
--      success_rate 를 1.0 으로, alarm 을 False 로 만든다. 즉 «아무것도 안 돌았음» 이
--      «성공» 과 구별되지 않는다 → 'idle' 로 따로 기록한다.
--   ② exit 1 의 사유가 둘로 겹친다 — 성공률 미달(:77-78)과 크래시
--      (scheduled_school_crawler.py:60-73). exit code 로는 구별할 수 없다
--      → 'alarm' 과 'crashed' 로 나눈다.
create table if not exists public.crawl_run_history (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null,
  finished_at timestamptz not null,
  outcome text not null,
  dry_run boolean not null default false,
  force boolean not null default false,
  total_registered integer not null default 0,
  selected_count integer not null default 0,
  skipped_count integer not null default 0,
  processed_count integer not null default 0,
  success_count integer not null default 0,
  failure_count integer not null default 0,
  -- 이름은 CRAWLER_SCHEDULE_FAIL_RATE_THRESHOLD 지만 실제로는 «성공률» 과 비교한다
  -- (config.py:106-111, scheduled_crawler_service.py:336). 화면 라벨은 «성공률 임계치».
  success_rate numeric not null default 0,
  alarm boolean not null default false,
  targets jsonb not null default '[]'::jsonb,
  results jsonb not null default '[]'::jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  constraint crawl_run_history_outcome_check
    check (outcome in ('ok', 'idle', 'alarm', 'crashed'))
);

create index if not exists crawl_run_history_created_idx
  on public.crawl_run_history (created_at desc);

-- 내부 운영 테이블. RLS 활성 + 정책 0개 = service_role 전용.
-- 선례 0013_school_crawl_state.sql:72, 0036_app_jobs_rls.sql
alter table public.crawl_run_history enable row level security;

-- ── ② 번역 검토 신호 ─────────────────────────────────────────────
-- 0012:6-10 이 requires_admin_review / admin_review_reason 를,
-- 0020:1-2 가 사유를 담던 metadata 를 지웠다. 남은 validation_status 는
-- 최종 번역문만 있으면 무조건 'passed' 로 덮어써진다(notice_service.py:778-781).
-- 안전장치는 동작하는데 출력을 받는 곳이 없다.
--
-- needs_review 는 사용자 노출을 바꾸지 않는다 — 번역문은 그대로 나가고
-- 검토 큐에도 «함께» 올라간다.
alter table public.notice_ai_translations
  add column if not exists needs_review boolean not null default false,
  add column if not exists review_reason text;

-- 0005:26-27 이 지웠던 검토 인덱스와 같은 역할. 검토 대상만 담는 부분 인덱스라
-- 전체 155행 중 소수만 인덱싱된다.
create index if not exists notice_ai_translations_needs_review_idx
  on public.notice_ai_translations (needs_review)
  where needs_review;
```

- [ ] **Step 2: 번호 검사를 통과하는지 확인한다**

```bash
python scripts/check_migration_numbers.py
```

Expected: `번호 중복 없음` + 종료코드 0. 개수는 형제 사업의 머지 상황에 따라 달라진다.

> `번호 중복 0041` 이 나오면 다른 사업이 그 번호를 가져갔다는 뜻이다. **중단하고 보고할 것** — 파일명을 바꾸면 이미 적용된 이력과 어긋난다. `0042`~`0044` 가 비어 있으므로(사업 D 는 `0045` 부터) 그쪽으로 옮기면 된다.

- [ ] **Step 3: 타입을 추가한다**

`types/database.ts` 의 `NoticeAiValidationStatus` 선언 아래:

```typescript
export type CrawlRunOutcome = 'ok' | 'idle' | 'alarm' | 'crashed'
```

`notice_ai_translations` 의 `Row` / `Insert` / `Update` 각각에 두 줄씩 (`validation_status` 다음 자리):

```typescript
          validation_status: NoticeAiValidationStatus
          needs_review: boolean
          review_reason: string | null
```

```typescript
          validation_status?: NoticeAiValidationStatus
          needs_review?: boolean
          review_reason?: string | null
```

```typescript
          validation_status?: NoticeAiValidationStatus
          needs_review?: boolean
          review_reason?: string | null
```

그리고 `Tables` 블록에 새 테이블:

```typescript
      crawl_run_history: {
        Row: {
          id: string
          started_at: string
          finished_at: string
          outcome: CrawlRunOutcome
          dry_run: boolean
          force: boolean
          total_registered: number
          selected_count: number
          skipped_count: number
          processed_count: number
          success_count: number
          failure_count: number
          success_rate: number
          alarm: boolean
          targets: Json
          results: Json
          error_message: string | null
          created_at: string
        }
        Insert: {
          id?: string
          started_at: string
          finished_at: string
          outcome: CrawlRunOutcome
          dry_run?: boolean
          force?: boolean
          total_registered?: number
          selected_count?: number
          skipped_count?: number
          processed_count?: number
          success_count?: number
          failure_count?: number
          success_rate?: number
          alarm?: boolean
          targets?: Json
          results?: Json
          error_message?: string | null
          created_at?: string
        }
        Update: {
          outcome?: CrawlRunOutcome
          error_message?: string | null
        }
        Relationships: []
      }
```

- [ ] **Step 4: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공

- [ ] **Step 5: 커밋**

```bash
git add supabase/migrations/0041_admin_console_observability.sql types/database.ts
git commit -m "feat(observability): 크롤 실행 이력 테이블 + 번역 검토 신호 컬럼

크롤 요약이 stdout JSON 한 줄로만 나가고 사라진다. 역사적 성공률을 볼
방법이 없어서 crawl_run_history 에 ScheduledCrawlerSummary 14개 키를 그대로
쌓는다. outcome 을 따로 두는 이유는 두 가지 함정 때문이다 —
processed_count==0 이 success_rate 1.0 으로 '성공' 처럼 보고되고(:335-336),
exit 1 의 사유가 성공률 미달과 크래시 둘로 겹친다.

번역 검토 신호는 0012 가 검수 컬럼을, 0020 이 사유를 담던 metadata 를
지우면서 담을 곳이 없어졌다. needs_review / review_reason 을 되살린다.
사용자 노출은 바뀌지 않는다 — 번역문은 그대로 나가고 검토 큐에 함께 오른다.

번호는 0041 이다. 스펙 §5.3 이 배정한 0039 와 그 다음 0040 을 사업 E 가 이미 쓴다.

적용은 머지 시 db-migrate 워크플로가 수행한다."
```

- [ ] **Step 6: 머지 후 적용됐는지 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
def head(path):
    r=urllib.request.Request(u+path); r.add_header('apikey',k)
    r.add_header('Authorization','Bearer '+k); r.add_header('Prefer','count=exact')
    x=urllib.request.urlopen(r,timeout=60); return x.status, x.headers.get('Content-Range')
print('crawl_run_history        ', *head('/rest/v1/crawl_run_history?select=id&limit=1'))
print('needs_review 컬럼        ', *head('/rest/v1/notice_ai_translations?select=id,needs_review,review_reason&limit=1'))
"
export SUPABASE_ANON_KEY="$(gh variable get NEXT_PUBLIC_SUPABASE_ANON_KEY)"
python -c "
import os,urllib.request,urllib.error
u=os.environ['SUPABASE_URL'].rstrip('/'); a=os.environ['SUPABASE_ANON_KEY']
r=urllib.request.Request(u+'/rest/v1/crawl_run_history?select=id&limit=1')
r.add_header('apikey',a); r.add_header('Authorization','Bearer '+a); r.add_header('Prefer','count=exact')
try:
    x=urllib.request.urlopen(r,timeout=60); print('anon:', x.status, x.headers.get('Content-Range'))
except urllib.error.HTTPError as e: print('anon:', e.code, e.reason)
"
```

Expected: `crawl_run_history 200 */0`, `needs_review 컬럼 200 …` (컬럼이 존재), anon 은 `*/0` 또는 4xx

---

## Task 8: 실행 이력 적재

**Files:**
- Create: `backend/app/services/crawl_run_history_service.py`
- Create: `backend/tests/test_crawl_run_history.py`
- Modify: `backend/app/jobs/scheduled_school_crawler.py` (`run_async`, `main`)

**Interfaces:**
- Consumes: Task 7 의 `crawl_run_history` 테이블, `ScheduledCrawlerSummary.to_dict()` 14개 키
- Produces:
  - `outcome_for(summary: dict[str, Any]) -> str` — `'idle' | 'alarm' | 'ok'`
  - `record_crawl_run(summary: dict[str, Any], *, outcome: str, error_message: str | None = None) -> bool` — best-effort, 실패해도 잡 결과를 바꾸지 않는다
  - 정기 크롤 1회당 `crawl_run_history` 1행

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_crawl_run_history.py`:

```python
import unittest
from unittest.mock import MagicMock, patch

from app.services import crawl_run_history_service as service


class OutcomeTest(unittest.TestCase):
    def test_zero_processed_is_idle_not_ok(self):
        """processed_count == 0 이면 scheduled_crawler_service.py:335-336 이
        success_rate 를 1.0, alarm 을 False 로 만든다. 그대로 쌓으면 화면이
        «아무것도 안 돌았음» 을 «성공» 으로 보여준다."""
        summary = {"processed_count": 0, "success_rate": 1.0, "alarm": False}
        self.assertEqual(service.outcome_for(summary), "idle")

    def test_alarm_beats_ok(self):
        summary = {"processed_count": 5, "success_rate": 0.2, "alarm": True}
        self.assertEqual(service.outcome_for(summary), "alarm")

    def test_normal_run_is_ok(self):
        summary = {"processed_count": 5, "success_rate": 1.0, "alarm": False}
        self.assertEqual(service.outcome_for(summary), "ok")


class RecordCrawlRunTest(unittest.TestCase):
    def test_inserts_all_summary_keys(self):
        client = MagicMock()
        summary = {
            "started_at": "2026-08-27T00:00:00+00:00",
            "finished_at": "2026-08-27T00:05:00+00:00",
            "dry_run": False,
            "force": False,
            "total_registered": 8,
            "selected_count": 6,
            "skipped_count": 2,
            "processed_count": 6,
            "success_count": 5,
            "failure_count": 1,
            "success_rate": 0.8333,
            "alarm": False,
            "targets": [{"school_id": "s-1"}],
            "results": [{"school_id": "s-1", "status": "success"}],
        }
        with patch.object(service, "get_supabase_client", return_value=client):
            self.assertTrue(service.record_crawl_run(summary, outcome="ok"))
        row = client.table.return_value.insert.call_args.args[0]
        self.assertEqual(row["outcome"], "ok")
        self.assertEqual(row["processed_count"], 6)
        self.assertEqual(row["success_count"], 5)
        self.assertEqual(row["targets"], [{"school_id": "s-1"}])
        self.assertIsNone(row["error_message"])

    def test_insert_failure_does_not_raise(self):
        """이력 적재 실패가 크롤 결과를 바꾸면 안 된다."""
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = RuntimeError("boom")
        with patch.object(service, "get_supabase_client", return_value=client):
            self.assertFalse(service.record_crawl_run({"processed_count": 0}, outcome="idle"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_crawl_run_history -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.crawl_run_history_service'`

- [ ] **Step 3: 최소 구현**

`backend/app/services/crawl_run_history_service.py`:

```python
"""정기 크롤 실행 요약을 crawl_run_history 에 1행 남긴다.

지금은 요약이 stdout JSON 한 줄로만 나가고 사라진다(scheduled_school_crawler.py:46).
이 테이블이 «성공률 추이» 화면의 유일한 데이터 소스다.

outcome 은 exit code 로 구별할 수 없는 네 가지를 나눈다:
  idle     processed_count == 0. 아무 학교도 안 돌았는데 success_rate 는 1.0,
           alarm 은 False 로 나온다(scheduled_crawler_service.py:335-336).
  alarm    성공률이 임계치 미만. exit 1.
  crashed  잡 자체가 예외로 죽음. exit 1 — alarm 과 exit code 가 겹친다.
  ok       그 외.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.supabase import get_supabase_client

LOGGER = logging.getLogger(__name__)


def outcome_for(summary: dict[str, Any]) -> str:
    if int(summary.get("processed_count") or 0) == 0:
        return "idle"
    if bool(summary.get("alarm")):
        return "alarm"
    return "ok"


def record_crawl_run(
    summary: dict[str, Any],
    *,
    outcome: str,
    error_message: str | None = None,
) -> bool:
    """실행 이력 1행 적재. best-effort — 실패해도 크롤 결과를 바꾸지 않는다."""
    row = {
        "started_at": summary.get("started_at"),
        "finished_at": summary.get("finished_at"),
        "outcome": outcome,
        "dry_run": bool(summary.get("dry_run")),
        "force": bool(summary.get("force")),
        "total_registered": int(summary.get("total_registered") or 0),
        "selected_count": int(summary.get("selected_count") or 0),
        "skipped_count": int(summary.get("skipped_count") or 0),
        "processed_count": int(summary.get("processed_count") or 0),
        "success_count": int(summary.get("success_count") or 0),
        "failure_count": int(summary.get("failure_count") or 0),
        "success_rate": float(summary.get("success_rate") or 0.0),
        "alarm": bool(summary.get("alarm")),
        "targets": summary.get("targets") or [],
        "results": summary.get("results") or [],
        "error_message": error_message,
    }
    try:
        get_supabase_client().table("crawl_run_history").insert(row).execute()
        return True
    except Exception as exc:  # noqa: BLE001 - 이력 적재 실패가 크롤 결과를 바꾸면 안 된다.
        LOGGER.warning(
            "crawl run history insert failed: outcome=%s error=%s",
            outcome,
            exc,
        )
        return False
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_crawl_run_history -v
```

Expected: PASS (5 tests)

- [ ] **Step 5: 크롤 진입점에서 적재한다**

`backend/app/jobs/scheduled_school_crawler.py` 상단 import 추가:

```python
from datetime import UTC, datetime

from app.services.crawl_run_history_service import outcome_for, record_crawl_run
```

`run_async` 를 교체:

```python
async def run_async(args: argparse.Namespace) -> int:
    summary = await ScheduledCrawlerService().run(
        school_id=args.school_id,
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
    )
    payload = summary.to_dict()
    print(json.dumps(payload, ensure_ascii=False))
    # dry-run 은 이력에 쌓지 않는다 — 실제로 아무것도 수집하지 않았기 때문이다.
    if not args.dry_run:
        record_crawl_run(payload, outcome=outcome_for(payload))
    return summary.exit_code()
```

`main` 의 예외 분기에서도 남긴다. `main` 을 교체:

```python
def main(argv: list[str] | None = None) -> int:
    setup_logging(job_type="scheduled_school_crawler")
    parser = build_parser()
    args = parser.parse_args(argv)
    started_at = datetime.now(UTC).isoformat()
    try:
        return asyncio.run(run_async(args))
    except Exception as exc:  # noqa: BLE001 - job should fail loudly on systemic errors.
        LOGGER.exception("scheduled school crawler job failed")
        # 크래시도 이력에 남긴다. exit 1 만으로는 성공률 미달(alarm)과 구별되지 않는다.
        if not args.dry_run:
            record_crawl_run(
                {
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "dry_run": args.dry_run,
                    "force": args.force,
                },
                outcome="crashed",
                error_message=f"{type(exc).__name__}: {exc}",
            )
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "job_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
```

- [ ] **Step 6: 전체 백엔드 테스트**

```bash
PYTHONPATH=backend python -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 7: dry-run 이 이력을 남기지 않는지 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_scheduled_crawler_service -v
PYTHONPATH=backend python -c "
import sys
from unittest.mock import patch
import app.jobs.scheduled_school_crawler as job
with patch.object(job, 'record_crawl_run') as rec, \
     patch.object(job.ScheduledCrawlerService, 'run') as run:
    class S:
        def to_dict(self): return {'processed_count': 0}
        def exit_code(self): return 0
    async def fake(**kw): return S()
    run.side_effect = fake
    job.main(['--dry-run'])
    print('dry-run 적재 호출:', rec.call_count)
    job.main([])
    print('평상시 적재 호출:', rec.call_count)
"
```

Expected: `dry-run 적재 호출: 0` / `평상시 적재 호출: 1`

- [ ] **Step 8: 커밋**

```bash
git add backend/app/services/crawl_run_history_service.py \
        backend/tests/test_crawl_run_history.py \
        backend/app/jobs/scheduled_school_crawler.py
git commit -m "feat(observability): 정기 크롤 실행 이력을 DB 에 누적

요약이 stdout JSON 한 줄로 나가고 사라져서 역사적 성공률을 볼 수 없었다.
Job 종료 직전 insert 1회로 crawl_run_history 에 쌓는다.

outcome 을 명시적으로 기록한다. exit code 로는 구별되지 않는 것들이 있다 —
processed_count==0 은 success_rate 1.0 / alarm False 라 '성공' 과 같은 모양이고
(scheduled_crawler_service.py:335-336), exit 1 은 성공률 미달과 크래시가 겹친다.
idle / alarm / crashed / ok 로 나눈다.

적재는 best-effort 다. 이력 insert 실패가 크롤 결과를 바꾸면 안 된다.
dry-run 은 쌓지 않는다 — 실제로 아무것도 수집하지 않았다."
```

- [ ] **Step 9: 배포 후 실제 실행에서 행이 생기는지 확인한다**

정기 크롤이 한 번 돈 뒤 (또는 Cloud Run Job 을 수동 실행한 뒤):

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/crawl_run_history?select=created_at,outcome,processed_count,success_count,failure_count,success_rate,alarm&order=created_at.desc&limit=5')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
for row in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()):
    print(row['created_at'][:19], row['outcome'], f\"처리 {row['processed_count']} 성공 {row['success_count']} 실패 {row['failure_count']} 성공률 {row['success_rate']}\")
"
```

Expected: 최소 1행. **스펙 §15 Q6 주의** — 스케줄러 5개가 PAUSED 라면 정기 실행이 없다. 그때는 `gcloud run jobs execute <SCHOOL_CRAWLER_JOB> --wait` 로 한 번 돌려 확인한다.

---

## Task 9: 번역 검토 신호 복구

`notice_service.py:778-787` 이 최종 번역문이 있으면 `validation_status` 를 무조건 `'passed'` 로 덮어쓰고, 실패 사유는 평문 `LOGGER.warning` 으로만 남긴다. 검색도 집계도 안 된다.

> **⚠️ 스펙 §9.3 의 사실 정정.** 스펙은 «`admin_review_required` 가 `backend/app/` 에 0건» 이라고 적었는데, 실제로는 파이프라인 결과에 **`admin_review: {required, reason, priority}` 딕셔너리가 존재한다** (`orchestrator.py:220,348,491`, `notice_service.py:137,363,414,428,454,508,697,741`). 다만 **`required` 가 모든 자리에서 리터럴 `False`** 다 — `grep '"required": True'` 결과 0건. 즉 «신호가 없다» 가 아니라 **«신호 통로는 있는데 아무도 True 를 넣지 않는 죽은 필드»** 다. 이 계획은 살아 있는 신호인 `metadata.validation_failure_reason`(`orchestrator.py:444`, `notice_service.py:660`)을 주 근거로 쓰되, `admin_review.required` 도 함께 본다 — 나중에 그 필드가 살아나면 자동으로 검토 큐에 오른다.

**Files:**
- Modify: `backend/app/services/notice_service.py` (`_save_translation_result` 의 검증 블록과 `row` 조립)
- Create: `backend/tests/test_translation_review_signal.py`

**Interfaces:**
- Consumes: Task 7 의 `needs_review` / `review_reason` 컬럼
- Produces:
  - `notice_ai_translations.needs_review = true` + `review_reason` 이 실제로 채워진다
  - `_needs_review_from_pipeline(pipeline_result, metadata) -> tuple[bool, str | None]` (모듈 레벨 함수, 테스트 대상)
  - **사용자 노출은 바뀌지 않는다** — `validation_status='passed'` 와 번역문 저장 동작이 그대로다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_translation_review_signal.py`:

```python
import unittest

from app.services.notice_service import _needs_review_from_pipeline


class NeedsReviewTest(unittest.TestCase):
    def test_clean_translation_does_not_need_review(self):
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": "안녕하세요", "admin_review": {"required": False, "reason": None}},
            {"validation_status": "passed", "validation_failure_reason": None},
        )
        self.assertFalse(needs)
        self.assertIsNone(reason)

    def test_validation_failure_reason_raises_the_flag(self):
        """검증이 실패해도 번역문이 있으면 validation_status 가 'passed' 로 덮어써진다
        (notice_service.py:778-781). 사유는 평문 로그로만 남아 있었다."""
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": "안녕하세요"},
            {"validation_failure_reason": "hard_fact_mismatch: 날짜 3건"},
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "hard_fact_mismatch: 날짜 3건")

    def test_quota_fallback_raises_the_flag(self):
        """notice_service.py:660 의 best-effort 폴백도 검토 대상이다."""
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": "안녕하세요"},
            {"validation_failure_reason": "quota_best_effort_fallback"},
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "quota_best_effort_fallback")

    def test_admin_review_required_is_also_honoured(self):
        """지금은 orchestrator 가 항상 False 를 넣지만, 살아나면 자동으로 큐에 오른다."""
        needs, reason = _needs_review_from_pipeline(
            {
                "final_translation": "안녕하세요",
                "admin_review": {"required": True, "reason": "manual_hold"},
            },
            {"validation_failure_reason": None},
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "manual_hold")

    def test_reason_is_truncated(self):
        """last_error 가 1000자로 잘리는 것(job_queue_service.py:256-262)과 같은 상한."""
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": "x"},
            {"validation_failure_reason": "가" * 2000},
        )
        self.assertTrue(needs)
        self.assertEqual(len(reason), 1000)

    def test_no_translation_means_no_review_queue_entry(self):
        """번역문 자체가 없으면 저장 경로를 타지 않는다 — 검토 큐가 아니라 실패다."""
        needs, reason = _needs_review_from_pipeline(
            {"final_translation": None},
            {"validation_failure_reason": "whatever"},
        )
        self.assertFalse(needs)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_translation_review_signal -v
```

Expected: FAIL — `ImportError: cannot import name '_needs_review_from_pipeline'`

- [ ] **Step 3: 판정 함수를 만든다**

`backend/app/services/notice_service.py` 의 모듈 레벨(다른 `_` 헬퍼들 옆)에 추가:

```python
REVIEW_REASON_MAX_LENGTH = 1000


def _needs_review_from_pipeline(
    pipeline_result: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[bool, str | None]:
    """검토 큐에 올릴지와 그 사유.

    번역문이 있으면 validation_status 는 무조건 'passed' 가 된다(아래 저장 블록).
    사용자에게는 그대로 내보내되, 사유가 있으면 검토 큐에도 함께 올린다.

    근거 두 갈래:
      ① metadata.validation_failure_reason — 살아 있는 신호.
         orchestrator.py:444 와 notice_service.py:660 이 실제 값을 넣는다.
      ② pipeline_result.admin_review.required — 지금은 모든 자리에서 리터럴 False 라
         죽어 있지만, 통로는 이미 있다. 살아나면 코드 변경 없이 큐에 오른다.
    """
    if not _optional_str(pipeline_result.get("final_translation")):
        return False, None

    reason = _optional_str(metadata.get("validation_failure_reason"))
    if not reason:
        admin_review = pipeline_result.get("admin_review") or {}
        if isinstance(admin_review, dict) and admin_review.get("required"):
            reason = _optional_str(admin_review.get("reason")) or "admin_review_required"

    if not reason:
        return False, None
    return True, reason[:REVIEW_REASON_MAX_LENGTH]
```

- [ ] **Step 4: 저장 경로에 연결한다**

`_save_translation_result` 의 검증 블록(현재 `:778-787`)을 교체한다:

```python
        needs_review, review_reason = _needs_review_from_pipeline(pipeline_result, metadata)
        if _optional_str(pipeline_result.get("final_translation")):
            validation_status = "passed"
            metadata["validation_status"] = validation_status
            if review_reason:
                LOGGER.warning(
                    "notice translation saved with validation warning: notice_id=%s target_language=%s reason=%s",
                    notice_id,
                    target_language,
                    review_reason,
                    extra={
                        "notice_id": notice_id,
                        "target_language": target_language,
                        "review_reason": review_reason,
                    },
                )
```

그리고 `row` 조립에 두 줄을 추가한다 (`"validation_status": validation_status,` 다음):

```python
            "validation_status": validation_status,
            # 번역문은 그대로 사용자에게 나간다. needs_review 는 «표시» 만 바꾼다.
            "needs_review": needs_review,
            "review_reason": review_reason,
```

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_translation_review_signal -v
```

Expected: PASS (6 tests)

- [ ] **Step 6: 회귀를 확인한다 — 사용자 노출이 바뀌지 않았다**

```bash
PYTHONPATH=backend python -m unittest discover backend/tests
```

Expected: 전부 통과. 특히 `test_notice_api`, `test_notice_service_school_only`, `test_translation_validators`, `test_best_effort_fallback_metadata` 가 통과해야 한다 — `validation_status='passed'` 와 번역문 저장 동작을 건드리지 않았다는 뜻이다.

- [ ] **Step 7: 커밋**

```bash
git add backend/app/services/notice_service.py backend/tests/test_translation_review_signal.py
git commit -m "feat(observability): 번역 검토 신호를 DB 에 기록

안전장치는 동작하는데 출력을 받는 곳이 없었다. 최종 번역문이 있으면
validation_status 가 무조건 'passed' 로 덮어써지고(:778-781), 진짜 사유는
평문 LOGGER.warning 한 줄로만 남아 검색도 집계도 안 됐다.

needs_review / review_reason 을 함께 기록한다. 번역문은 그대로 사용자에게
나가고(현재 동작 유지) 검토 큐에도 올라간다.

판정 근거는 둘이다. metadata.validation_failure_reason 이 살아 있는 신호이고
(orchestrator.py:444, notice_service.py:660), pipeline_result.admin_review.required
는 통로는 있으나 모든 자리에서 리터럴 False 인 죽은 필드다. 둘 다 본다 —
후자가 살아나면 코드 변경 없이 큐에 오른다."
```

- [ ] **Step 8: 신규 번역에 값이 채워지는지 확인한다**

배포 후 공지 1건을 재번역시키고:

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notice_ai_translations?select=notice_id,target_language,validation_status,needs_review,review_reason&order=updated_at.desc&limit=10')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
for row in rows:
    print(row['target_language'], row['validation_status'], row['needs_review'], (row['review_reason'] or '-')[:60])
print('검토 대상:', sum(1 for r in rows if r['needs_review']), '/', len(rows))
"
```

Expected: `validation_status` 는 여전히 전부 `passed`(회귀 없음). `needs_review` 가 `true` 인 행이 0개일 수도 있다 — 그건 최근 번역에 검증 경고가 없었다는 뜻이지 실패가 아니다. Task 16 화면이 이 컬럼을 읽는다.

---

## Task 10: P0-2 잡 큐 콘솔

`scripts/_hambak_jobstatus.py:39-74` 를 대체한다. `job_queue_service.py` 에는 **목록 조회 함수도 통계 함수도 없다** — 조회 계열은 `completed_recently`(:101, 불리언), `latest_job`(:119, 특정 `job_key` 단건), `claim`(:198, 선점 부작용 포함) 셋뿐이다. 콘솔용 조회를 Next.js 쪽에 새로 만든다.

`app_jobs` 는 RLS 활성 + 정책 0개(`0036`)라 브라우저 Supabase 클라이언트로는 **아예 못 읽는다.** service_role 경유는 선택이 아니라 제약이다.

**Files:**
- Create: `lib/admin/jobs.ts`
- Create: `app/api/admin/jobs/route.ts`
- Create: `app/api/admin/jobs/[jobId]/route.ts`
- Create: `app/(admin)/admin/(protected)/jobs/page.tsx`
- Create: `app/(admin)/admin/(protected)/jobs/JobActions.tsx`

**Interfaces:**
- Consumes: Task 3 의 `app_jobs` 타입, Task 4 의 `requireAdminSession` / `writeAdminAudit`
- Produces:
  - `listAppJobs(filter?: { jobType?: string; status?: AppJobStatus; limit?: number }): Promise<AppJobRow[]>`
  - `countAppJobsByStatus(): Promise<Record<AppJobStatus, number>>`
  - `retryAppJob(jobId: string): Promise<{ ok: true; job: AppJobRow } | { ok: false; error: string }>`
  - `abandonAppJob(jobId: string): Promise<{ ok: true; job: AppJobRow } | { ok: false; error: string }>`
  - `GET /api/admin/jobs?job_type=&status=` → `{ ok, jobs, counts }`
  - `POST /api/admin/jobs/{jobId}` `{ action: 'retry' | 'abandon' }`

- [ ] **Step 1: 조회·조작 라이브러리를 쓴다**

`lib/admin/jobs.ts`:

```typescript
import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import type { AppJobStatus, Database } from '@/types/database'

export type AppJobRow = Database['public']['Tables']['app_jobs']['Row']

const JOB_COLUMNS =
  'id,job_type,job_key,status,attempts,max_attempts,available_at,started_at,finished_at,last_error,result,payload,created_at,updated_at'

/** 운영 실측 app_jobs 230행. 페이징을 만들지 않는다 — 필터와 정렬로 충분하다.
 *  0027:19-20 의 인덱스(job_type, status, available_at, created_at)가 이 형태를 지원한다. */
const DEFAULT_LIMIT = 300

export interface JobListFilter {
  jobType?: string
  status?: AppJobStatus
  limit?: number
}

export async function listAppJobs(filter: JobListFilter = {}): Promise<AppJobRow[]> {
  const service = createSupabaseServiceClient()
  let query = service
    .from('app_jobs')
    .select(JOB_COLUMNS)
    .order('created_at', { ascending: false })
    .limit(filter.limit ?? DEFAULT_LIMIT)
  if (filter.jobType) query = query.eq('job_type', filter.jobType)
  if (filter.status) query = query.eq('status', filter.status)

  const { data, error } = await query
  if (error) throw new Error(`잡 목록 조회 실패: ${error.message}`)
  return (data ?? []) as AppJobRow[]
}

export async function countAppJobsByStatus(): Promise<Record<AppJobStatus, number>> {
  const service = createSupabaseServiceClient()
  const statuses: AppJobStatus[] = ['queued', 'processing', 'completed', 'failed']
  const counts = { queued: 0, processing: 0, completed: 0, failed: 0 }
  for (const status of statuses) {
    const { count, error } = await service
      .from('app_jobs')
      .select('id', { count: 'exact', head: true })
      .eq('status', status)
    if (error) throw new Error(`잡 상태 집계 실패: ${error.message}`)
    counts[status] = count ?? 0
  }
  return counts
}

/** 재시도. failed 인 잡만 되살린다.
 *
 *  attempts 는 되돌리지 않는다. claim(:198)이 attempts+1 을 하고 fail(:256-)이
 *  attempts < max_attempts 로 재시도 여부를 정하므로, 이미 소진된 잡은 «딱 한 번 더»
 *  돌고 다시 failed 가 된다. 그게 의도한 동작이다 — 무한 재시도를 만들지 않는다.
 *
 *  0027:22-24 의 unique index(job_key where status in ('queued','processing'))가
 *  같은 job_key 로 이미 도는 잡이 있으면 23505 를 낸다. 조용히 삼키지 않고 사유를 돌려준다. */
export async function retryAppJob(
  jobId: string,
): Promise<{ ok: true; job: AppJobRow } | { ok: false; error: string }> {
  const service = createSupabaseServiceClient()
  const now = new Date().toISOString()
  const { data, error } = await service
    .from('app_jobs')
    .update({ status: 'queued', available_at: now, last_error: null, updated_at: now })
    .eq('id', jobId)
    .eq('status', 'failed')
    .select(JOB_COLUMNS)
    .maybeSingle()

  if (error) {
    if (error.code === '23505') {
      return { ok: false, error: 'job_key_already_active' }
    }
    return { ok: false, error: error.message }
  }
  if (!data) return { ok: false, error: 'not_failed_or_not_found' }
  return { ok: true, job: data as AppJobRow }
}

/** 포기. 큐에 남아 워커를 계속 물어뜯는 잡을 끊는다. */
export async function abandonAppJob(
  jobId: string,
): Promise<{ ok: true; job: AppJobRow } | { ok: false; error: string }> {
  const service = createSupabaseServiceClient()
  const now = new Date().toISOString()
  const { data, error } = await service
    .from('app_jobs')
    .update({ status: 'failed', finished_at: now, updated_at: now })
    .eq('id', jobId)
    .in('status', ['queued', 'processing'])
    .select(JOB_COLUMNS)
    .maybeSingle()

  if (error) return { ok: false, error: error.message }
  if (!data) return { ok: false, error: 'not_active_or_not_found' }
  return { ok: true, job: data as AppJobRow }
}
```

- [ ] **Step 2: API 라우트를 쓴다**

`app/api/admin/jobs/route.ts`:

```typescript
import { NextResponse, type NextRequest } from 'next/server'
import { requireAdminSession } from '@/lib/admin/session'
import { countAppJobsByStatus, listAppJobs } from '@/lib/admin/jobs'
import type { AppJobStatus } from '@/types/database'

const STATUSES = new Set<AppJobStatus>(['queued', 'processing', 'completed', 'failed'])

export async function GET(request: NextRequest) {
  // 이중 방어 ②. middleware 는 쿠키 존재만 봤다.
  try {
    await requireAdminSession()
  } catch {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const params = request.nextUrl.searchParams
  const statusParam = params.get('status')
  const status = statusParam && STATUSES.has(statusParam as AppJobStatus)
    ? (statusParam as AppJobStatus)
    : undefined

  const [jobs, counts] = await Promise.all([
    listAppJobs({ jobType: params.get('job_type') ?? undefined, status }),
    countAppJobsByStatus(),
  ])
  return NextResponse.json({ ok: true, jobs, counts })
}
```

`app/api/admin/jobs/[jobId]/route.ts`:

```typescript
import { NextResponse, type NextRequest } from 'next/server'
import { requireAdminSession, writeAdminAudit } from '@/lib/admin/session'
import { abandonAppJob, retryAppJob } from '@/lib/admin/jobs'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  let session
  try {
    session = await requireAdminSession()
  } catch {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const { jobId } = await params
  const body = await request.json().catch(() => null)
  const action = body?.action

  if (action !== 'retry' && action !== 'abandon') {
    return NextResponse.json({ ok: false, error: 'unknown_action' }, { status: 400 })
  }

  const result = action === 'retry' ? await retryAppJob(jobId) : await abandonAppJob(jobId)
  await writeAdminAudit(session, `job_${action}`, jobId, {
    ok: result.ok,
    detail: result.ok ? result.job.job_key : result.error,
  })

  if (!result.ok) {
    return NextResponse.json({ ok: false, error: result.error }, { status: 409 })
  }
  return NextResponse.json({ ok: true, job: result.job })
}
```

- [ ] **Step 3: 화면을 쓴다**

`app/(admin)/admin/(protected)/jobs/JobActions.tsx`:

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function JobActions({ jobId, status }: { jobId: string; status: string }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function act(action: 'retry' | 'abandon') {
    setBusy(true)
    setError(null)
    const response = await fetch(`/api/admin/jobs/${jobId}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      setError(payload?.error ?? 'failed')
      return
    }
    router.refresh()
  }

  return (
    <div className="flex items-center gap-2">
      {status === 'failed' ? (
        <button disabled={busy} onClick={() => act('retry')} className="underline disabled:opacity-50">
          재시도
        </button>
      ) : null}
      {status === 'queued' || status === 'processing' ? (
        <button disabled={busy} onClick={() => act('abandon')} className="underline disabled:opacity-50">
          포기
        </button>
      ) : null}
      {error ? <span className="text-xs text-rose-400">{error}</span> : null}
    </div>
  )
}
```

`app/(admin)/admin/(protected)/jobs/page.tsx`:

```typescript
import { countAppJobsByStatus, listAppJobs } from '@/lib/admin/jobs'
import { requireAdminSession } from '@/lib/admin/session'
import type { AppJobStatus } from '@/types/database'
import JobActions from './JobActions'

export const dynamic = 'force-dynamic'

const STATUSES: AppJobStatus[] = ['queued', 'processing', 'completed', 'failed']

export default async function AdminJobsPage({
  searchParams,
}: {
  searchParams: Promise<{ job_type?: string; status?: string }>
}) {
  await requireAdminSession()
  const query = await searchParams
  const status = STATUSES.includes(query.status as AppJobStatus)
    ? (query.status as AppJobStatus)
    : undefined

  const [jobs, counts] = await Promise.all([
    listAppJobs({ jobType: query.job_type, status }),
    countAppJobsByStatus(),
  ])

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">잡 큐</h1>

      <div className="flex gap-3 text-sm">
        <a href="/admin/jobs" className="underline">전체</a>
        {STATUSES.map((s) => (
          <a key={s} href={`/admin/jobs?status=${s}`} className="underline">
            {s} ({counts[s]})
          </a>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1100px] text-left text-xs">
          <thead className="text-slate-400">
            <tr>
              <th className="py-1">생성</th>
              <th>job_type</th>
              <th>job_key</th>
              <th>상태</th>
              <th>시도</th>
              <th>available_at</th>
              <th>시작</th>
              <th>종료</th>
              {/* last_error 는 job_queue_service.py:256-262 에서 1000자로 잘려 저장된다.
                  화면도 그 이상을 기대하지 않는다. */}
              <th>last_error</th>
              <th>조작</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="border-t border-slate-800 align-top">
                <td className="py-1 whitespace-nowrap">{job.created_at.slice(0, 19)}</td>
                <td className="whitespace-nowrap">{job.job_type}</td>
                <td className="max-w-[220px] truncate" title={job.job_key}>{job.job_key}</td>
                <td className={job.status === 'failed' ? 'text-rose-400' : ''}>{job.status}</td>
                <td>{job.attempts}/{job.max_attempts}</td>
                <td className="whitespace-nowrap">{job.available_at.slice(0, 19)}</td>
                <td className="whitespace-nowrap">{job.started_at?.slice(0, 19) ?? '-'}</td>
                <td className="whitespace-nowrap">{job.finished_at?.slice(0, 19) ?? '-'}</td>
                <td className="max-w-[320px] whitespace-pre-wrap break-words">{job.last_error ?? '-'}</td>
                <td><JobActions jobId={job.id} status={job.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-500">{jobs.length}건 표시</p>
    </main>
  )
}
```

- [ ] **Step 4: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공

- [ ] **Step 5: 화면 결과가 기존 스크립트와 일치하는지 확인한다**

dev 서버를 띄우고 Step 8(Task 5)에서 만든 관리자 쿠키로:

```bash
curl -s -b /tmp/admin_cookies.txt http://localhost:3000/api/admin/jobs > /tmp/jobs.json
python -c "
import json
d=json.load(open('/tmp/jobs.json',encoding='utf-8'))
print('counts =', d['counts'])
print('반환 건수 =', len(d['jobs']))
print('컬럼 =', sorted(d['jobs'][0].keys()) if d['jobs'] else '(비어 있음)')
"
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
from collections import Counter
r=urllib.request.Request(u+'/rest/v1/app_jobs?select=status&limit=2000')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
print('DB 직접 =', dict(Counter(x['status'] for x in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()))))
"
```

Expected: `counts` 와 `DB 직접` 의 상태별 숫자가 **일치**한다. 컬럼 목록에 `last_error`, `result`, `attempts`, `max_attempts`, `available_at` 이 모두 있다.

- [ ] **Step 6: 재시도가 실제로 워커에 잡히는 상태로 바뀌는지 확인한다**

```bash
FAILED_ID=$(python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/app_jobs?select=id,job_key&status=eq.failed&limit=1')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
print(rows[0]['id'] if rows else '')
")
if [ -n "$FAILED_ID" ]; then
  curl -s -b /tmp/admin_cookies.txt -X POST -H 'content-type: application/json' \
    -d '{"action":"retry"}' "http://localhost:3000/api/admin/jobs/$FAILED_ID" | python -m json.tool
else
  echo "failed 잡이 없다 — 이 확인은 건너뛴다"
fi
```

Expected: `{"ok": true, "job": {... "status": "queued", "last_error": null ...}}`. `failed` 잡이 없으면 건너뛴다.

- [ ] **Step 7: 감사 로그가 남는지 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/admin_audit_log?select=created_at,action,target,detail&order=created_at.desc&limit=5')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
for row in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()):
    print(row['created_at'][:19], row['action'], row['target'], row['detail'])
"
```

Expected: `admin_login` 과 (Step 6 을 돌렸다면) `job_retry` 가 보인다. `admin_user_id` 가 채워져 «누가» 를 알 수 있다.

- [ ] **Step 8: 커밋**

```bash
git add lib/admin/jobs.ts app/api/admin/jobs app/\(admin\)/admin/\(protected\)/jobs
git commit -m "feat(admin): 잡 큐 콘솔 — 조회·재시도·포기

scripts/_hambak_jobstatus.py:39-74 를 대체한다. job_queue_service.py 에는
목록 조회도 통계도 없다(조회 계열이 :101 불리언, :119 단건, :198 선점뿐).
콘솔용 조회를 새로 만든다.

app_jobs 는 RLS 활성 + 정책 0개(0036)라 브라우저 클라이언트로는 못 읽는다.
service_role 경유는 선택이 아니라 제약이다.

재시도는 attempts 를 되돌리지 않는다. claim 이 +1 하고 fail 이
attempts < max_attempts 로 판단하므로 소진된 잡은 딱 한 번 더 돌고 끝난다 —
무한 재시도를 만들지 않는다.

0027:22-24 의 job_key unique index 충돌(23505)을 삼키지 않고 사유를 돌려준다.
페이징은 만들지 않는다 — 운영 실측 230행이다."
```

---

## Task 11: P0-3 학교별 수집 상태

`scripts/probe_school_state.py:67` 과 `scripts/_review_schools.py` 를 대체한다. `crawl_board_kind` 오선택이 **눈에 띄어야** 한다 — `announcement_fallback` 은 «가정통신문 게시판을 못 찾아 일반 공지로 대체», `unknown` 은 «아직 못 정함» 이다.

**Files:**
- Create: `lib/admin/schools.ts`
- Create: `app/(admin)/admin/(protected)/schools/page.tsx`

**Interfaces:**
- Consumes: Task 3 이 보강한 `board_watermarks`, `school_crawl_state` 타입
- Produces:
  - `AdminSchoolRow = { id, name, homepageUrl, crawlBoardUrl, crawlBoardKind, crawlStatus, crawlErrorMessage, crawlLastCheckedAt, watermarkBoards, noticeCount, pendingNoticeCount }`
  - `listAdminSchools(): Promise<AdminSchoolRow[]>`

- [ ] **Step 1: 조회 라이브러리를 쓴다**

`lib/admin/schools.ts`:

```typescript
import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import type { Json, SchoolCrawlBoardKind } from '@/types/database'

export interface AdminSchoolRow {
  id: string
  name: string
  homepageUrl: string | null
  crawlBoardUrl: string | null
  crawlBoardKind: SchoolCrawlBoardKind
  crawlStatus: string
  crawlErrorMessage: string | null
  crawlLastCheckedAt: string | null
  watermarkBoards: number
  noticeCount: number
  pendingNoticeCount: number
}

/** 운영 실측 schools 8 / notices 38. 집계를 SQL 뷰로 만들지 않는다 —
 *  세 번의 전체 조회가 그 규모에서 더 싸고 되돌리기도 쉽다. */
export async function listAdminSchools(): Promise<AdminSchoolRow[]> {
  const service = createSupabaseServiceClient()

  const [schools, states, notices] = await Promise.all([
    service.from('schools').select('id,name,homepage_url').order('name'),
    service
      .from('school_crawl_state')
      .select(
        'school_id,crawl_board_url,crawl_board_kind,crawl_status,crawl_error_message,crawl_last_checked_at,board_watermarks',
      ),
    service.from('notices').select('id,school_id,status'),
  ])

  if (schools.error) throw new Error(`학교 목록 조회 실패: ${schools.error.message}`)
  if (states.error) throw new Error(`수집 상태 조회 실패: ${states.error.message}`)
  if (notices.error) throw new Error(`공지 수 조회 실패: ${notices.error.message}`)

  const stateBySchool = new Map((states.data ?? []).map((s) => [s.school_id, s]))
  const total = new Map<string, number>()
  const pending = new Map<string, number>()
  for (const notice of notices.data ?? []) {
    if (!notice.school_id) continue
    total.set(notice.school_id, (total.get(notice.school_id) ?? 0) + 1)
    if (notice.status === 'pending') {
      pending.set(notice.school_id, (pending.get(notice.school_id) ?? 0) + 1)
    }
  }

  return (schools.data ?? []).map((school) => {
    const state = stateBySchool.get(school.id)
    const watermarks = (state?.board_watermarks ?? {}) as Record<string, Json>
    return {
      id: school.id,
      name: school.name,
      homepageUrl: school.homepage_url,
      crawlBoardUrl: state?.crawl_board_url ?? null,
      crawlBoardKind: (state?.crawl_board_kind ?? 'unknown') as SchoolCrawlBoardKind,
      crawlStatus: state?.crawl_status ?? 'pending',
      crawlErrorMessage: state?.crawl_error_message ?? null,
      crawlLastCheckedAt: state?.crawl_last_checked_at ?? null,
      watermarkBoards: Object.keys(watermarks).length,
      noticeCount: total.get(school.id) ?? 0,
      pendingNoticeCount: pending.get(school.id) ?? 0,
    }
  })
}
```

- [ ] **Step 2: 화면을 쓴다**

`app/(admin)/admin/(protected)/schools/page.tsx`:

```typescript
import { listAdminSchools } from '@/lib/admin/schools'
import { requireAdminSession } from '@/lib/admin/session'
import type { SchoolCrawlBoardKind } from '@/types/database'

export const dynamic = 'force-dynamic'

/** 0013:23 의 세 값. announcement_fallback 과 unknown 은 «오선택» 이므로 눈에 띄어야 한다.
 *  지금은 scripts/probe_school_state.py:67 이 텍스트로 찍어야만 보인다. */
const BOARD_KIND_BADGE: Record<SchoolCrawlBoardKind, { label: string; className: string }> = {
  family_notice: { label: '가정통신문', className: 'bg-emerald-900 text-emerald-200' },
  announcement_fallback: { label: '일반공지 대체', className: 'bg-amber-900 text-amber-100' },
  unknown: { label: '미정', className: 'bg-rose-900 text-rose-100' },
}

export default async function AdminSchoolsPage() {
  await requireAdminSession()
  const schools = await listAdminSchools()

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">학교별 수집 상태</h1>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1000px] text-left text-xs">
          <thead className="text-slate-400">
            <tr>
              <th className="py-1">학교</th>
              <th>게시판 종류</th>
              <th>게시판 URL</th>
              <th>수집 상태</th>
              <th>마지막 확인</th>
              <th>watermark</th>
              <th>공지</th>
              <th>대기</th>
              <th>오류</th>
            </tr>
          </thead>
          <tbody>
            {schools.map((school) => {
              const badge = BOARD_KIND_BADGE[school.crawlBoardKind]
              return (
                <tr key={school.id} className="border-t border-slate-800 align-top">
                  <td className="py-1">{school.name}</td>
                  <td>
                    <span className={`rounded px-1.5 py-0.5 ${badge.className}`}>{badge.label}</span>
                  </td>
                  <td className="max-w-[280px] truncate" title={school.crawlBoardUrl ?? ''}>
                    {school.crawlBoardUrl ?? '-'}
                  </td>
                  <td>{school.crawlStatus}</td>
                  <td className="whitespace-nowrap">{school.crawlLastCheckedAt?.slice(0, 19) ?? '-'}</td>
                  <td>{school.watermarkBoards}개 게시판</td>
                  <td>{school.noticeCount}</td>
                  <td className={school.pendingNoticeCount > 0 ? 'text-amber-300' : ''}>
                    {school.pendingNoticeCount}
                  </td>
                  <td className="max-w-[240px] whitespace-pre-wrap break-words text-rose-300">
                    {school.crawlErrorMessage ?? '-'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </main>
  )
}
```

- [ ] **Step 3: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공

- [ ] **Step 4: 화면 결과가 기존 스크립트와 일치하는지 확인한다**

```bash
curl -s -b /tmp/admin_cookies.txt -o /tmp/schools.html http://localhost:3000/admin/schools
grep -o "가정통신문\|일반공지 대체\|미정" /tmp/schools.html | sort | uniq -c

python -c "
import json,os,urllib.request
from collections import Counter
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/school_crawl_state?select=crawl_board_kind')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
print('DB 직접 =', dict(Counter(x['crawl_board_kind'] for x in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()))))
"
```

Expected: 화면 배지 개수와 DB 의 `crawl_board_kind` 분포가 일치. `family_notice` → 가정통신문, `announcement_fallback` → 일반공지 대체, `unknown` → 미정

- [ ] **Step 5: 커밋**

```bash
git add lib/admin/schools.ts app/\(admin\)/admin/\(protected\)/schools
git commit -m "feat(admin): 학교별 수집 상태 화면

scripts/probe_school_state.py:67 과 _review_schools.py 를 대체한다.

crawl_board_kind 오선택을 배지로 띄운다. announcement_fallback 은 '가정통신문
게시판을 못 찾아 일반 공지로 대체', unknown 은 '아직 못 정함' 인데 지금은
스크립트로 텍스트를 찍어야만 보인다.

board_watermarks 게시판 수도 함께 보여준다 — Task 3 이 lib 의 select 를
늘린 덕분에 프론트가 처음으로 이 값을 본다.

집계 뷰를 만들지 않는다. 학교 8 / 공지 38 규모에서 전체 조회 세 번이 더 싸다."
```

---

## Task 12: FastAPI `/admin` 라우터 + GCP 제어

프론트에서 GCP Admin API 를 직접 부를 수 없다 — ADC 자격이 브라우저에 없고, 있어서도 안 된다. 이미 `run.jobs.run` 권한을 가진 `naranhi-api` 런타임 SA 쪽에 라우터를 추가하는 편이 권한 확산을 막는다.

`worker_trigger.py:87-108` `_post_run_job` 은 본문이 **리터럴 `json={}`** 이라 `overrides` 를 전혀 쓰지 않는다. 그래서 「공지 1건 강제 재추출」이 지금 수동 gcloud 밖에 방법이 없다. **기존 함수를 확장하지 않고 별도 함수를 만든다** — `trigger_worker_for_job_type` 은 ① 인메모리 디바운스(`:45-54`) ② `except Exception` 으로 실패를 삼킴(`:77-84`) ③ `WORKER_TRIGGER_ENABLED` 가 꺼지면 no-op(`:64-65`) 셋 다 관리자 조작에 부적합하다.

**Files:**
- Create: `backend/app/services/gcp_admin_service.py`
- Create: `backend/app/api/admin.py`
- Create: `backend/tests/test_admin_api.py`
- Modify: `backend/app/core/config.py` (필드 2개)
- Modify: `backend/app/main.py` (라우터 등록)
- Modify: `.github/workflows/deploy-api-cloud-run.yml` (env 1 + secret 1)
- Modify: `.github/workflows/deploy-cloud-run.yml` (secret 1)

**Interfaces:**
- Consumes: 없음 (ADC + Settings)
- Produces:
  - `Settings.admin_api_token: str | None` (`ADMIN_API_TOKEN`), `Settings.scheduler_location: str` (`SCHEDULER_LOCATION`)
  - `CONTROLLABLE_SCHEDULERS: frozenset[str]`, `RUNNABLE_JOBS: frozenset[str]`
  - `list_schedulers() -> list[dict[str, object]]`
  - `pause_scheduler(name: str) -> dict[str, object]` / `resume_scheduler(name: str) -> dict[str, object]`
  - `run_job_with_args(job_name: str, args: list[str]) -> RunResult` — `RunResult(job_name, operation, args)`
  - `GET /admin/schedulers`, `POST /admin/schedulers/{name}/pause|resume`, `POST /admin/jobs/{job_name}/run` — 전부 `Depends(_require_admin_token)`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_admin_api.py`:

```python
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

import app.api.admin as admin_api
import app.services.gcp_admin_service as gcp


def _settings(**over):
    base = dict(
        admin_api_token="secret-token",
        environment="local",
        gcp_project_id="proj",
        gcp_region="asia-northeast3",
        scheduler_location="asia-northeast3",
    )
    base.update(over)
    return type("S", (), base)()


class RequireAdminTokenTest(unittest.TestCase):
    def test_missing_token_is_503_even_in_local(self):
        """crawler.py:25-26 은 토큰 미설정 + local 이면 통과시킨다.
        스케줄러 정지에는 그 fail-open 이 허용될 수 없다."""
        with patch.object(admin_api, "get_settings", return_value=_settings(admin_api_token=None)):
            with self.assertRaises(HTTPException) as ctx:
                admin_api._require_admin_token(x_admin_token="anything")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_absent_header_is_401(self):
        with patch.object(admin_api, "get_settings", return_value=_settings()):
            with self.assertRaises(HTTPException) as ctx:
                admin_api._require_admin_token(x_admin_token=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_is_401(self):
        with patch.object(admin_api, "get_settings", return_value=_settings()):
            with self.assertRaises(HTTPException) as ctx:
                admin_api._require_admin_token(x_admin_token="wrong")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_matching_token_passes(self):
        with patch.object(admin_api, "get_settings", return_value=_settings()):
            self.assertIsNone(admin_api._require_admin_token(x_admin_token="secret-token"))


class RunJobWithArgsTest(unittest.TestCase):
    def test_overrides_are_filled(self):
        """worker_trigger.py:87-108 은 리터럴 json={} 이라 args 를 못 넘긴다.
        그래서 공지 1건 재추출이 수동 gcloud 밖에 방법이 없었다."""
        response = MagicMock(status_code=200)
        response.json.return_value = {"name": "operations/abc"}
        with (
            patch.object(gcp, "get_settings", return_value=_settings()),
            patch.object(gcp, "_authed_headers", return_value={"Authorization": "Bearer x"}),
            patch.object(gcp.httpx, "post", return_value=response) as post,
        ):
            result = gcp.run_job_with_args(
                "naranhi-content-extractor",
                ["--notice-id=n-1", "--force", "--max-notices=1"],
            )
        body = post.call_args.kwargs["json"]
        self.assertEqual(
            body["overrides"]["containerOverrides"][0]["args"],
            ["--notice-id=n-1", "--force", "--max-notices=1"],
        )
        self.assertEqual(result.operation, "operations/abc")

    def test_unlisted_job_is_refused(self):
        with patch.object(gcp, "get_settings", return_value=_settings()):
            with self.assertRaises(PermissionError):
                gcp.run_job_with_args("some-other-job", [])

    def test_failure_propagates_instead_of_returning_false(self):
        """trigger_worker_for_job_type 은 모든 실패를 삼키고 False 를 돌려준다.
        관리자에게는 사유가 그대로 보여야 한다."""
        response = MagicMock(status_code=403, text="permission denied")
        with (
            patch.object(gcp, "get_settings", return_value=_settings()),
            patch.object(gcp, "_authed_headers", return_value={}),
            patch.object(gcp.httpx, "post", return_value=response),
        ):
            with self.assertRaises(RuntimeError):
                gcp.run_job_with_args("naranhi-content-extractor", [])


class SchedulerWhitelistTest(unittest.TestCase):
    def test_unlisted_scheduler_is_refused(self):
        with patch.object(gcp, "get_settings", return_value=_settings()):
            with self.assertRaises(PermissionError):
                gcp.pause_scheduler("someone-elses-job")

    def test_listed_scheduler_calls_pause_endpoint(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"state": "PAUSED", "schedule": "0 6 * * *"}
        name = sorted(gcp.CONTROLLABLE_SCHEDULERS)[0]
        with (
            patch.object(gcp, "get_settings", return_value=_settings()),
            patch.object(gcp, "_authed_headers", return_value={}),
            patch.object(gcp.httpx, "post", return_value=response) as post,
        ):
            result = gcp.pause_scheduler(name)
        self.assertIn(f"jobs/{name}:pause", post.call_args.args[0])
        self.assertEqual(result["state"], "PAUSED")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_admin_api -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.admin'`

- [ ] **Step 3: Settings 필드를 추가한다**

`backend/app/core/config.py` 의 `crawler_worker_job_name` 선언 아래에:

```python
    # 관리자 콘솔 전용 토큰. crawler_internal_token 과 분리한다 —
    # 그쪽은 토큰 미설정 + local 이면 통과하는 fail-open 분기가 있다(crawler.py:25-26).
    admin_api_token: str | None = Field(default=None, alias="ADMIN_API_TOKEN")
    # Cloud Scheduler 잡의 location. Cloud Run region 과 같은지 미확인이므로
    # 별도 값으로 둔다. 비어 있으면 gcp_region 으로 폴백한다.
    scheduler_location: str = Field(default="", alias="SCHEDULER_LOCATION")
```

- [ ] **Step 4: GCP 제어 서비스를 쓴다**

`backend/app/services/gcp_admin_service.py`:

```python
"""Cloud Scheduler 조회·정지·재개 + Cloud Run Job 인자 지정 실행.

worker_trigger.trigger_worker_for_job_type 을 재사용하지 않는 이유 셋:
  ① 인메모리 디바운스(worker_trigger.py:45-54) — 관리자가 누른 버튼이 조용히
     무시되면 안 된다.
  ② except Exception 으로 모든 실패를 삼키고 False 를 돌려준다(:77-84) —
     관리자에게는 실패 사유가 그대로 보여야 한다.
  ③ WORKER_TRIGGER_ENABLED 가 꺼져 있으면 no-op(:64-65) — 관리자 조작은
     이 스위치와 무관해야 한다.

여기 있는 함수는 디바운스 없음 / 예외 전파 / overrides 채움이다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

LOGGER = logging.getLogger(__name__)

_RUN_API_BASE = "https://run.googleapis.com/v2"
_SCHEDULER_API_BASE = "https://cloudscheduler.googleapis.com/v1"
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_TIMEOUT_SECONDS = 20.0

# ⚠️ 화이트리스트를 코드 상수로 고정한다. 조작 가능한 이름을 API 인자로 자유롭게
#    받으면 관리자 콘솔이 GCP 프로젝트 전체의 조작 창구가 된다.
#
#    아래 이름은 docs/scheduled-crawl-runbook.md:64-67 의 생성 명령에서 가져왔다.
#    실운영 이름이 문서와 어긋난다고 보고된 바 있으므로(스펙 §6.4), Step 9 에서
#    GET /admin/schedulers 응답과 대조해 확정한다.
CONTROLLABLE_SCHEDULERS = frozenset(
    {
        "naranhi-school-crawler-0600",
        "naranhi-school-crawler-1800",
        "naranhi-content-extractor-0700",
        "naranhi-content-extractor-1900",
    }
)

# 인자 지정 실행을 허용하는 Job. 워커 Job(translation/crawler)은 넣지 않는다 —
# 그쪽은 큐가 깨우는 것이지 사람이 인자를 넣어 부르는 대상이 아니다.
RUNNABLE_JOBS = frozenset(
    {
        "naranhi-content-extractor",
        "naranhi-school-crawler",
    }
)


@dataclass(frozen=True)
class RunResult:
    job_name: str
    operation: str
    args: list[str]

    def to_dict(self) -> dict[str, object]:
        return {"job_name": self.job_name, "operation": self.operation, "args": self.args}


def _authed_headers() -> dict[str, str]:
    import google.auth
    from google.auth.transport.requests import Request as AuthRequest

    credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    credentials.refresh(AuthRequest())
    return {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }


def _scheduler_parent() -> str:
    settings = get_settings()
    location = (settings.scheduler_location or settings.gcp_region or "").strip()
    if not settings.gcp_project_id or not location:
        raise RuntimeError("GCP_PROJECT_ID / SCHEDULER_LOCATION 이 설정되지 않았습니다.")
    return f"projects/{settings.gcp_project_id}/locations/{location}"


def _raise_for_status(response: httpx.Response, label: str) -> None:
    if response.status_code >= 300:
        raise RuntimeError(f"{label} returned {response.status_code}: {response.text[:300]}")


def _short_name(full_name: str) -> str:
    return (full_name or "").rsplit("/", 1)[-1]


def list_schedulers() -> list[dict[str, object]]:
    """문서가 아니라 API 가 돌려준 실제 cron 과 state 를 보여준다.
    문서(scheduled-crawl-runbook.md:64-65)와 실운영이 이미 어긋나 있다."""
    response = httpx.get(
        f"{_SCHEDULER_API_BASE}/{_scheduler_parent()}/jobs",
        headers=_authed_headers(),
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_status(response, "cloudscheduler.jobs.list")
    jobs = response.json().get("jobs") or []
    result = []
    for job in jobs:
        name = _short_name(job.get("name") or "")
        result.append(
            {
                "name": name,
                "schedule": job.get("schedule"),
                "time_zone": job.get("timeZone"),
                "state": job.get("state"),
                "last_attempt_time": job.get("lastAttemptTime"),
                "controllable": name in CONTROLLABLE_SCHEDULERS,
            }
        )
    return result


def pause_scheduler(name: str) -> dict[str, object]:
    return _scheduler_action(name, "pause")


def resume_scheduler(name: str) -> dict[str, object]:
    return _scheduler_action(name, "resume")


def _scheduler_action(name: str, action: str) -> dict[str, object]:
    if name not in CONTROLLABLE_SCHEDULERS:
        raise PermissionError(f"조작 대상이 아닌 스케줄러입니다: {name}")
    response = httpx.post(
        f"{_SCHEDULER_API_BASE}/{_scheduler_parent()}/jobs/{name}:{action}",
        headers=_authed_headers(),
        json={},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_status(response, f"cloudscheduler.jobs.{action}")
    body = response.json()
    LOGGER.info(
        "scheduler %s: name=%s state=%s",
        action,
        name,
        body.get("state"),
        extra={"scheduler_name": name, "scheduler_action": action},
    )
    return {"name": name, "state": body.get("state"), "schedule": body.get("schedule")}


def run_job_with_args(job_name: str, args: list[str]) -> RunResult:
    """Cloud Run Job 을 args overrides 로 1회 실행한다.

    worker_trigger.py:87-108 은 리터럴 json={} 이라 배포 시점에 고정된 --args 로만
    돈다. 그래서 「공지 1건 강제 재추출」이 수동 gcloud 밖에 방법이 없었다
    (docs/content-extractor-job.md:137-141).
    """
    if job_name not in RUNNABLE_JOBS:
        raise PermissionError(f"실행 대상이 아닌 Job 입니다: {job_name}")
    settings = get_settings()
    if not settings.gcp_project_id or not settings.gcp_region:
        raise RuntimeError("GCP_PROJECT_ID / GCP_REGION 이 설정되지 않았습니다.")

    url = (
        f"{_RUN_API_BASE}/projects/{settings.gcp_project_id}"
        f"/locations/{settings.gcp_region}/jobs/{job_name}:run"
    )
    response = httpx.post(
        url,
        headers=_authed_headers(),
        json={"overrides": {"containerOverrides": [{"args": list(args)}]}},
        timeout=_TIMEOUT_SECONDS,
    )
    _raise_for_status(response, "run.jobs.run")
    operation = str(response.json().get("name") or "")
    LOGGER.info(
        "cloud run job started: job=%s operation=%s",
        job_name,
        operation,
        extra={"job_name": job_name, "operation": operation},
    )
    return RunResult(job_name=job_name, operation=operation, args=list(args))
```

- [ ] **Step 5: FastAPI 라우터를 쓴다**

`backend/app/api/admin.py`:

```python
"""관리자 전용 GCP 제어 라우터. 호출자는 Next.js 서버뿐이다.

crawler.py 의 _require_internal_token 을 재사용하지 않는다 — 그쪽은 토큰 미설정 +
ENVIRONMENT=local 이면 return 으로 통과시킨다(:25-26). 크롤 트리거에는 편의지만
스케줄러 정지·Job 강제 실행에는 허용될 수 없는 fail-open 이다.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.services.gcp_admin_service import (
    list_schedulers,
    pause_scheduler,
    resume_scheduler,
    run_job_with_args,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


def _require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = (get_settings().admin_api_token or "").strip()
    if not expected:
        # local 예외를 두지 않는다. 토큰이 없으면 환경 불문 잠긴다.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_TOKEN is required.",
        )
    provided = (x_admin_token or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
        )


def _wrap(operation, label: str):
    try:
        return operation()
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RuntimeError as exc:
        LOGGER.warning("%s failed: %s", label, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/schedulers", dependencies=[Depends(_require_admin_token)])
async def get_schedulers() -> dict[str, object]:
    return {"ok": True, "jobs": _wrap(list_schedulers, "list_schedulers")}


@router.post("/schedulers/{name}/pause", dependencies=[Depends(_require_admin_token)])
async def post_scheduler_pause(name: str) -> dict[str, object]:
    return {"ok": True, "job": _wrap(lambda: pause_scheduler(name), "pause_scheduler")}


@router.post("/schedulers/{name}/resume", dependencies=[Depends(_require_admin_token)])
async def post_scheduler_resume(name: str) -> dict[str, object]:
    return {"ok": True, "job": _wrap(lambda: resume_scheduler(name), "resume_scheduler")}


@router.post("/jobs/{job_name}/run", dependencies=[Depends(_require_admin_token)])
async def post_job_run(
    job_name: str,
    args: list[str] = Body(default_factory=list, embed=True),
) -> dict[str, object]:
    result = _wrap(lambda: run_job_with_args(job_name, args), "run_job_with_args")
    return {"ok": True, **result.to_dict()}
```

- [ ] **Step 6: 라우터를 등록한다**

`backend/app/main.py` 의 import 에 한 줄:

```python
from app.api.admin import router as admin_router
```

그리고 `include_router` 블록에 한 줄:

```python
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
```

- [ ] **Step 7: 테스트 통과를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_admin_api -v
PYTHONPATH=backend python -m unittest discover backend/tests
```

Expected: `test_admin_api` 9 tests PASS, 전체도 통과

- [ ] **Step 8: 토큰을 만들어 Secret Manager 에 넣는다**

```bash
TOKENFILE="$(mktemp)"
python -c "import secrets;open('$TOKENFILE','w').write(secrets.token_urlsafe(48))"
python -c "print('토큰 길이:', len(open('$TOKENFILE').read()), '자')"
gcloud secrets create admin-api-token --data-file="$TOKENFILE" \
  || gcloud secrets versions add admin-api-token --data-file="$TOKENFILE"
rm -f "$TOKENFILE"
gcloud secrets versions list admin-api-token --limit=1
```

Expected: `토큰 길이: 64자` 근처 + 시크릿 버전 1개. **값은 화면에 찍히지 않는다.**

- [ ] **Step 9: 스케줄러 커스텀 역할을 만들고 부여한다**

```bash
PROJECT_ID="$(gh variable get GCP_PROJECT_ID)"
API_SA="$(gcloud run services describe naranhi-api --region="$(gh variable get GCP_REGION)" \
  --format='value(spec.template.spec.serviceAccountName)')"
echo "API 런타임 SA: $API_SA"

gcloud iam roles create naranhiSchedulerOperator --project="$PROJECT_ID" \
  --title="Naranhi Scheduler Operator" \
  --description="관리자 콘솔이 정기 크롤 스케줄러를 보고 멈추고 되살리는 데만 쓴다" \
  --permissions=cloudscheduler.jobs.list,cloudscheduler.jobs.get,cloudscheduler.jobs.pause,cloudscheduler.jobs.resume \
  --stage=GA

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$API_SA" \
  --role="projects/$PROJECT_ID/roles/naranhiSchedulerOperator" \
  --condition=None
```

Expected: 역할 생성 + 바인딩 완료. **`roles/cloudscheduler.admin` 을 쓰지 않는다** — 그것은 생성·삭제까지 준다.

- [ ] **Step 10: 배포 워크플로에 env·secret 을 넣는다**

`.github/workflows/deploy-api-cloud-run.yml` 의 `env_vars:` 블록에 한 줄 추가:

```yaml
            SCHEDULER_LOCATION=${{ vars.GCP_SCHEDULER_LOCATION }}
```

같은 스텝의 `secrets:` 블록에 한 줄 추가:

```yaml
            ADMIN_API_TOKEN=admin-api-token:latest
```

`.github/workflows/deploy-cloud-run.yml`(웹)의 `secrets:` 블록에도 한 줄 추가 — Next.js 서버가 이 토큰으로 FastAPI 를 부른다:

```yaml
            ADMIN_API_TOKEN=admin-api-token:latest
```

> **env 인라인 금지.** `env_vars:` 가 아니라 `secrets:` 에 넣는다. env 로 넣으면 `gcloud run services describe` 로 값이 그대로 보인다 (`docs/content-extractor-job.md:79` 가 같은 이유로 경고한다).
>
> **선행 작업**: GitHub Variable `GCP_SCHEDULER_LOCATION` 을 만든다. 값은 Step 12 에서 확정한다 — 지금은 `gcloud scheduler jobs list --location=asia-northeast3` 이 결과를 내면 `asia-northeast3`, 아니면 `--location` 을 바꿔가며 찾는다.

- [ ] **Step 11: 커밋**

```bash
git add backend/app/api/admin.py backend/app/services/gcp_admin_service.py \
        backend/tests/test_admin_api.py backend/app/core/config.py backend/app/main.py \
        .github/workflows/deploy-api-cloud-run.yml .github/workflows/deploy-cloud-run.yml
git commit -m "feat(admin): FastAPI /admin 라우터 — 스케줄러 제어와 인자 지정 Job 실행

GCP 제어만 백엔드에 둔다. ADC 자격이 브라우저에 없고 있어서도 안 되며,
이미 run.jobs.run 권한을 가진 naranhi-api SA 쪽에 라우터를 얹는 편이
권한 확산이 적다. 조회는 Next.js 가 service_role 로 직접 한다.

_require_internal_token 을 재사용하지 않는다. 그쪽은 토큰 미설정 + local 이면
통과시킨다(crawler.py:25-26). 새 _require_admin_token 은 local 예외 없이
토큰이 없으면 환경 불문 503 이다.

run_job_with_args 를 새로 만든다. worker_trigger._post_run_job 은 리터럴
json={} 이라 overrides 를 못 쓰고, 디바운스·예외 삼킴·WORKER_TRIGGER_ENABLED
no-op 셋 다 관리자 조작에 부적합하다. 새 함수는 디바운스 없음 / 예외 전파 /
overrides 채움 / operation 반환이다.

조작 대상 스케줄러와 Job 이름을 코드 상수 화이트리스트로 고정한다 — 안 그러면
콘솔이 GCP 프로젝트 전체의 조작 창구가 된다.

토큰은 Secret Manager 로만 주입한다. env 인라인은 describe 로 값이 보인다."
```

- [ ] **Step 12: 배포 후 실제 스케줄러 이름·location 을 확정한다**

```bash
TOKENFILE="$(mktemp)"
gcloud secrets versions access latest --secret=admin-api-token > "$TOKENFILE"
API="$(gh variable get NEXT_PUBLIC_API_BASE_URL)"

echo "--- 토큰 없이 (스펙 §12.1 #8) ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" "$API/admin/schedulers"

echo "--- 토큰 헤더로 ---"
curl -s -H "X-Admin-Token: $(cat "$TOKENFILE")" "$API/admin/schedulers" | python -m json.tool
rm -f "$TOKENFILE"
```

Expected:
- 토큰 없이 **`HTTP 401`** (토큰은 설정돼 있으므로 503 이 아니라 401). **`200` 이 나오면 fail-open 이 재발한 것이다 — 즉시 중단하고 보고할 것.**
- 토큰으로는 스케줄러 목록. 각 항목에 `name` / `schedule` / `state` / `controllable`.

**여기서 확정해야 할 두 가지:**
1. 목록에 나온 실제 이름이 `CONTROLLABLE_SCHEDULERS` 상수와 일치하는가. **다르면 상수를 실제 이름으로 고치고 별도 커밋한다.** `controllable: false` 인 항목이 정기 크롤/추출 잡이라면 그게 바로 그 경우다.
2. `_scheduler_parent()` 가 쓴 location 이 맞는가. 목록이 비어 있으면 `GCP_SCHEDULER_LOCATION` 이 틀렸다는 뜻이다.

```bash
# 상수를 고쳤다면
git add backend/app/services/gcp_admin_service.py
git commit -m "fix(admin): 스케줄러 화이트리스트를 실운영 이름으로 확정

docs/scheduled-crawl-runbook.md:64-67 의 생성 명령과 실제 이름이 달랐다.
GET /admin/schedulers 응답을 근거로 상수를 고친다."
```

---

## Task 13: P1-1 스케줄러 정지/재개

`gcloud scheduler jobs pause` / `resume` 가 **저장소 전체에 0건**이다. 문서는 `create` 만 적어 두었는데 **실제로 지금 5개가 PAUSED** 다. 되살리는 방법이 사람 기억에만 있다. 이 화면이 절차를 코드로 만든다.

**Files:**
- Create: `lib/admin/gcp.ts`
- Create: `app/api/admin/schedulers/route.ts`
- Create: `app/api/admin/schedulers/[name]/route.ts`
- Create: `app/(admin)/admin/(protected)/schedulers/page.tsx`
- Create: `app/(admin)/admin/(protected)/schedulers/SchedulerActions.tsx`
- Modify: `app/(admin)/admin/(protected)/page.tsx` (PAUSED 배지 + 마지막 성공 실행 시각)

**Interfaces:**
- Consumes: Task 12 의 FastAPI `/admin/schedulers*`, Task 8 의 `crawl_run_history`
- Produces:
  - `AdminApiError extends Error { status: number }`
  - `listSchedulers(): Promise<SchedulerJob[]>` — `SchedulerJob = { name, schedule, timeZone, state, lastAttemptTime, controllable }`
  - `setSchedulerState(name: string, action: 'pause' | 'resume'): Promise<SchedulerJob>`
  - `runAdminJob(jobName: string, args: string[]): Promise<{ operation: string }>` (Task 15 가 쓴다)
  - `GET /api/admin/schedulers`, `POST /api/admin/schedulers/{name}` `{action}`

- [ ] **Step 1: FastAPI 호출 라이브러리를 쓴다**

`lib/admin/gcp.ts`:

```typescript
import 'server-only'

const ADMIN_API_TIMEOUT_MS = 20_000

export class AdminApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'AdminApiError'
  }
}

export interface SchedulerJob {
  name: string
  schedule: string | null
  timeZone: string | null
  state: string | null
  lastAttemptTime: string | null
  controllable: boolean
}

/** ADMIN_API_TOKEN 은 브라우저에 절대 내려가지 않는다.
 *  이 파일은 server-only 이고, 클라이언트 컴포넌트에서 FastAPI /admin/* 를
 *  직접 부르는 코드를 만들지 않는다. */
async function callAdminApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/+$/, '')
  if (!base) throw new AdminApiError('NEXT_PUBLIC_API_BASE_URL 이 설정되지 않았습니다.', 503)
  const token = process.env.ADMIN_API_TOKEN?.trim()
  if (!token) throw new AdminApiError('ADMIN_API_TOKEN 이 설정되지 않았습니다.', 503)

  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      'X-Admin-Token': token,
      'content-type': 'application/json',
    },
    cache: 'no-store',
    signal: AbortSignal.timeout(ADMIN_API_TIMEOUT_MS),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload?.ok) {
    throw new AdminApiError(payload?.detail ?? `admin api ${response.status}`, response.status)
  }
  return payload as T
}

interface RawSchedulerJob {
  name: string
  schedule: string | null
  time_zone: string | null
  state: string | null
  last_attempt_time: string | null
  controllable: boolean
}

function toSchedulerJob(raw: RawSchedulerJob): SchedulerJob {
  return {
    name: raw.name,
    schedule: raw.schedule,
    timeZone: raw.time_zone,
    state: raw.state,
    lastAttemptTime: raw.last_attempt_time,
    controllable: raw.controllable,
  }
}

export async function listSchedulers(): Promise<SchedulerJob[]> {
  const payload = await callAdminApi<{ jobs: RawSchedulerJob[] }>('/admin/schedulers')
  return payload.jobs.map(toSchedulerJob)
}

export async function setSchedulerState(
  name: string,
  action: 'pause' | 'resume',
): Promise<SchedulerJob> {
  const payload = await callAdminApi<{ job: RawSchedulerJob }>(
    `/admin/schedulers/${encodeURIComponent(name)}/${action}`,
    { method: 'POST' },
  )
  return toSchedulerJob({ ...payload.job, time_zone: null, last_attempt_time: null, controllable: true })
}

export async function runAdminJob(
  jobName: string,
  args: string[],
): Promise<{ operation: string }> {
  const payload = await callAdminApi<{ operation: string }>(
    `/admin/jobs/${encodeURIComponent(jobName)}/run`,
    { method: 'POST', body: JSON.stringify({ args }) },
  )
  return { operation: payload.operation }
}
```

- [ ] **Step 2: API 라우트를 쓴다**

`app/api/admin/schedulers/route.ts`:

```typescript
import { NextResponse } from 'next/server'
import { requireAdminSession } from '@/lib/admin/session'
import { AdminApiError, listSchedulers } from '@/lib/admin/gcp'

export async function GET() {
  try {
    await requireAdminSession()
  } catch {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }
  try {
    return NextResponse.json({ ok: true, jobs: await listSchedulers() })
  } catch (error) {
    const status = error instanceof AdminApiError ? error.status : 502
    return NextResponse.json({ ok: false, error: String(error) }, { status })
  }
}
```

`app/api/admin/schedulers/[name]/route.ts`:

```typescript
import { NextResponse, type NextRequest } from 'next/server'
import { requireAdminSession, writeAdminAudit } from '@/lib/admin/session'
import { AdminApiError, setSchedulerState } from '@/lib/admin/gcp'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  let session
  try {
    session = await requireAdminSession()
  } catch {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const { name } = await params
  const body = await request.json().catch(() => null)
  const action = body?.action
  if (action !== 'pause' && action !== 'resume') {
    return NextResponse.json({ ok: false, error: 'unknown_action' }, { status: 400 })
  }

  try {
    const job = await setSchedulerState(name, action)
    // 정지는 수집을 조용히 멈춘다. 누가 언제 눌렀는지가 남아야 한다.
    await writeAdminAudit(session, `scheduler_${action}`, name, { state: job.state })
    return NextResponse.json({ ok: true, job })
  } catch (error) {
    await writeAdminAudit(session, `scheduler_${action}_failed`, name, { error: String(error) })
    const status = error instanceof AdminApiError ? error.status : 502
    return NextResponse.json({ ok: false, error: String(error) }, { status })
  }
}
```

- [ ] **Step 3: 화면을 쓴다**

`app/(admin)/admin/(protected)/schedulers/SchedulerActions.tsx`:

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function SchedulerActions({
  name,
  state,
  controllable,
}: {
  name: string
  state: string | null
  controllable: boolean
}) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!controllable) {
    return <span className="text-xs text-slate-500">화이트리스트 밖</span>
  }

  const action = state === 'PAUSED' ? 'resume' : 'pause'
  const label = action === 'resume' ? '재개' : '정지'

  async function run() {
    // 정지는 수집을 조용히 멈춘다. 되돌릴 수 있지만 그동안 아무도 모른다.
    if (action === 'pause' && !confirm(`${name} 을(를) 정지합니다.\n정지 중에는 수집이 멈추고 알림이 오지 않습니다.`)) {
      return
    }
    setBusy(true)
    setError(null)
    const response = await fetch(`/api/admin/schedulers/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      setError(payload?.error ?? 'failed')
      return
    }
    router.refresh()
  }

  return (
    <div className="flex items-center gap-2">
      <button disabled={busy} onClick={run} className="underline disabled:opacity-50">
        {busy ? '처리 중…' : label}
      </button>
      {error ? <span className="text-xs text-rose-400">{error}</span> : null}
    </div>
  )
}
```

`app/(admin)/admin/(protected)/schedulers/page.tsx`:

```typescript
import { requireAdminSession } from '@/lib/admin/session'
import { listSchedulers } from '@/lib/admin/gcp'
import SchedulerActions from './SchedulerActions'

export const dynamic = 'force-dynamic'

export default async function AdminSchedulersPage() {
  await requireAdminSession()

  let jobs
  let error: string | null = null
  try {
    jobs = await listSchedulers()
  } catch (caught) {
    jobs = []
    error = String(caught)
  }

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">스케줄러</h1>
      {/* 문서가 아니라 Cloud Scheduler API 가 돌려준 실제 cron 과 state 를 보여준다.
          문서(docs/기능명세서.md:154)는 '평일 06:30/18:00' 이라 적었지만 실제는
          요일 제한 없는 매일 06:00/18:00 이다. 화면은 드러내기만 한다. */}
      <p className="text-xs text-slate-500">
        Cloud Scheduler API 가 돌려준 실제 값이다. 문서에 적힌 시각과 다를 수 있다.
      </p>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[840px] text-left text-xs">
          <thead className="text-slate-400">
            <tr>
              <th className="py-1">이름</th>
              <th>cron</th>
              <th>시간대</th>
              <th>상태</th>
              <th>마지막 시도</th>
              <th>조작</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.name} className="border-t border-slate-800">
                <td className="py-1">{job.name}</td>
                <td className="font-mono">{job.schedule ?? '-'}</td>
                <td>{job.timeZone ?? '-'}</td>
                <td className={job.state === 'PAUSED' ? 'text-rose-400 font-semibold' : 'text-emerald-300'}>
                  {job.state ?? '-'}
                </td>
                <td className="whitespace-nowrap">{job.lastAttemptTime?.slice(0, 19) ?? '-'}</td>
                <td>
                  <SchedulerActions name={job.name} state={job.state} controllable={job.controllable} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  )
}
```

- [ ] **Step 4: 대시보드에 «조용한 정지» 경보를 올린다**

`app/(admin)/admin/(protected)/page.tsx` 를 교체한다:

```typescript
import { requireAdminSession } from '@/lib/admin/session'
import { listSchedulers } from '@/lib/admin/gcp'
import { createSupabaseServiceClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

/** 잘못 눌린 pause 로 수집이 조용히 멈추는 것이 이 콘솔의 가장 큰 부작용 위험이다.
 *  지금도 5개가 PAUSED 인데 아무도 알림을 못 받고 있다.
 *  «마지막 성공 실행 시각» 과 PAUSED 개수를 최상단에 상시로 띄운다. */
async function lastSuccessfulRun(): Promise<string | null> {
  const service = createSupabaseServiceClient()
  const { data } = await service
    .from('crawl_run_history')
    .select('finished_at')
    .eq('outcome', 'ok')
    .order('finished_at', { ascending: false })
    .limit(1)
    .maybeSingle()
  return data?.finished_at ?? null
}

export default async function AdminDashboardPage() {
  const session = await requireAdminSession()

  const [lastOk, schedulers] = await Promise.all([
    lastSuccessfulRun().catch(() => null),
    listSchedulers().catch(() => []),
  ])
  const paused = schedulers.filter((job) => job.state === 'PAUSED')

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">운영 대시보드</h1>

      <section className="rounded border border-slate-800 p-4">
        <h2 className="text-sm text-slate-400">마지막 성공 수집</h2>
        <p className={lastOk ? 'text-lg' : 'text-lg text-rose-400'}>
          {lastOk ? lastOk.slice(0, 19) : '기록 없음'}
        </p>
      </section>

      <section className="rounded border border-slate-800 p-4">
        <h2 className="text-sm text-slate-400">정지된 스케줄러</h2>
        <p className={paused.length > 0 ? 'text-lg text-rose-400' : 'text-lg text-emerald-300'}>
          {paused.length}개
        </p>
        {paused.length > 0 ? (
          <ul className="mt-2 text-xs text-slate-300">
            {paused.map((job) => <li key={job.name}>{job.name}</li>)}
          </ul>
        ) : null}
      </section>

      <p className="text-xs text-slate-500">
        {session.displayName ?? session.username} · 세션 만료 {session.expiresAt.slice(0, 19)}
      </p>
    </main>
  )
}
```

- [ ] **Step 5: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공

- [ ] **Step 6: 목록이 `gcloud` 와 일치하는지 확인한다**

```bash
LOCATION="$(gh variable get GCP_SCHEDULER_LOCATION)"
gcloud scheduler jobs list --location="$LOCATION" \
  --format='table(name.basename(), schedule, state)'

curl -s -b /tmp/admin_cookies.txt http://localhost:3000/api/admin/schedulers \
  | python -c "
import json,sys
for job in json.load(sys.stdin)['jobs']:
    print(f\"{job['name']:40s} {job['schedule'] or '-':14s} {job['state']:10s} controllable={job['controllable']}\")
"
```

Expected: 이름·cron·state 가 **정확히 일치**. `controllable=False` 인 정기 크롤/추출 잡이 있으면 Task 12 Step 12 의 상수 확정이 덜 된 것이다.

- [ ] **Step 7: pause → resume 왕복을 시험한다**

조작해도 안전한 잡 하나를 골라(예: 정지 상태인 것 중 하나):

```bash
NAME="naranhi-content-extractor-0700"   # Step 6 목록에서 실제 이름으로 바꾼다

curl -s -b /tmp/admin_cookies.txt -X POST -H 'content-type: application/json' \
  -d '{"action":"pause"}' "http://localhost:3000/api/admin/schedulers/$NAME" | python -m json.tool
gcloud scheduler jobs describe "$NAME" --location="$LOCATION" --format='value(state)'

curl -s -b /tmp/admin_cookies.txt -X POST -H 'content-type: application/json' \
  -d '{"action":"resume"}' "http://localhost:3000/api/admin/schedulers/$NAME" | python -m json.tool
gcloud scheduler jobs describe "$NAME" --location="$LOCATION" --format='value(state)'
```

Expected: `PAUSED` → `ENABLED`. 응답의 `job.state` 와 `gcloud describe` 결과가 매번 일치한다.

- [ ] **Step 8: 화이트리스트 밖 이름을 직접 호출해 본다 (스펙 §12.2)**

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -b /tmp/admin_cookies.txt \
  -X POST -H 'content-type: application/json' -d '{"action":"pause"}' \
  "http://localhost:3000/api/admin/schedulers/some-unrelated-job"
```

Expected: `HTTP 403`. 화이트리스트는 화면이 아니라 **백엔드 상수**가 막는다.

- [ ] **Step 9: 감사 로그를 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/admin_audit_log?select=created_at,action,target,detail&action=like.scheduler*&order=created_at.desc&limit=5')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
for row in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()):
    print(row['created_at'][:19], row['action'], row['target'], row['detail'])
"
```

Expected: `scheduler_pause` / `scheduler_resume` 각 1행 + 실패 시도의 `scheduler_pause_failed`

- [ ] **Step 10: 커밋**

```bash
git add lib/admin/gcp.ts app/api/admin/schedulers app/\(admin\)/admin/\(protected\)/schedulers \
        app/\(admin\)/admin/\(protected\)/page.tsx
git commit -m "feat(admin): 스케줄러 정지/재개 화면 + 조용한 정지 경보

gcloud scheduler jobs pause/resume 이 저장소 전체에 0건이었다. 문서는 create 만
적어 두었는데 실제로는 5개가 PAUSED 다 — 되살리는 방법이 사람 기억에만 있었다.
절차를 코드로 옮긴다.

문서가 아니라 Cloud Scheduler API 가 돌려준 실제 cron 과 state 를 보여준다.
문서와 실운영이 이미 어긋나 있다.

대시보드 최상단에 '마지막 성공 수집' 과 'PAUSED 개수' 를 상시로 띄운다.
잘못 눌린 pause 로 수집이 조용히 멈추는 것이 이 콘솔의 가장 큰 부작용 위험이고,
지금 5개가 그 상태인데 아무도 알림을 못 받고 있다.

ADMIN_API_TOKEN 은 server-only 파일에만 있다. 클라이언트 컴포넌트가 FastAPI
/admin/* 를 직접 부르는 코드를 만들지 않는다."
```

---

## Task 14: P1-2 재크롤 — 확인 다이얼로그가 본체다

`scripts/recrawl_trigger.py:51` 이 확인 프롬프트 없이 `DELETE /notices?school_id=eq.…` 를 던진다. `notice_ai_translations`(`0005:3`)·`school_events`(`0017:3-4`)·`notice_cards` 가 캐스케이드로 함께 사라진다. 화면은 **영향 건수를 먼저 보여주고 사람이 그 숫자를 확인한 뒤에** 실행한다.

`triggerInitialSchoolCrawl` 은 이미 `lib/school-crawler-trigger.ts:25-27` 에 있다. lib 에 없는 것은 **notices DELETE 와 watermark 리셋** 둘뿐이다.

> **사업 E 와의 접점.** 사업 E 의 `0039_school_events_source.sql` 이 `school_events.notice_id` 를 nullable 로 바꾼다 — RSS·공식 API 에서 온 일정은 공지에 딸리지 않는다. 아래 `previewRecrawl` 은 `.in('notice_id', noticeIds)` 로 세므로 `notice_id` 가 null 인 행은 **애초에 집계에서 빠지고, 공지 삭제로 사라지지도 않는다.** 두 동작이 일치하므로 사업 E 가 먼저 서든 나중에 서든 «미리보기 건수 = 실제 삭제 건수» 가 유지된다. Step 6 의 대조가 이를 확인한다.

**Files:**
- Create: `lib/admin/recrawl.ts`
- Create: `app/api/admin/schools/[schoolId]/recrawl/route.ts`
- Create: `app/(admin)/admin/(protected)/schools/RecrawlButton.tsx`
- Modify: `app/(admin)/admin/(protected)/schools/page.tsx` (열 1개 추가)

**Interfaces:**
- Consumes: Task 11 의 학교 목록, `triggerInitialSchoolCrawl`, Task 4 의 감사 로그
- Produces:
  - `RecrawlPreview = { schoolId, schoolName, noticeCount, translationCount, eventCount, cardCount, watermarkBoards }`
  - `previewRecrawl(schoolId: string): Promise<RecrawlPreview>`
  - `executeRecrawl(schoolId: string): Promise<{ deletedNotices: number; watermarkCleared: boolean; crawlQueued: boolean }>`
  - `GET /api/admin/schools/{id}/recrawl` → 미리보기
  - `POST /api/admin/schools/{id}/recrawl` `{ confirmNoticeCount }` → 건수 재확인 후 실행. 불일치면 **409**

- [ ] **Step 1: 미리보기·실행 라이브러리를 쓴다**

`lib/admin/recrawl.ts`:

```typescript
import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { triggerInitialSchoolCrawl } from '@/lib/school-crawler-trigger'

export interface RecrawlPreview {
  schoolId: string
  schoolName: string
  noticeCount: number
  translationCount: number
  eventCount: number
  cardCount: number
  watermarkBoards: number
}

async function noticeIdsFor(schoolId: string): Promise<string[]> {
  const service = createSupabaseServiceClient()
  const { data, error } = await service.from('notices').select('id').eq('school_id', schoolId)
  if (error) throw new Error(`공지 목록 조회 실패: ${error.message}`)
  return (data ?? []).map((row) => row.id)
}

/** 삭제 예정 건수. notices 만이 아니라 캐스케이드 대상까지 센다 —
 *  notice_ai_translations(0005:3), school_events(0017:3-4), notice_cards.
 *  「공지 38건 · 번역 155건 · 일정 68건이 삭제됩니다」가 보여야 사람이 판단할 수 있다. */
export async function previewRecrawl(schoolId: string): Promise<RecrawlPreview> {
  const service = createSupabaseServiceClient()

  const { data: school, error: schoolError } = await service
    .from('schools')
    .select('id,name')
    .eq('id', schoolId)
    .maybeSingle()
  if (schoolError) throw new Error(`학교 조회 실패: ${schoolError.message}`)
  if (!school) throw new Error('school_not_found')

  const noticeIds = await noticeIdsFor(schoolId)

  const countIn = async (table: 'notice_ai_translations' | 'school_events' | 'notice_cards') => {
    if (noticeIds.length === 0) return 0
    const { count, error } = await service
      .from(table)
      .select('id', { count: 'exact', head: true })
      .in('notice_id', noticeIds)
    if (error) throw new Error(`${table} 집계 실패: ${error.message}`)
    return count ?? 0
  }

  const { data: state } = await service
    .from('school_crawl_state')
    .select('board_watermarks')
    .eq('school_id', schoolId)
    .maybeSingle()

  return {
    schoolId,
    schoolName: school.name,
    noticeCount: noticeIds.length,
    translationCount: await countIn('notice_ai_translations'),
    eventCount: await countIn('school_events'),
    cardCount: await countIn('notice_cards'),
    watermarkBoards: Object.keys((state?.board_watermarks ?? {}) as Record<string, unknown>).length,
  }
}

/** scripts/recrawl_trigger.py 의 ②③④ 를 그대로 옮긴 것이다.
 *  ① 스냅샷은 previewRecrawl 이 맡고, 라우트가 사람 확인을 강제한다. */
export async function executeRecrawl(
  schoolId: string,
): Promise<{ deletedNotices: number; watermarkCleared: boolean; crawlQueued: boolean }> {
  const service = createSupabaseServiceClient()

  // ② notices 삭제 — translations/cards/events 가 캐스케이드로 함께 사라진다.
  const { data: deleted, error: deleteError } = await service
    .from('notices')
    .delete()
    .eq('school_id', schoolId)
    .select('id')
  if (deleteError) throw new Error(`공지 삭제 실패: ${deleteError.message}`)

  // ③ watermark 리셋 — 안 하면 증분수집이 옛 글을 건너뛴다.
  const { error: watermarkError } = await service
    .from('school_crawl_state')
    .update({ board_watermarks: {} })
    .eq('school_id', schoolId)

  // ④ discover-board 큐잉
  const crawlQueued = await triggerInitialSchoolCrawl(schoolId)

  return {
    deletedNotices: deleted?.length ?? 0,
    watermarkCleared: !watermarkError,
    crawlQueued,
  }
}
```

- [ ] **Step 2: 라우트를 쓴다**

`app/api/admin/schools/[schoolId]/recrawl/route.ts`:

```typescript
import { NextResponse, type NextRequest } from 'next/server'
import { requireAdminSession, writeAdminAudit } from '@/lib/admin/session'
import { executeRecrawl, previewRecrawl } from '@/lib/admin/recrawl'

/** 스펙 §7.4 는 /recrawl/preview 를 별도 경로로 적었다. 같은 자원에 대한
 *  «보기» 와 «실행» 이므로 GET/POST 로 가른다 — 파일이 하나 줄고 의미는 같다. */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ schoolId: string }> },
) {
  try {
    await requireAdminSession()
  } catch {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }
  const { schoolId } = await params
  return NextResponse.json({ ok: true, preview: await previewRecrawl(schoolId) })
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ schoolId: string }> },
) {
  let session
  try {
    session = await requireAdminSession()
  } catch {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const { schoolId } = await params
  const body = await request.json().catch(() => null)
  const confirmed = Number(body?.confirmNoticeCount)

  // 사람이 본 숫자와 지금 숫자가 같아야 실행한다. 미리보기와 실행 사이에
  // 크롤이 돌아 건수가 바뀌었다면 다시 보여주고 다시 묻는다.
  const preview = await previewRecrawl(schoolId)
  if (!Number.isInteger(confirmed) || confirmed !== preview.noticeCount) {
    return NextResponse.json(
      { ok: false, error: 'preview_stale', preview },
      { status: 409 },
    )
  }

  const result = await executeRecrawl(schoolId)
  await writeAdminAudit(session, 'school_recrawl', schoolId, {
    school: preview.schoolName,
    deleted_notices: result.deletedNotices,
    cascaded_translations: preview.translationCount,
    cascaded_events: preview.eventCount,
    cascaded_cards: preview.cardCount,
    watermark_cleared: result.watermarkCleared,
    crawl_queued: result.crawlQueued,
  })

  return NextResponse.json({ ok: true, preview, result })
}
```

- [ ] **Step 3: 확인 다이얼로그를 쓴다**

`app/(admin)/admin/(protected)/schools/RecrawlButton.tsx`:

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

interface Preview {
  schoolName: string
  noticeCount: number
  translationCount: number
  eventCount: number
  cardCount: number
  watermarkBoards: number
}

/** 이 버튼의 본체는 확인 다이얼로그다. scripts/recrawl_trigger.py:51 은
 *  확인 없이 DELETE 를 던진다. 되돌릴 수 없는 작업이므로 실제 영향 건수를
 *  먼저 보여주고, 사람이 본 그 숫자를 서버가 다시 대조한 뒤에 실행한다. */
export default function RecrawlButton({ schoolId }: { schoolId: string }) {
  const router = useRouter()
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function loadPreview() {
    setBusy(true)
    setError(null)
    const response = await fetch(`/api/admin/schools/${schoolId}/recrawl`)
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      setError(payload?.error ?? 'preview_failed')
      return
    }
    setPreview(payload.preview)
  }

  async function execute() {
    if (!preview) return
    setBusy(true)
    setError(null)
    const response = await fetch(`/api/admin/schools/${schoolId}/recrawl`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ confirmNoticeCount: preview.noticeCount }),
    })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      // 409 면 건수가 바뀐 것이다. 새 숫자를 보여주고 다시 묻는다.
      if (payload?.preview) setPreview(payload.preview)
      setError(payload?.error ?? 'recrawl_failed')
      return
    }
    setPreview(null)
    router.refresh()
  }

  if (!preview) {
    return (
      <button disabled={busy} onClick={loadPreview} className="underline disabled:opacity-50">
        {busy ? '확인 중…' : '재크롤'}
        {error ? <span className="ml-2 text-xs text-rose-400">{error}</span> : null}
      </button>
    )
  }

  return (
    <div className="flex flex-col gap-1 rounded border border-rose-800 bg-rose-950/40 p-2">
      <p className="text-xs font-semibold text-rose-200">되돌릴 수 없습니다</p>
      <p className="text-xs">
        {preview.schoolName} — 공지 {preview.noticeCount}건 · 번역 {preview.translationCount}건 ·
        일정 {preview.eventCount}건 · 카드 {preview.cardCount}건이 삭제되고,
        watermark {preview.watermarkBoards}개 게시판이 초기화됩니다.
      </p>
      <div className="flex gap-3">
        <button disabled={busy} onClick={execute} className="text-rose-300 underline disabled:opacity-50">
          {busy ? '실행 중…' : '삭제하고 재크롤'}
        </button>
        <button disabled={busy} onClick={() => setPreview(null)} className="underline disabled:opacity-50">
          취소
        </button>
      </div>
      {error ? <span className="text-xs text-rose-400">{error}</span> : null}
    </div>
  )
}
```

- [ ] **Step 4: 학교 화면에 열을 붙인다**

`app/(admin)/admin/(protected)/schools/page.tsx` 의 import 에 한 줄:

```typescript
import RecrawlButton from './RecrawlButton'
```

`<thead>` 의 마지막 `<th>오류</th>` 다음에:

```typescript
              <th>재크롤</th>
```

`<tbody>` 의 마지막 `<td>` 다음에:

```typescript
                  <td><RecrawlButton schoolId={school.id} /></td>
```

- [ ] **Step 5: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공

- [ ] **Step 6: 미리보기 건수가 DB 와 맞는지 확인한다**

```bash
SCHOOL_ID=$(python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notices?select=school_id&limit=1000')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
from collections import Counter
c=Counter(x['school_id'] for x in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()) if x['school_id'])
print(c.most_common(1)[0][0] if c else '')
")
echo "대상 학교: $SCHOOL_ID"

curl -s -b /tmp/admin_cookies.txt "http://localhost:3000/api/admin/schools/$SCHOOL_ID/recrawl" \
  | python -m json.tool

python -c "
import json,os,sys,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
sid=sys.argv[1]
def get(p):
    r=urllib.request.Request(u+p); r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
    return json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
ids=[x['id'] for x in get(f'/rest/v1/notices?select=id&school_id=eq.{sid}')]
q='in.(' + ','.join(ids) + ')'
print('DB 직접 — 공지', len(ids),
      '번역', len(get(f'/rest/v1/notice_ai_translations?select=id&notice_id={q}')),
      '일정', len(get(f'/rest/v1/school_events?select=id&notice_id={q}')),
      '카드', len(get(f'/rest/v1/notice_cards?select=id&notice_id={q}')))
" "$SCHOOL_ID"
```

Expected: 미리보기 응답의 `noticeCount` / `translationCount` / `eventCount` / `cardCount` 가 DB 직접 집계와 **정확히 일치**. 다르면 캐스케이드 계산이 틀린 것이니 **중단하고 보고할 것.**

- [ ] **Step 7: 틀린 건수로는 실행되지 않는지 확인한다**

```bash
curl -s -o /tmp/stale.json -w "HTTP %{http_code}\n" -b /tmp/admin_cookies.txt \
  -X POST -H 'content-type: application/json' -d '{"confirmNoticeCount":99999}' \
  "http://localhost:3000/api/admin/schools/$SCHOOL_ID/recrawl"
python -c "
import json
d=json.load(open('/tmp/stale.json',encoding='utf-8'))
print('error =', d.get('error'), '| 실제 건수 =', (d.get('preview') or {}).get('noticeCount'))
"
python -c "
import json,os,sys,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+f'/rest/v1/notices?select=id&school_id=eq.{sys.argv[1]}')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
print('삭제되지 않았음 — 남은 공지:', len(json.loads(urllib.request.urlopen(r,timeout=60).read().decode())))
" "$SCHOOL_ID"
```

Expected: `HTTP 409` + `error = preview_stale` + 공지가 **하나도 삭제되지 않았다**

- [ ] **Step 8: 커밋 (실제 실행은 하지 않는다)**

```bash
git add lib/admin/recrawl.ts app/api/admin/schools \
        app/\(admin\)/admin/\(protected\)/schools
git commit -m "feat(admin): 재크롤 — 미리보기 → 확인 → 실행 + 감사 로그

scripts/recrawl_trigger.py:51 은 확인 프롬프트 없이 DELETE /notices 를 던진다.
translations(0005:3) / school_events(0017:3-4) / notice_cards 가 캐스케이드로
함께 사라지는데 그 건수를 아무도 안 본다.

화면은 영향 건수를 먼저 보여주고, 사람이 본 그 숫자를 서버가 다시 대조한
뒤에만 실행한다. 미리보기와 실행 사이에 건수가 바뀌면 409 로 되돌리고
새 숫자로 다시 묻는다.

스크립트의 ②notices DELETE 와 ③watermark 리셋만 새로 만든다.
④discover-board 는 lib/school-crawler-trigger.ts:25-27 에 이미 있다.

감사 로그에 캐스케이드 건수까지 남긴다 — 나중에 '무엇이 사라졌나' 를
물을 곳이 여기뿐이다.

이 커밋은 실제 재크롤을 실행하지 않는다."
```

- [ ] **Step 9: (선택) 실제 재크롤 1회 — 운영 승인 후에만**

미리보기 건수와 실제 삭제 건수가 같은지 끝까지 확인하려면 실제로 한 번 돌려야 한다. **운영 승인 없이는 하지 않는다.** 승인 후:

```bash
BEFORE=$(curl -s -b /tmp/admin_cookies.txt "http://localhost:3000/api/admin/schools/$SCHOOL_ID/recrawl" \
  | python -c "import json,sys; print(json.load(sys.stdin)['preview']['noticeCount'])")
curl -s -b /tmp/admin_cookies.txt -X POST -H 'content-type: application/json' \
  -d "{\"confirmNoticeCount\":$BEFORE}" \
  "http://localhost:3000/api/admin/schools/$SCHOOL_ID/recrawl" | python -m json.tool
```

Expected: `result.deletedNotices` 가 **`BEFORE` 와 같다.** `result.crawlQueued: true` 이고 `app_jobs` 에 `school-discovery:{id}` 가 생긴다.

---

## Task 15: P1-3 공지 검수 · 강제 재추출

지금은 사람이 이걸 친다 (`docs/content-extractor-job.md:137-141`):

```
gcloud run jobs execute naranhi-content-extractor \
  --args="--notice-id=<notice_id>,--force,--max-notices=1" --wait
```

**Files:**
- Create: `app/api/admin/notices/[noticeId]/reextract/route.ts`
- Create: `app/(admin)/admin/(protected)/notices/page.tsx`
- Create: `app/(admin)/admin/(protected)/notices/ReextractButton.tsx`

**Interfaces:**
- Consumes: Task 13 의 `runAdminJob`, Task 12 의 `RUNNABLE_JOBS`
- Produces: `POST /api/admin/notices/{noticeId}/reextract` → `{ ok, operation }`

- [ ] **Step 1: 재추출 라우트를 쓴다**

`app/api/admin/notices/[noticeId]/reextract/route.ts`:

```typescript
import { NextResponse, type NextRequest } from 'next/server'
import { requireAdminSession, writeAdminAudit } from '@/lib/admin/session'
import { AdminApiError, runAdminJob } from '@/lib/admin/gcp'

/** docs/content-extractor-job.md:137-141 의 수동 gcloud 와 같은 args 다.
 *  scheduled_content_extractor 의 파서는 --force 에 --notice-id 를 요구한다(:59). */
const EXTRACTOR_JOB = 'naranhi-content-extractor'

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ noticeId: string }> },
) {
  let session
  try {
    session = await requireAdminSession()
  } catch {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const { noticeId } = await params
  const args = [`--notice-id=${noticeId}`, '--force', '--max-notices=1']

  try {
    const { operation } = await runAdminJob(EXTRACTOR_JOB, args)
    // Gemini 호출 비용이 발생하는 조작이다. 누가 얼마나 눌렀는지가 남아야 한다.
    await writeAdminAudit(session, 'notice_reextract', noticeId, { operation, args })
    return NextResponse.json({ ok: true, operation })
  } catch (error) {
    await writeAdminAudit(session, 'notice_reextract_failed', noticeId, { error: String(error) })
    const status = error instanceof AdminApiError ? error.status : 502
    return NextResponse.json({ ok: false, error: String(error) }, { status })
  }
}
```

- [ ] **Step 2: 버튼과 화면을 쓴다**

`app/(admin)/admin/(protected)/notices/ReextractButton.tsx`:

```typescript
'use client'

import { useState } from 'react'

export default function ReextractButton({ noticeId }: { noticeId: string }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function run() {
    if (!confirm('이 공지를 강제 재추출합니다. Gemini 호출 비용이 발생합니다.')) return
    setBusy(true)
    setMessage(null)
    const response = await fetch(`/api/admin/notices/${noticeId}/reextract`, { method: 'POST' })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    setMessage(
      response.ok && payload?.ok
        ? `실행됨 (${String(payload.operation).slice(-12)})`
        : (payload?.error ?? 'failed'),
    )
  }

  return (
    <div className="flex items-center gap-2">
      <button disabled={busy} onClick={run} className="underline disabled:opacity-50">
        {busy ? '실행 중…' : '재추출'}
      </button>
      {message ? <span className="text-xs text-slate-400">{message}</span> : null}
    </div>
  )
}
```

`app/(admin)/admin/(protected)/notices/page.tsx`:

```typescript
import { requireAdminSession } from '@/lib/admin/session'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
import ReextractButton from './ReextractButton'

export const dynamic = 'force-dynamic'

export default async function AdminNoticesPage() {
  await requireAdminSession()
  const service = createSupabaseServiceClient()

  const [notices, schools] = await Promise.all([
    service
      .from('notices')
      .select('id,school_id,title,status,created_at,extracted_content')
      .order('created_at', { ascending: false })
      .limit(200),
    service.from('schools').select('id,name'),
  ])
  if (notices.error) throw new Error(`공지 조회 실패: ${notices.error.message}`)
  if (schools.error) throw new Error(`학교 조회 실패: ${schools.error.message}`)

  const schoolName = new Map((schools.data ?? []).map((s) => [s.id, s.name]))

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">공지 검수</h1>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead className="text-slate-400">
            <tr>
              <th className="py-1">생성</th>
              <th>학교</th>
              <th>제목</th>
              <th>상태</th>
              <th>본문</th>
              <th>조작</th>
            </tr>
          </thead>
          <tbody>
            {(notices.data ?? []).map((notice) => {
              const extracted = (notice.extracted_content ?? null) as Record<string, unknown> | null
              const sources = Array.isArray(extracted?.sources) ? extracted.sources : []
              return (
                <tr key={notice.id} className="border-t border-slate-800">
                  <td className="py-1 whitespace-nowrap">{notice.created_at.slice(0, 19)}</td>
                  <td>{notice.school_id ? (schoolName.get(notice.school_id) ?? '-') : '-'}</td>
                  <td className="max-w-[320px] truncate" title={notice.title ?? ''}>{notice.title ?? '-'}</td>
                  <td className={notice.status === 'error' ? 'text-rose-400' : ''}>{notice.status}</td>
                  <td>{extracted ? `첨부 ${sources.length}` : '없음'}</td>
                  <td><ReextractButton noticeId={notice.id} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </main>
  )
}
```

- [ ] **Step 3: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공

- [ ] **Step 4: 재추출이 수동 gcloud 와 같은 결과를 내는지 확인한다**

```bash
NID=$(python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notices?select=id&order=created_at.desc&limit=1')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
print(json.loads(urllib.request.urlopen(r,timeout=60).read().decode())[0]['id'])
")
curl -s -b /tmp/admin_cookies.txt -X POST \
  "http://localhost:3000/api/admin/notices/$NID/reextract" | python -m json.tool

OP=$(gcloud run jobs executions list --job=naranhi-content-extractor \
  --region="$(gh variable get GCP_REGION)" --limit=1 --format='value(name)')
gcloud run jobs executions describe "$OP" \
  --region="$(gh variable get GCP_REGION)" \
  --format='value(spec.template.spec.template.spec.containers[0].args)'
```

Expected: 응답 `{"ok": true, "operation": "..."}`. `executions describe` 의 args 가 **`--notice-id=<NID>`, `--force`, `--max-notices=1`** 이다 — `worker_trigger.py:87-108` 의 `json={}` 로는 나올 수 없는 값이다.

- [ ] **Step 5: 커밋**

```bash
git add app/api/admin/notices app/\(admin\)/admin/\(protected\)/notices
git commit -m "feat(admin): 공지 강제 재추출 버튼

docs/content-extractor-job.md:137-141 의 수동 gcloud 를 화면으로 옮긴다.
같은 args(--notice-id=… --force --max-notices=1)를 Cloud Run Job overrides 로
넘긴다 — Task 12 의 run_job_with_args 가 없으면 불가능한 일이다.

Gemini 호출 비용이 발생하는 조작이라 확인 다이얼로그와 감사 로그를 둔다."
```

---

## Task 16: P2-1 번역 검토 큐 + P2-2 실행 이력

Task 9 가 채우기 시작한 `needs_review` 와 Task 8 이 쌓기 시작한 `crawl_run_history` 를 화면으로 만든다. **이 두 화면은 앞의 두 Task 없이는 빈 화면이다.**

**Files:**
- Create: `lib/admin/reviews.ts`
- Create: `lib/admin/runs.ts`
- Create: `app/(admin)/admin/(protected)/reviews/page.tsx`
- Create: `app/(admin)/admin/(protected)/runs/page.tsx`

**Interfaces:**
- Consumes: Task 7 의 `crawl_run_history` / `needs_review` 타입, Task 8·9 가 채운 데이터
- Produces:
  - `listReviewQueue(): Promise<ReviewQueueRow[]>` — `{ noticeId, noticeTitle, schoolName, targetLanguage, reviewReason, updatedAt }`
  - `listCrawlRuns(limit?: number): Promise<CrawlRunRow[]>` — `crawl_run_history` Row 그대로

- [ ] **Step 1: 검토 큐 조회를 쓴다**

`lib/admin/reviews.ts`:

```typescript
import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'

export interface ReviewQueueRow {
  noticeId: string
  noticeTitle: string | null
  schoolName: string | null
  targetLanguage: string
  reviewReason: string | null
  updatedAt: string
}

/** 부분 인덱스 notice_ai_translations_needs_review_idx(0041)가 이 조회를 받는다.
 *  전체 155행 중 needs_review 인 소수만 인덱싱된다. */
export async function listReviewQueue(): Promise<ReviewQueueRow[]> {
  const service = createSupabaseServiceClient()

  const { data: translations, error } = await service
    .from('notice_ai_translations')
    .select('notice_id,target_language,review_reason,updated_at')
    .eq('needs_review', true)
    .order('updated_at', { ascending: false })
    .limit(300)
  if (error) throw new Error(`검토 큐 조회 실패: ${error.message}`)

  const rows = translations ?? []
  if (rows.length === 0) return []

  const noticeIds = [...new Set(rows.map((row) => row.notice_id))]
  const { data: notices } = await service
    .from('notices')
    .select('id,title,school_id')
    .in('id', noticeIds)
  const { data: schools } = await service.from('schools').select('id,name')

  const schoolName = new Map((schools ?? []).map((s) => [s.id, s.name]))
  const noticeById = new Map((notices ?? []).map((n) => [n.id, n]))

  return rows.map((row) => {
    const notice = noticeById.get(row.notice_id)
    return {
      noticeId: row.notice_id,
      noticeTitle: notice?.title ?? null,
      schoolName: notice?.school_id ? (schoolName.get(notice.school_id) ?? null) : null,
      targetLanguage: row.target_language,
      reviewReason: row.review_reason,
      updatedAt: row.updated_at,
    }
  })
}
```

- [ ] **Step 2: 실행 이력 조회를 쓴다**

`lib/admin/runs.ts`:

```typescript
import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import type { Database } from '@/types/database'

export type CrawlRunRow = Database['public']['Tables']['crawl_run_history']['Row']

export async function listCrawlRuns(limit = 100): Promise<CrawlRunRow[]> {
  const service = createSupabaseServiceClient()
  const { data, error } = await service
    .from('crawl_run_history')
    .select(
      'id,started_at,finished_at,outcome,dry_run,force,total_registered,selected_count,skipped_count,processed_count,success_count,failure_count,success_rate,alarm,targets,results,error_message,created_at',
    )
    .order('created_at', { ascending: false })
    .limit(limit)
  if (error) throw new Error(`실행 이력 조회 실패: ${error.message}`)
  return (data ?? []) as CrawlRunRow[]
}
```

- [ ] **Step 3: 검토 큐 화면을 쓴다**

`app/(admin)/admin/(protected)/reviews/page.tsx`:

```typescript
import { requireAdminSession } from '@/lib/admin/session'
import { listReviewQueue } from '@/lib/admin/reviews'

export const dynamic = 'force-dynamic'

export default async function AdminReviewsPage() {
  await requireAdminSession()
  const rows = await listReviewQueue()

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">번역 검토 대기</h1>
      {/* 이 목록에 오른 번역도 사용자에게는 그대로 나가고 있다.
          validation_status 는 여전히 'passed' 다(notice_service.py:778-781).
          needs_review 는 '표시' 만 바꾼다. */}
      <p className="text-xs text-slate-500">
        검증 경고가 붙은 번역이다. 사용자에게는 이미 노출되고 있다 — 여기 있다고 막힌 것이 아니다.
      </p>

      {rows.length === 0 ? (
        <p className="text-sm text-slate-400">
          검토 대기 없음. (0041 적용 전에 저장된 번역은 needs_review 가 false 다 —
          컬럼 기본값이지 «검증을 통과했다» 는 뜻이 아니다.)
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead className="text-slate-400">
              <tr>
                <th className="py-1">갱신</th>
                <th>학교</th>
                <th>공지</th>
                <th>언어</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.noticeId}:${row.targetLanguage}`} className="border-t border-slate-800 align-top">
                  <td className="py-1 whitespace-nowrap">{row.updatedAt.slice(0, 19)}</td>
                  <td>{row.schoolName ?? '-'}</td>
                  <td className="max-w-[280px] truncate" title={row.noticeTitle ?? ''}>
                    {row.noticeTitle ?? row.noticeId}
                  </td>
                  <td>{row.targetLanguage}</td>
                  <td className="max-w-[360px] whitespace-pre-wrap break-words text-amber-200">
                    {row.reviewReason ?? '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-slate-500">{rows.length}건</p>
    </main>
  )
}
```

- [ ] **Step 4: 실행 이력 화면을 쓴다**

`app/(admin)/admin/(protected)/runs/page.tsx`:

```typescript
import { requireAdminSession } from '@/lib/admin/session'
import { listCrawlRuns } from '@/lib/admin/runs'
import type { CrawlRunOutcome } from '@/types/database'

export const dynamic = 'force-dynamic'

/** ⚠️ processed_count == 0 은 «성공» 이 아니라 «미실행» 이다.
 *  scheduled_crawler_service.py:335-336 이 그 경우 success_rate 를 1.0,
 *  alarm 을 False 로 만들기 때문에, 숫자만 보면 완벽한 실행처럼 보인다. */
const OUTCOME_BADGE: Record<CrawlRunOutcome, { label: string; className: string }> = {
  ok: { label: '성공', className: 'bg-emerald-900 text-emerald-200' },
  idle: { label: '미실행', className: 'bg-slate-700 text-slate-200' },
  alarm: { label: '성공률 미달', className: 'bg-amber-900 text-amber-100' },
  crashed: { label: '크래시', className: 'bg-rose-900 text-rose-100' },
}

export default async function AdminRunsPage() {
  await requireAdminSession()
  const runs = await listCrawlRuns()

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">정기 크롤 실행 이력</h1>
      <p className="text-xs text-slate-500">
        «성공률 임계치» 는 CRAWLER_SCHEDULE_FAIL_RATE_THRESHOLD 다. 이름은 fail_rate 지만
        실제로는 성공률과 비교한다(기본 0.5).
      </p>

      {runs.length === 0 ? (
        <p className="text-sm text-slate-400">
          이력 없음. 스케줄러가 PAUSED 라면 정기 실행이 없다 — 스케줄러 화면을 확인한다.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead className="text-slate-400">
              <tr>
                <th className="py-1">시작</th>
                <th>결과</th>
                <th>등록</th>
                <th>선택</th>
                <th>건너뜀</th>
                <th>처리</th>
                <th>성공/실패</th>
                <th>성공률</th>
                <th>오류</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const badge = OUTCOME_BADGE[run.outcome]
                return (
                  <tr key={run.id} className="border-t border-slate-800 align-top">
                    <td className="py-1 whitespace-nowrap">{run.started_at.slice(0, 19)}</td>
                    <td><span className={`rounded px-1.5 py-0.5 ${badge.className}`}>{badge.label}</span></td>
                    <td>{run.total_registered}</td>
                    <td>{run.selected_count}</td>
                    <td>{run.skipped_count}</td>
                    <td>{run.processed_count}</td>
                    <td>{run.success_count}/{run.failure_count}</td>
                    <td>{run.processed_count === 0 ? '-' : `${Math.round(run.success_rate * 100)}%`}</td>
                    <td className="max-w-[300px] whitespace-pre-wrap break-words text-rose-300">
                      {run.error_message ?? '-'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}
```

- [ ] **Step 5: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공

- [ ] **Step 6: 검토 큐가 실제 신호를 잡는지 확인한다**

번역 1건을 검증 경고가 나도록 실행시킨 뒤(또는 이미 그런 행이 있으면 그대로):

```bash
curl -s -b /tmp/admin_cookies.txt -o /tmp/reviews.html http://localhost:3000/admin/reviews
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notice_ai_translations?select=notice_id,target_language,review_reason&needs_review=is.true&limit=50')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
print('DB needs_review =', len(rows))
for row in rows[:5]: print(' ', row['target_language'], (row['review_reason'] or '')[:60])
"
grep -c "검토 대기 없음" /tmp/reviews.html
```

Expected: DB 건수와 화면 행 수가 일치. 0건이면 화면에 `검토 대기 없음` 이 나오고 grep 이 `1` 을 낸다 — 그것도 정상이다.

- [ ] **Step 7: 실행 이력이 `idle` 을 «성공» 으로 보여주지 않는지 확인한다**

```bash
curl -s -b /tmp/admin_cookies.txt -o /tmp/runs.html http://localhost:3000/admin/runs
grep -o "성공률 미달\|미실행\|크래시\|>성공<" /tmp/runs.html | sort | uniq -c
python -c "
import json,os,urllib.request
from collections import Counter
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/crawl_run_history?select=outcome,processed_count,success_rate&limit=200')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
print('DB outcome 분포 =', dict(Counter(x['outcome'] for x in rows)))
idle=[x for x in rows if x['processed_count']==0]
print('processed_count==0 인 행:', len(idle), '— 전부 outcome=idle 인가?', all(x['outcome']=='idle' for x in idle))
"
```

Expected: 화면 배지 분포와 DB `outcome` 분포가 일치. `processed_count==0` 인 행이 **전부 `idle`** 이고 화면에 «미실행» 로 나온다 — success_rate 100% 로 «성공» 처럼 보이지 않는다.

- [ ] **Step 8: 커밋**

```bash
git add lib/admin/reviews.ts lib/admin/runs.ts \
        app/\(admin\)/admin/\(protected\)/reviews app/\(admin\)/admin/\(protected\)/runs
git commit -m "feat(admin): 번역 검토 큐 + 정기 크롤 실행 이력 화면

Task 8·9 가 만든 데이터를 화면으로 만든다. 두 화면 모두 그 앞의 두 Task
없이는 빈 화면이다 — 신호가 코드에서 사라졌고 담을 컬럼도 없었기 때문이다.

실행 이력은 processed_count==0 을 '성공' 이 아니라 '미실행' 으로 표시한다.
scheduled_crawler_service.py:335-336 이 그 경우 success_rate 를 1.0,
alarm 을 False 로 만들어서 숫자만 보면 완벽한 실행처럼 보인다.

검토 큐는 '여기 있다고 막힌 것이 아니다' 를 화면에 명시한다.
validation_status 는 여전히 passed 이고 번역문은 이미 사용자에게 나가 있다."
```

---

## 자체 검토

**1. 스펙 커버리지**

| 스펙 항목 | 담당 Task |
|---|---|
| §3.4 권고 (c) — 별도 테이블 + pgcrypto + 자체 세션 | Task 1, 2, 4 |
| §3.5 세션 8시간 절대 만료·갱신 없음 | Task 4 Step 1 (`ADMIN_SESSION_MAX_AGE_SECONDS`) |
| §3.5 쿠키 속성 (`HttpOnly`/`Secure`/`SameSite=Strict`) | Task 5 Step 5 |
| §3.5 세션 저장은 토큰 «해시» | Task 4 Step 2 (`hashToken`) |
| §3.5 2단계 인증 «하지 않되 자리만» | Task 1 Step 3 (`totp_secret` 컬럼, 미사용) |
| §3.5 5회 실패 → 15분 잠금 | Task 1 Step 3 (`admin_verify_password`), Task 2 Step 6 |
| §3.5 응답 시간·문구 고정 | Task 5 Step 5 (`FIXED_RESPONSE_MS`), Step 3 (단일 문구) |
| §3.5 비밀번호를 사람이 고르지 않는다 | Task 2 Step 1 |
| §4.1 1단계는 `/admin`, route group 격리 | Task 5 Step 3~4 (`app/(admin)/`) |
| §4.1 세션 검증을 한 파일에 | Task 4 (`lib/admin/session.ts`) |
| §4.2 middleware 맨 앞 + 라우트 이중 검사 | Task 5 Step 2·4, 각 API 라우트의 `requireAdminSession()` |
| §4.2 `PUBLIC_PATHS` 에 관리자 경로를 넣지 않음 | Task 5 Step 2 (`ADMIN_LOGIN_PATHS` 별도) |
| §5.1 `profiles.role` 복원하지 않음 | Global Constraints + Task 1 Step 3 주석 |
| §5.4 `0038` 세 테이블 + RLS 활성·정책 0개 | Task 1 Step 3 |
| §6.2 페이징 만들지 않음 | Task 10 Step 1 (`DEFAULT_LIMIT`), Task 11 Step 1 |
| §6.3 P0-2 잡 큐 — 전 컬럼 + 재시도·포기 + 1000자 상한 | Task 10 |
| §6.3 P0-3 학교 상태 — `crawl_board_kind` 배지 | Task 11 Step 2 |
| §6.3 `board_watermarks` 누락 보강 (선행) | Task 3 Step 6 |
| §6.3 P1-2 재크롤 — ①②③④ + 캐스케이드 건수 | Task 14 |
| §6.3 P1-3 강제 재추출 | Task 15 |
| §6.4 화면이 명세↔구현 불일치를 «드러내기만» | Task 13 Step 3 (실제 cron 표시 + 안내 문구) |
| §7.1~7.2 조회는 Next.js, GCP 제어는 FastAPI | Task 10·11·14(Next.js) vs Task 12(FastAPI) |
| §7.3 `_require_admin_token` — local 예외 없이 503 | Task 12 Step 5 + 테스트 Step 1 |
| §7.4 엔드포인트 목록 | Task 5·10·12·13·14·15 |
| §8.1 `run_job_with_args` — 디바운스 없음·예외 전파·overrides | Task 12 Step 4 + 테스트 |
| §8.2 Scheduler 제어 + 커스텀 역할 + 화이트리스트 상수 | Task 12 Step 4·9, Task 13 Step 8 |
| §8.2 location 확정 | Task 12 Step 10·12 |
| §9.1 구조화 로깅 (진입점 6개) | Task 6 |
| §9.2 `crawl_run_history` + `processed_count==0` 구분 + `outcome` | Task 7·8, Task 16 Step 4 |
| §9.3 검토 신호 복구 (컬럼 + 쓰기 경로) | Task 7 Step 1, Task 9 |
| §9.4 실패 알림 | **미포함** — Global Constraints 에 사유 명시 (§15 Q7 미결) |
| §12.1 비인가 접근 #1·#2·#3·#4·#7·#11 | Task 5 Step 7·8 |
| §12.1 #5·#6 anon 으로 관리자 테이블 | Task 1 Step 1·6 |
| §12.1 #8 FastAPI 토큰 없이 | Task 12 Step 12 |
| §12.1 #12 5회 실패 잠금 | Task 2 Step 6 |
| §12.1 #13 계정 존재 유추 차단 | Task 2 Step 5, Task 5 Step 8 |
| §12.1 #14 `profiles.role` 자기 승격 | **해당 없음** — 복원하지 않으므로 그 경로 자체가 없다 |
| §12.2 기능 검증 12항목 | Task 10 Step 5~7, 11 Step 4, 13 Step 6~9, 14 Step 6~9, 15 Step 4, 16 Step 6~7 |
| §12.3 회귀 | Task 6 Step 8, Task 9 Step 6, 각 프론트 Task 의 typecheck+build |
| §13.1 `server-only` 누락 (범위 최소 예외) | Task 3 Step 2 |
| §13.1 «조용한 정지» 완화 — 마지막 성공 실행 시각 상시 표시 | Task 13 Step 4 |
| §12.1 #9·#10 (쿠키 경로 격리 / 8시간 만료) | **부분** — 아래 «3. 남긴 것» 참조 |

**2. 자리표시자 점검** — "TBD"·"적절히"·"비슷하게" 없음. 모든 코드·SQL Step 에 실제 내용이 들어 있다. 단 두 곳이 «착수 시 실측으로 확정» 이며, 확정 절차가 Step 으로 들어 있다:
- `CONTROLLABLE_SCHEDULERS` 초기값은 `docs/scheduled-crawl-runbook.md:64-67` 에서 가져온 실제 이름 4개다. Task 12 Step 12 가 API 응답과 대조해 확정하고 필요하면 별도 커밋한다.
- `GCP_SCHEDULER_LOCATION` 은 Task 12 Step 10 의 안내대로 확정한다.

**3. 남긴 것 — 의도적으로 하지 않은 검증**

| 스펙 항목 | 왜 안 했나 |
|---|---|
| §12.1 #9 «관리자 쿠키를 `/` 경로에서 읽기 시도» | 쿠키가 `__Host-` + `Path=/` 라 경로로는 격리되지 않는다. **격리는 `HttpOnly` 가 한다** — 스크립트가 아예 못 읽으므로 경로와 무관하게 통과한다. 시험 자체가 의미를 잃어 대체하지 않았다 (Global Constraints 의 쿠키 접두 결정 참조) |
| §12.1 #10 «세션 발급 8시간 + 1분 후» | 8시간을 실제로 기다리는 Step 을 만들 수 없다. `getAdminSession()` 의 `expires_at` 비교가 그 판정을 하고, Task 5 Step 8 의 #11(폐기 쿠키 거부)이 같은 코드 경로를 지난다. 필요하면 `admin_sessions.expires_at` 을 과거로 PATCH 해 1초 만에 확인할 수 있다 |
| §9.4 실패 알림 | 알림 채널이 미확정(§15 Q7). Task 8·13·16 이 «드러내기» 까지 하고 채널이 정해지면 별건 |

**4. 타입·심볼 일관성**

- `ADMIN_COOKIE_NAME` / `ADMIN_SESSION_MAX_AGE_SECONDS` — Task 4 Step 1 정의, Task 4 Step 2 재수출, Task 5 Step 2(middleware)·Step 5(라우트) 사용. middleware 는 `session.ts` 가 아니라 `cookie.ts` 에서 가져온다(Step 2 확인).
- `admin_verify_password` / `admin_set_password` — Task 1 Step 3 SQL, Task 3 Step 5 타입, Task 4 Step 2·Task 2 Step 1 호출. 인자명 `p_username` / `p_password` / `p_display_name` 3곳 일치.
- `outcome ∈ {'ok','invalid','locked'}` — Task 1 SQL CHECK 없이 리터럴, Task 3 타입 유니온, Task 4 `VerifyOutcome` 분기. 세 곳 일치.
- `AppJobStatus` — Task 3 Step 4 정의, Task 10 Step 1·2·3 사용.
- `CrawlRunOutcome ∈ {'ok','idle','alarm','crashed'}` — Task 7 Step 1 SQL CHECK, Step 3 타입, Task 8 Step 3 `outcome_for`(3값) + Step 5 `'crashed'`, Task 16 Step 4 `OUTCOME_BADGE`(4키). 네 곳 일치.
- `needs_review` / `review_reason` — Task 7 컬럼, Task 9 Step 4 `row` 조립, Task 16 Step 1 조회. 키 이름 일치.
- `_needs_review_from_pipeline(pipeline_result, metadata)` — Task 9 Step 1 테스트가 참조, Step 3 정의, Step 4 호출. 인자 순서 일치.
- `record_crawl_run(summary, *, outcome, error_message=None)` — Task 8 Step 1 테스트, Step 3 정의, Step 5 두 호출부. 일치.
- `setup_logging(*, job_type=None, level=None)` — Task 6 Step 3 정의, Step 5 여섯 호출부. `main.py`/`worker_main.py` 만 `level` 을 넘긴다(Settings 값이 있으므로).
- `RunResult(job_name, operation, args)` + `to_dict()` — Task 12 Step 4 정의, Step 5 라우터가 `**result.to_dict()` 로 펼침, Task 13 Step 1 `runAdminJob` 이 `operation` 을 읽음. 키 이름 일치.
- `CONTROLLABLE_SCHEDULERS` / `RUNNABLE_JOBS` — Task 12 Step 4 정의, Step 4 내부 검사 2곳, Task 12 Step 1 테스트가 `sorted(...)[0]` 로 참조. `naranhi-content-extractor` 가 `RUNNABLE_JOBS` 에 있어야 Task 15 가 동작한다 — 있다.
- `AdminApiError` — Task 13 Step 1 정의, Step 2·Task 15 Step 1 의 `instanceof` 분기. 일치.
- `previewRecrawl` 의 `noticeCount` ↔ 라우트의 `confirmNoticeCount` ↔ 버튼의 `preview.noticeCount` — Task 14 Step 1·2·3 세 곳 일치.
- `board_watermarks` — Task 3 이 타입·select·매핑에 넣고, Task 11(`watermarkBoards`)·Task 14(`previewRecrawl`)가 읽고, Task 14 `executeRecrawl` 이 `{}` 로 되돌린다.
- `/tmp/admin_cookies.txt` — Task 5 Step 8 이 만들고 Task 10·11·13·14·15·16 의 확인 Step 이 쓴다. 세션이 8시간이므로 하루 작업 안에서는 재로그인이 필요 없다.

**5. 순서 의존성 점검**

- Task 4 는 Task 3 의 타입 없이는 typecheck 를 통과하지 못한다 → Task 3 이 앞. ✅
- Task 2 는 Task 1 이 **머지·적용된 뒤**에만 성공한다 → Task 1 Step 6 이 «머지 후 확인» 이다. ✅
- Task 8·9 는 Task 7 이 머지·적용된 뒤에만 실제 데이터를 만든다. 코드·테스트는 그 전에 통과한다(전부 mock). Task 8 Step 9 와 Task 9 Step 8 이 «배포 후» 로 표시돼 있다. ✅
- Task 13 은 Task 12 가 **배포된 뒤**에만 실제 스케줄러를 본다 → Task 12 Step 12 가 배포 후 확인이고, Task 13 Step 6 이 그 뒤다. ✅
- Task 15 는 Task 13 Step 1 의 `runAdminJob` 을 쓴다 → Task 13 이 앞. ✅
- Task 16 은 Task 7·8·9 의 데이터에 의존한다 → 전부 앞에 있다. ✅

---

## 선행 준비물

착수 전에 사람이 해둬야 하는 것:

| | 항목 | 필요한 Task |
|---|---|---|
| ⬜ | **사업 A Task 1~7 완료·머지** (`db-migrate` 워크플로 동작, `0037` 까지 정합) | 전부 |
| ⬜ | `gcloud` 로그인 + 대상 프로젝트 설정 | Task 2, 12 |
| ⬜ | GitHub Variable `GCP_SCHEDULER_LOCATION` | Task 12 |
| ⬜ | Secret Manager 쓰기 권한 (`secretmanager.admin` 또는 동등) | Task 2, 12 |
| ⬜ | IAM 커스텀 역할 생성 권한 (`iam.roles.create`) | Task 12 Step 9 |
| ⬜ | 로컬 https 프록시 (선택 — `__Host-` 쿠키 로컬 확인용) | Task 5 Step 8 |
| ⬜ | **스케줄러 5개 PAUSED 재개 여부 결정** (§15 Q6) | Task 8 Step 9 확인이 성립하려면 필요 |
| ⬜ | Task 14 Step 9(실제 재크롤) 운영 승인 | Task 14 (선택 Step) |

`SUPABASE_DB_PASSWORD` 는 **필요 없다** (사업 A 에서 검증 완료).

---

## 스펙에서 발견한 문제 (이 계획이 정정한 것)

| # | 스펙 | 실제 | 이 계획의 처리 |
|---|---|---|---|
| 1 | §3.5 «`Path=/admin`, `__Host-` 접두» | **배타적이다.** `__Host-` 는 `Path=/` 를 강제한다 | `__Host-` + `Path=/` 채택. 경로 격리는 `HttpOnly` 가 대신한다 (Global Constraints) |
| 2 | §9.3 «`admin_review_required` 가 `backend/app/` 에 0건» | `admin_review: {required, reason, priority}` 딕셔너리가 **12곳에 존재**한다 (`orchestrator.py:220,348,491` 외). 다만 `required` 가 전부 리터럴 `False` — `grep '"required": True'` 0건 | «신호가 없다» 가 아니라 «죽은 필드» 다. `validation_failure_reason` 을 주 근거로 쓰되 `admin_review.required` 도 함께 본다 (Task 9) |
| 3 | §5.3 이 이 사업에 `0039` 배정 | **사업 E 가 `0039`·`0040` 을 이미 가져갔다** (`2026-08-27-E-rss-official-api.md:40,46`). 사업 D 는 `0045`~`0052` | 관측 마이그레이션을 `0041` 로 옮김 (Global Constraints 의 배정표) |
| 4 | §4.2 의 `adminGate` 가 «세션 검증» 을 하는 것처럼 그려짐 | middleware 는 Edge 런타임 — service_role·`node:crypto` 사용 불가 | 게이트는 쿠키 존재만, 검증은 레이아웃·핸들러 (Global Constraints, Task 5) |
| 5 | §11 이 읽기 화면(4·5)을 관측 기반(6·7)보다 앞에 둠 | 그 논거(«쓰기 조작의 결과를 볼 창»)는 쓰기 화면에 대한 것이다. 관측은 지연이 곧 데이터 손실 | 관측을 앞으로 (실행 순서 절) |
| 6 | §7.4 가 `/recrawl/preview` 를 별도 경로로 명시 | 같은 자원의 «보기» 와 «실행» | GET/POST 로 통합 (Task 14 Step 2 주석) |
| 7 | §12.1 #9 «관리자 쿠키를 `/` 에서 읽기 시도 → 못 읽는다» | 정정 1 로 `Path=/` 가 됐고, 애초에 `HttpOnly` 라 경로와 무관하게 못 읽는다 | 시험을 대체하지 않고 사유를 남김 (자체 검토 «3. 남긴 것») |
| 8 | §6.3 이 `app_jobs` 화면을 «select 확장만 하면 된다» 는 톤으로 서술 | `app_jobs` 가 `types/database.ts` 에 **아예 없다.** `.from('app_jobs')` 가 타입 오류 | 선행 Task 로 분리 (Task 3) |
