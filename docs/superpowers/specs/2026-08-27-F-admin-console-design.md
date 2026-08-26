# 사업 F — 관리자 콘솔 · 운영 화면화 · 관측 기반

기준일: 2026-08-27
상태: 설계 (구현 전)
선행: 사업 A(보안 기반 · 인증 복구) / 후행: 없음

> 한 줄 목표: **운영자가 손으로 하던 일을 화면에서 하게 만든다.**

---

## 1. 배경

### 1.1 운영이 사람 기억과 스크립트에 얹혀 있다

이 저장소의 «운영»은 지금 전부 사람 손이다. `scripts/` 에 있는 파일 30여 개 중
절반 이상이 `SUPABASE_KEY`(service_role)를 셸에 export 하고 프로덕션 PostgREST 를
직접 두드리는 일회성 도구다. 결과는 DB 가 아니라 `scripts/_state_out.txt`,
`scripts/_review_out.txt` 같은 로컬 텍스트 파일에 쌓인다.

가장 뚜렷한 증상 세 가지.

| 증상 | 근거 |
|---|---|
| **스케줄러 재개 절차가 어디에도 없다** | `gcloud scheduler jobs pause` / `resume` 가 **저장소 전체에 0건**. 문서는 `create` 만 적어 두었다 (`docs/scheduled-crawl-runbook.md:64-67`, `docs/worker-jobs-runbook.md:114-126`). 그런데 **실제로 지금 5개가 PAUSED 다.** 되살리는 방법은 사람 기억에만 있다 |
| **파괴적 작업에 확인 절차가 없다** | `scripts/recrawl_trigger.py:51` 이 확인 프롬프트 없이 `DELETE /notices?school_id=eq.…` 를 던진다. `school_events`(`0017_school_events.sql:3-4`)·`notice_ai_translations`(`0005:3`)·`notice_cards` 가 캐스케이드로 함께 사라진다 |
| **재크롤 진행 상태가 로컬 파일에 있다** | 시작 시각이 `scripts/_recrawl_start.txt` 에 저장되고 `scripts/recrawl_monitor.py:63-64` 가 그 파일을 읽어 경과를 계산한다. 다른 사람 머신에서는 재현 불가 |

### 1.2 관리자 화면 요구사항은 이미 문서에 있다

`docs/worker-queue-architecture.md:142-146` 「다음 단계」:

```
1. `app_jobs` 상태 조회 API 추가
2. worker heartbeat/observability 추가
3. 필요 시 translation worker와 crawler worker를 완전히 별도 배포 단위로 분리
```

1번은 아직 없다. 그 자리를 `scripts/_hambak_jobstatus.py:39-74` 가
service_role 키로 대신하고 있다. **잡 큐 콘솔은 새 아이디어가 아니라
팀이 인지하고 미뤄둔 항목이다.**

### 1.3 관리자 개념이 스키마에서 뿌리 뽑혀 있다

`supabase/migrations/0012_phase1_schema_cleanup.sql` 이 관리자 관련 스키마를
한 번에 걷어냈다.

```sql
 6  drop index if exists public.notice_ai_translations_review_idx;
 8  alter table public.notice_ai_translations
 9    drop column if exists requires_admin_review,
10    drop column if exists admin_review_reason;
15  alter table public.profiles
16    drop column if exists role;
18  drop type if exists public.user_role;
```

원래 설계에는 있었다 — `0001_initial_schema.sql:3`
`create type public.user_role as enum ('parent', 'school_admin');`,
`:15` `role public.user_role not null default 'parent'`.

즉 **권한 모델과 검수 워크플로가 둘 다 없다.** 이 사업은 그 둘을 다시 세우는 일이다.

### 1.4 이 사업의 핵심 제약

사업 A 의 결정에 따라 학부모 쪽 개발 진입로 `/home` 은 **프로덕션에서 켜둔다**
(`docs/superpowers/specs/2026-08-26-security-foundation-design.md:130`, §5.2(b)).
누구나 `/home` 한 번으로 유효한 Supabase 세션을 얻는다.

> **따라서 관리자 인증은 학부모 인증 위에 얹을 수 없다.**
> 「로그인한 사용자인가」는 관리자 판정에 아무 정보도 주지 못한다.
> 이 제약이 §3 전체를 지배한다.

---

## 2. 목표 / 비목표

### 목표

1. 관리자가 **학부모와 완전히 분리된 계정**으로 별도 URL 에 로그인한다.
2. `/home` 이 열려 있어도, 그 경로로 얻은 세션으로는 관리자 화면에 **한 걸음도 못 들어간다.**
3. 잡 큐·학교 수집 상태를 화면에서 본다 (`_hambak_jobstatus.py`, `probe_school_state.py` 대체).
4. 재크롤·재추출·스케줄러 정지/재개를 화면에서 한다. 파괴적 작업은 **영향 건수를 보여준 뒤** 실행한다.
5. 화면이 보여줄 데이터가 실제로 생긴다 — 구조화 로깅, 실행 이력 누적, 검토 사유 보존.

### 비목표 (이 사업에서 하지 않는다)

- **푸시 알림** — 기능명세 4.11. 미구현이고 이 사업 범위 밖.
- **배포 승인 게이트** — `docs/ci-cd-phases.md:119-128` Phase 6. 별건.
- **FastAPI 공개 엔드포인트 전반의 인증** — `/notices/*`, `/capture/ocr` 무인증 문제
  (`docs/superpowers/specs/2026-08-26-security-foundation-design.md:46` 에서 이미 별건으로 분리됨).
  이 사업은 **새로 만드는 관리자 엔드포인트만** 책임진다.
- **학교 관계자 권한 부여** — 주면 학교 범위 제한(row scoping)이 필요하다. §15 열린 질문.
- **기능명세 ↔ 구현 불일치의 «정정»** — 화면이 **드러내기만** 한다 (§6.4). 어느 쪽에 맞출지는 운영 결정.
- **성능 실험 결과 복원** — `scripts/vertex_*.py` 5종이 전부 stdout 전용이고 untracked 다.
  `GEMINI_MAX_CONCURRENCY=32` 의 측정 근거는 소실됐다. 재측정은 별건.
- **문서 위생** — `/Users/sunnykim/…` 깨진 링크 60건 이상
  (`docs/worker-queue-architecture.md:28`, `refactor.md` 40여 건, `schema-migration-plan.md` 21건),
  `docs/supabase/schema.md` 가 0001 시점(23줄)에 멈춘 것. §10 에 목록만 남긴다.

---

## 3. 🔴 인증 설계 — 이 사업의 핵심

### 3.1 지금 인증이 어떻게 생겼는가

| 요소 | 위치 | 상태 |
|---|---|---|
| 학부모 구글 로그인 | `app/(auth)/login/actions.ts:22` `signInWithOAuth({provider:'google'})` | 구현됨 |
| OAuth 콜백 | `app/auth/callback/route.ts` | 구현됨 |
| 개발 계정 즉시 로그인 | `app/api/auth/dev-login/route.ts:43` `signInWithPassword` | 구현됨. 사업 A 가 프로덕션에서 켠다 |
| 인증 게이트 | `middleware.ts:56-64` | `auth.getUser()` → 없으면 `/login` 리다이렉트 |
| 권한(역할) 개념 | — | **없다.** `profiles.role` 은 `0012:15-16` 이 drop |

### 3.2 ⚠️ middleware 에 우회 분기가 둘 있다 — 관리자 게이트 설계의 전제

`middleware.ts` 는 인증 검사(`:56`)에 **도달하기 전에** 두 번 빠져나간다.

```typescript
19  const isTestEntryBypass = process.env.TEST_ENTRY_BYPASS === 'true'
21  if (isTestEntryBypass) { … return NextResponse.next({ request }) }   // :26

29  const isPreview = process.env.NEXT_PUBLIC_UI_PREVIEW === 'true'
30    || request.cookies.get('ui_preview')?.value === 'true'
32  if (isPreview) { return NextResponse.next({ request }) }              // :33
```

첫 번째(`TEST_ENTRY_BYPASS`)는 사업 A Task 3 이 제거한다.
**두 번째는 남는다.** 그리고 그 쿠키는 무인증 공개 라우트가 아무에게나 심어준다:

```typescript
// app/demo/route.ts:8-12
response.cookies.set('ui_preview', 'true', { path:'/', maxAge: 60*60*24*7, sameSite:'lax' })
```

> **결론: `/admin` 을 middleware 검사에만 의존시키면, `/demo` 를 한 번 방문한
> 아무나 7일간 관리자 게이트를 통과한다.** 관리자 판정은
> ① middleware 의 **가장 앞**(모든 우회 분기보다 위)에서 한 번,
> ② 각 관리자 라우트/레이아웃에서 다시 한 번 — **이중으로** 걸어야 한다.
> 이것은 선택이 아니라 실측된 코드에서 나온 요구사항이다.

`middleware.ts:70` matcher 는 `/((?!_next/static|_next/image|favicon.ico|icons|manifest.json|characters|.*\..*).*)`
이므로 `/admin` 도 이미 matcher 에 걸린다. 별도 matcher 수정은 불필요하다.

### 3.3 선택지

네 가지를 비교한다. 판정 기준은 **「`/home` 이 열려 있어도 안전한가」** 하나다.

| | 방식 | `/home` 우회 저항 | 구현량 | 계정 추가 | 감사 추적 | 자격 회전 |
|---|---|---|---|---|---|---|
| **(a)** | Supabase Auth 별도 사용자 + `profiles.role` 복원 | ⚠️ **조건부** | 소 | 대시보드 | 있음 | Supabase |
| **(b)** | 환경변수 고정 계정 + 별도 세션 쿠키 | ✅ | 최소 | 불가(1개) | 없음 | **재배포 필요** |
| **(c)** | 별도 테이블 + 해시 비밀번호 + 자체 세션 | ✅ | 중 | SQL/화면 | 있음 | 즉시 |
| **(d)** | Cloud Run IAM / IAP (인프라 레벨) | ✅✅ | 인프라 | Google 계정 | GCP 감사로그 | 즉시 |

---

#### (a) Supabase Auth 별도 사용자 + `profiles.role` 복원

관리자를 Supabase Auth 에 이메일/비번 사용자로 만들고, `profiles.role = 'admin'` 인지 본다.

**`/home` 제약 하에서의 판정: 위험하다. 두 가지 이유.**

**① 자기 승격 경로가 열려 있다.** `0001_initial_schema.sql:138-141`:

```sql
138  create policy "profiles update own"
139  on public.profiles for update
140  using (auth.uid() = id)
141  with check (auth.uid() = id);
```

Postgres RLS 는 **행 단위이지 컬럼 단위가 아니다.** 이 정책은 로그인한 사용자가
자기 `profiles` 행의 **모든 컬럼**을 갱신하도록 허용한다. `role` 컬럼을 되살리면
`/home` 으로 세션을 얻은 누구나 공개된 anon 키로

```
PATCH /rest/v1/profiles?id=eq.<자기 id>   {"role": "admin"}
```

를 던져 스스로 관리자가 된다. 막으려면 `revoke update (role) on public.profiles from authenticated`
같은 **컬럼 단위 GRANT** 회수나 `before update` 트리거로 `role` 을 고정해야 한다.
가능하지만, **안전성이 미묘한 Postgres 세부사항 하나에 걸린다.**

**② 세션 기반이 학부모와 같다.** 관리자와 학부모가 같은 쿠키 이름
(`sb-<ref>-auth-token`), 같은 도메인, 같은 갱신 경로를 쓴다. 학부모 쪽에
우회가 하나라도 생기면 관리자 표면까지 닿는다. 사업 A 가 `/home` 을
**의도적으로 열어둔** 상황에서 이 결합은 정면으로 불리하다.

부가 문제: 관리자가 실수로 `/home` 을 방문하면 세션이 개발 계정으로 덮어써진다.

---

#### (b) 환경변수 고정 계정 + 별도 세션 쿠키

`ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` 를 Secret Manager 에서 주입하고,
로그인 성공 시 앱이 서명한 별도 쿠키(예: `__Host-naranhi_admin`)를 발급한다.

**`/home` 제약 하에서의 판정: 만족한다.** Supabase 세션과 쿠키 이름·서명키·검증 경로가
전부 다르다. `/home` 이 주는 것은 `sb-…` 쿠키뿐이고, 관리자 게이트는 그것을 보지 않는다.
`ui_preview` 쿠키도 마찬가지로 무관하다(§3.2 의 «게이트를 맨 앞에» 요건은 여전히 필요).

**약점 셋.**
1. **계정이 하나뿐이다.** 여러 사람이 같은 자격을 공유하면 `admin_audit_log` 를 남겨도
   «누가» 를 알 수 없다. 재크롤이 공지를 지우는 화면에서 이건 실질적 결함이다.
2. **회전에 재배포가 필요하다.** 비밀번호를 바꾸려면 Secret 새 버전 + Cloud Run 재배포.
   사람이 떠날 때 즉시 잠글 수 없다.
3. **Cloud Run 서비스 설정에 노출된다.** env 로 넣으면 `gcloud run services describe` 로
   보인다 (`docs/content-extractor-job.md:79` 가 같은 이유로 경고한다). Secret 참조로만 넣어야 한다.

관리자가 1명으로 확정되고 당분간 늘 계획이 없다면 합리적 선택이다.

---

#### (c) 별도 테이블 + 해시 비밀번호 + 자체 세션  ← **권고**

`admin_users`(사람별 계정) + `admin_sessions`(세션 토큰) 두 테이블을 만들고,
Next.js 서버가 세션 쿠키를 발급·검증한다.

**`/home` 제약 하에서의 판정: 만족한다. 그리고 이 저장소의 기존 방어 패턴과 정확히 맞는다.**

두 테이블에 **RLS 활성 + 정책 0개**를 건다. 저장소에 선례가 둘 있다 —
`0013_school_crawl_state.sql:72`, `0036_app_jobs_rls.sql`. 이 상태는
anon/authenticated 를 전면 차단하고 service_role 만 통과시킨다.

> 그 결과: **`/home` 이 발급하는 세션의 anon 키로는 `admin_users` 테이블의
> 존재조차 확인할 수 없다.** 학부모 인증 표면 전체가 관리자 자격과 물리적으로 단절된다.

**비밀번호 해시에 새 의존성이 필요 없다.** `0001_initial_schema.sql:1` 이
`create extension if not exists "pgcrypto"` 를 이미 실행했다. `crypt()` / `gen_salt('bf')` 로
DB 안에서 해싱·검증하면, 해시가 애플리케이션 메모리로 나오지 않는다.
(참고: `package.json:12-26` 에 bcrypt/argon2 계열 없음, `backend/requirements.txt` 에도 없음.)

검증은 `security definer` RPC 하나로 감싼다 — 앱은 «맞다/틀리다»와 계정 id 만 받는다.

**비용:** 마이그레이션 1개 + 로그인 라우트 + 세션 검증 헬퍼 + 계정 추가 스크립트.
대략 200~300줄. (b) 대비 +150줄 정도이고, 그 대가로 사람별 계정·즉시 잠금·
실패 카운터·감사 추적을 얻는다.

---

#### (d) Cloud Run IAM / IAP 등 인프라 레벨 보호

요청이 애플리케이션 코드에 **닿기 전에** Google 이 신원을 검증한다.

**`/home` 제약 하에서의 판정: 가장 강하다.** middleware 의 우회 분기(§3.2)도,
`profiles` RLS 의 컬럼 단위 허점도 무관해진다. 앱 코드의 실수가 관리자 표면에 닿지 않는다.

**하지만 지금 구조에 그대로 얹을 수 없다.**

1. `naranhi-web` 은 `--allow-unauthenticated` 로 뜬 **단일 Cloud Run 서비스**다
   (`.github/workflows/deploy-cloud-run.yml:90-92`). IAM 은 서비스 단위이지 경로 단위가 아니다.
   `/admin` 만 잠글 수 없다. → **관리자 콘솔을 별도 Cloud Run 서비스로 분리**하거나,
   외부 HTTPS 로드밸런서 + IAP 경로 규칙을 세워야 한다.
2. IAP 의 신원은 **Google 계정**이다. 사용자 결정 「아이디·비밀번호를 따로 설정한다」와
   어긋난다.
3. 프로젝트에 LB·인증서·DNS 가 지금 없다. 조사 범위에서 확인되지 않았다 — **미확인**.

**결론: 1단계의 주 인증 수단으로는 부적합하다.** 다만 §11 이후 관리자 콘솔을
별도 서비스/도메인으로 떼어낼 때 **(c) 위에 겹쳐 쓰는 2중 방어**로는 매우 유효하다.

---

### 3.4 권고

> **(c) 별도 테이블 + 해시 비밀번호 + 자체 세션을 채택한다.**
> `profiles.role` 은 **복원하지 않는다** (§5).

근거 넷.

| # | 근거 |
|---|---|
| 1 | `/home` 이 여는 표면과 **자격 저장소 자체가 단절**된다 — RLS 정책 0개(`0013:72`, `0036` 선례)로 anon 키가 테이블에 닿지 못한다. (a) 처럼 컬럼 단위 GRANT 를 정확히 거는 데 안전이 걸리지 않는다 |
| 2 | 사용자 결정 「아이디·비밀번호를 따로 설정한다」를 문자 그대로 만족한다. (d) 는 Google 신원이라 어긋난다 |
| 3 | 새 의존성이 0 이다 — pgcrypto 가 `0001:1` 에서 이미 켜져 있다 |
| 4 | 파괴적 작업(공지 삭제·스케줄러 정지)의 **사람별 감사 추적**이 가능하다. (b) 는 불가능하다 |

**(b) 를 고르는 것이 정당한 경우:** 관리자가 확정적으로 1명이고, 감사 추적이 필요 없다고
운영이 판단할 때. 그때는 §5·§11 의 마이그레이션 단계가 통째로 빠진다.
(c) → (b) 는 쉽지만 (b) → (c) 는 다시 만드는 일이므로, **§15 «관리자 인원수» 답이
나오기 전에는 (c) 로 간다.**

### 3.5 세션 수명 · 2단계 인증 · 실패 잠금

관리자는 소수다. 규모에 맞춰 자른다.

| 항목 | 결정 | 근거 |
|---|---|---|
| **세션 수명** | **8시간 절대 만료. 슬라이딩 갱신 없음** | 학부모는 14일(사업 A §5.2(c))이지만 관리자는 정반대여야 한다. 하루 업무를 덮되 다음 날은 다시 로그인. 갱신을 안 붙이면 «훔친 쿠키의 최대 수명 = 8시간»이 보장된다 |
| 유휴 만료 | 30분 (선택) | 공유 PC 대비. 구현이 1줄(마지막 활동 시각 비교)이면 넣고, 아니면 생략 |
| 쿠키 속성 | `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/admin`, `__Host-` 접두 | `SameSite=Strict` 로 CSRF 표면을 줄인다. 학부모 쿠키(`sameSite:'lax'`, `path:'/'` — `app/demo/route.ts:11`)와 **의도적으로 다르게** 간다 |
| 세션 저장 | `admin_sessions` 테이블에 **토큰 해시**만 | 서버 측 즉시 무효화가 가능해야 한다. JWT 는 회수가 안 된다 |
| **2단계 인증** | **1단계에서는 하지 않는다** | 관리자 소수 + 자동 생성 고엔트로피 비밀번호 + 8시간 세션이면 잔여 위험이 작다. `admin_users.totp_secret` 컬럼 자리만 남겨 두고, 필요해지면 컬럼 1개 + 검증 50줄로 붙인다. 관리자에게 인증기 앱이 있는지 **미확인** (§15) |
| **실패 잠금** | 계정당 **5회 실패 → 15분 잠금** (`failed_attempts`, `locked_until`) | 규모상 분산 브루트포스는 현실적 위협이 아니다. 카운터 2컬럼이면 충분 |
| 응답 시간 | 성공·실패 모두 고정 지연 | 계정 존재 여부 유추(user enumeration) 차단. 실패 응답 문구도 하나로 통일 |
| 비밀번호 | **사람이 고르지 않는다.** 생성해서 전달 | 규칙(길이·기호)을 강제하는 것보다 확실하다 |

---

## 4. 접근 경로

### 4.1 `/admin` 하위 경로 vs 별도 도메인

| | 같은 서비스의 `/admin` | 별도 도메인 / 별도 서비스 |
|---|---|---|
| 배포 | 기존 `naranhi-web` 그대로 | Cloud Run 서비스 + DNS + 인증서 추가 |
| service_role 접근 | 이미 있음 (`lib/supabase/server.ts:36`) | 새로 주입 |
| 쿠키 격리 | 경로(`Path=/admin`) 격리만 | **오리진 격리** — 학부모 쪽 XSS 가 관리자 쿠키에 못 닿음 |
| (d) IAM/IAP 적용 | 불가 | 가능 |
| 관리자 표면 노출 | 공개 서비스와 동일 URL 공간 | 분리 |

**1단계는 `/admin`** — 새 인프라 없이 시작한다. 규모(§1.5 실측: notices 38 / schools 8)에서
별도 서비스는 과잉이다.

**단, 두 가지를 지금 지킨다** — 나중에 떼어낼 때 코드가 안 바뀌도록.
1. 관리자 라우트를 route group `app/(admin)/` 에 **완전히 격리**한다.
   학부모 레이아웃(`app/(app)/layout.tsx`)을 상속하지 않는다.
2. 세션 검증을 `lib/admin/session.ts` **한 파일**에 모은다.
   도메인을 옮길 때 이 파일의 쿠키 도메인 설정만 바뀐다.

### 4.2 route group 과 middleware 로 어떻게 가르는가

```
app/
  (admin)/
    admin/
      layout.tsx        ← requireAdminSession() 재검사 (이중 방어 ②)
      page.tsx          ← 대시보드
      jobs/page.tsx     ← 잡 큐 콘솔
      schools/page.tsx  ← 수집 상태
      schedulers/page.tsx
      login/page.tsx    ← 유일한 미인증 관리자 경로
  api/
    admin/…             ← 관리자 전용 Route Handler
```

`middleware.ts` 는 **함수 맨 앞**에서 갈린다:

```typescript
export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname

  // ① 관리자 경로는 다른 어떤 분기보다 먼저 판정한다.
  //    아래의 isPreview 분기(:29-34)는 무인증 /demo 가 심는 쿠키 하나로 통과되므로
  //    (app/demo/route.ts:8), 관리자 판정이 그 뒤에 오면 게이트가 없는 것과 같다.
  if (pathname.startsWith('/admin') || pathname.startsWith('/api/admin')) {
    return adminGate(request)   // /admin/login 만 통과, 나머지는 세션 검증
  }

  // ② 여기서부터 기존 학부모 흐름 (isPreview, getUser, PUBLIC_PATHS …)
}
```

`PUBLIC_PATHS`(`middleware.ts:7-15`)에 관리자 경로를 **넣지 않는다.**
`/admin/login` 예외는 `adminGate` 안에서만 처리한다 — 공개 목록에 올리면
학부모 흐름의 `startsWith` 매칭(`middleware.ts:58`)과 섞여 실수가 생긴다.

**이중 방어 ②**: `app/(admin)/admin/layout.tsx` 와 `app/api/admin/**` 의 각 핸들러가
`requireAdminSession()` 을 다시 호출한다. middleware 만 믿지 않는다 —
matcher 는 정규식이고(`middleware.ts:70`), `.*\..*` 제외 규칙 때문에
점이 들어간 경로는 middleware 를 아예 타지 않는다.

---

## 5. `profiles.role` 복원 마이그레이션

### 5.1 결론부터 — 1단계에서는 복원하지 않는다

§3.4 의 권고 (c) 를 따르면 `profiles.role` 이 필요 없다. 관리자 신원은
`admin_users` 에 있고, `profiles` 는 학부모 전용으로 남는다.

**복원하지 않는 편이 나은 적극적 이유:**
- §3.3(a) ①의 자기 승격 경로(`0001:138-141`)를 만들지 않는다.
- `0012` 가 «unused» 를 이유로 지운 컬럼을, 실제로 쓰지도 않으면서 되살리지 않는다.

**복원이 필요해지는 시점:** §15 의 «학교 관계자에게 권한을 줄 것인가» 가 «준다»로
답해질 때. 그때는 관리자(별도 체계)와 **학부모 계정에 붙는 제한된 권한**(같은 체계)이
둘 다 필요해지고, 후자가 곧 `profiles.role` 이다. 아래는 그때의 설계다.

### 5.2 복원할 경우의 설계 — enum 이 아니라 `text + CHECK`

저장소가 이 문제에서 갈려 있다. 실측:

| 대상 | 방식 | 근거 |
|---|---|---|
| `user_role` (삭제됨) | **enum** | `0001_initial_schema.sql:3` |
| `notice_source`, `notice_status`, `notice_card_type` | **enum** | `0001:4-6` |
| `schools.crawl_board_kind` | **text + CHECK** | `0002_school_crawler_state.sql:20-21` |
| `school_crawl_state.crawl_board_kind` | **text + CHECK** | `0013_school_crawl_state.sql:22-23` |
| `app_jobs.status` | **text + CHECK** | `0027_app_jobs.sql:16` |
| `children.dietary_restrictions` | **text[] + CHECK (`<@`)** | `0034_child_dietary_restrictions.sql:2,12-22` |
| `school_events.event_kinds` | **jsonb, CHECK 없음** | `0028_school_events_event_kinds.sql:2` |

**패턴이 시간순으로 뚜렷하다.** enum 은 `0001` 에만 있다. `0002` 이후 새로 생긴 열거값은
**전부 `text + CHECK`** 다. `0034` 는 다중값이라 `text[] + <@` 로, `0028` 은 다중값이면서
CHECK 를 아예 생략했다 (`event_kinds` 에는 어떤 jsonb 든 들어간다 — 편집 UI 를 만든다면
검증이 앱 책임이다).

> **권고: `text + CHECK`.** 일관성 근거는 «다수결»이 아니라 **되돌리기 비용**이다.
> Postgres enum 은 값 추가가 `alter type … add value` 이고 **값 제거가 불가능**하다.
> `0012:18` 이 `drop type if exists public.user_role` 를 별도 구문으로 써야 했던 것이
> 그 증거다. CHECK 제약은 drop 후 재생성이면 끝난다.
> `0028` 처럼 CHECK 를 생략하는 선택은 하지 않는다 — 권한 값은 오타 하나가 곧 권한 사고다.

```sql
-- (필요해질 때만) supabase/migrations/00NN_profiles_role_restore.sql
alter table public.profiles
  add column if not exists role text not null default 'parent';

-- CHECK 는 0034 의 멱등 do-block 패턴을 따른다 (0034:4-24)
--   check (role in ('parent', 'school_staff'))
--   'admin' 은 넣지 않는다 — 관리자는 admin_users 에 있다

-- ⚠️ 필수: 자기 승격 차단. 0001:138-141 의 "profiles update own" 은
--         행 단위라 role 컬럼까지 허용한다.
revoke update (role) on public.profiles from authenticated;
```

### 5.3 신규 마이그레이션 번호

**`0038` 이후를 쓴다.**

| 번호 | 예약자 |
|---|---|
| `0035` | `docs/기능명세서-자녀-개인일정.md` (`child_personal_schedules`) |
| `0036` | 사업 A — `0036_app_jobs_rls.sql` (존재 확인) |
| `0037` | 사업 A — 첨부 버킷 비공개 (계획 Task 7) |
| **`0038`** | **이 사업 — `admin_users` / `admin_sessions` / `admin_audit_log`** |
| `0039` | 이 사업 — 관측 기반 (§9: `crawl_run_history`, 검토 사유 컬럼) |

> ⚠️ `0030` 이 두 개 존재한다 (`0030_notice_ai_translations_add_translated_title.sql`,
> `0030_school_events_end_date.sql`). 사업 A 계획 Task 2 Step 3 이 이를 예외로 등록한다.
> 이 사업은 새 중복을 만들지 않는다.

### 5.4 `0038` 개요

```sql
create table if not exists public.admin_users (
  id uuid primary key default gen_random_uuid(),
  username text not null unique,
  password_hash text not null,          -- pgcrypto crypt(…, gen_salt('bf'))
  display_name text,
  is_active boolean not null default true,
  totp_secret text,                     -- 자리만 남긴다 (§3.5)
  failed_attempts integer not null default 0,
  locked_until timestamptz,
  last_login_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.admin_sessions (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid not null references public.admin_users(id) on delete cascade,
  token_hash text not null unique,      -- 원본 토큰은 쿠키에만
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.admin_audit_log (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid references public.admin_users(id) on delete set null,
  action text not null,                 -- 'recrawl' | 'scheduler_pause' | …
  target text,                          -- school_id / job name / notice_id
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- 세 테이블 모두: RLS 활성 + 정책 0개.
-- 선례 0013_school_crawl_state.sql:72, 0036_app_jobs_rls.sql
alter table public.admin_users    enable row level security;
alter table public.admin_sessions enable row level security;
alter table public.admin_audit_log enable row level security;
```

---

## 6. 화면 목록과 우선순위

근거는 전부 «지금 사람이 손으로 하는 일»이다.

### 6.1 우선순위 표

| 순위 | 화면 | 대체하는 수동 작업 | 데이터 출처 | 선행 조건 |
|---|---|---|---|---|
| **P0-1** | 관리자 로그인 · 세션 | (없음 — 신규) | `admin_users`, `admin_sessions` | `0038` |
| **P0-2** | **잡 큐 콘솔** | `scripts/_hambak_jobstatus.py:39-74` | `app_jobs` (`0027:1-17`) | `0036` 적용 후 service_role 경유 |
| **P0-3** | **학교별 수집 상태** | `scripts/probe_school_state.py:67`, `scripts/_review_schools.py` | `school_crawl_state` (`0013:1-11`) | `lib/school-crawl-state.ts` select 확장 |
| **P1-1** | **스케줄러 정지/재개** | 저장소에 절차 **0건**. 사람 기억 | Cloud Scheduler Admin API | §8, IAM |
| **P1-2** | **재크롤 트리거** (삭제 건수 확인) | `scripts/recrawl_trigger.py` | `notices`, `school_crawl_state` | §7 |
| **P1-3** | **공지 검수 · 강제 재추출** | `docs/content-extractor-job.md:137-141` gcloud | `notices`, Cloud Run Job overrides | §8 (신규 함수 필요) |
| **P2-1** | 번역 검토 큐 | (지금 아무도 안 한다) | ⚠️ **데이터 소스가 없다** | §9.3 선행 필수 |
| **P2-2** | 실행 이력 · 성공률 추이 | (지금 알 방법이 없다) | ⚠️ `crawl_run_history` 신설 | §9.2 |
| **P2-3** | 실패 알림 | (없다) | Cloud Logging 지표 | §9.1 선행 |
| **P3** | `board_watermarks` 리셋 · 공지 본문 교정 | `docs/scheduled-crawl-runbook.md:77-78`, `scripts/_dedent_notice.py` 등 | `school_crawl_state.board_watermarks`, `notices` | — |

### 6.2 규모 전제 — 페이징을 설계하지 않는다

운영 DB 실측 (2026-08-26): notices 38 / schools 8 / children 9 / profiles 10 /
notice_ai_translations 155 / **app_jobs 230** / school_events 68 / meals 102.

전부 한 페이지에 들어간다. **커서 페이징·가상 스크롤·서버 집계 캐시를 만들지 않는다.**
필요한 것은 `job_type` / `status` 필터와 정렬뿐이다.
`0027:19-20` 의 인덱스(`job_type, status, available_at, created_at`)가 이미 그 형태를 지원한다.

### 6.3 화면별 설계 요점

**P0-2 잡 큐 콘솔.** `app_jobs` 컬럼 전부를 노출한다 —
`job_type`, `job_key`, `status`, `attempts` / `max_attempts`, `available_at`,
`started_at`, `finished_at`, `last_error`, `result`.
`last_error` 는 `job_queue_service.py:256-262` 에서 **1000자로 잘려** 저장되므로
화면도 그 이상을 기대하지 않는다.
필요한 조작 2개: **재시도**(`status='queued'`, `available_at=now()`),
**포기**(`status='failed'`). 둘 다 감사 로그를 남긴다.

> ⚠️ `job_queue_service.py` 에 **목록 조회 함수도 통계 함수도 없다.**
> 조회 계열은 `completed_recently`(:101, 불리언), `latest_job`(:119, 특정 `job_key` 단건),
> `claim`(:198, 선점 부작용 포함) 셋뿐이다. 콘솔용 조회는 새로 만들어야 한다 (§7).

**P0-3 학교별 수집 상태.** `school_crawl_state` 전 컬럼 +
`crawl_board_kind` 를 **오선택이 보이도록** 표시한다 —
값은 `family_notice` / `announcement_fallback` / `unknown` 셋 (`0013:23`).
`announcement_fallback` 은 «가정통신문 게시판을 못 찾아 일반 공지로 대체»라는 뜻이고,
`unknown` 은 «아직 못 정함»이다. 둘 다 **눈에 띄는 배지**로 띄운다.
지금은 `scripts/probe_school_state.py:67` 이 텍스트로 찍어야만 보인다.

> ⚠️ 선행 작업 1건: `lib/school-crawl-state.ts:47` 과 `:74` 의 select 문자열에
> **`board_watermarks` 가 빠져 있다** (`0033` 에서 추가된 컬럼).
> 프론트가 watermark 를 아예 못 본다. 이것이 `docs/scheduled-crawl-runbook.md:77-78` 이
> «SQL 로 비우거나 낮춘다»고 적은 이유다. P3 화면을 만들려면 이 문자열부터 늘려야 한다.
>
> 그리고 이 파일에는 **UPDATE 경로가 없다** — INSERT(`:68-72`)와 SELECT 뿐이다.
> 상태 갱신은 전적으로 백엔드/스크립트 몫이다.

**P1-2 재크롤 트리거 — 확인 다이얼로그가 본체다.**
`scripts/recrawl_trigger.py` 가 하는 일은 4단계다.

| 단계 | 스크립트 위치 | 동작 |
|---|---|---|
| ① | `:46-48` | 삭제 전 `notices` 건수 스냅샷 |
| ② | `:51` | **`DELETE /notices?school_id=eq.…`** — 주석: "cascades to translations/cards/events" |
| ③ | `:56-57` | `school_crawl_state.board_watermarks` 를 `{}` 로 PATCH |
| ④ | `:61-62` | `POST /crawler/schools/{id}/discover-board` (`X-Internal-Token`) |

화면은 ① 을 **먼저 보여주고 사람이 그 숫자를 확인한 뒤에** ②③④ 를 실행한다.
숫자는 notices 뿐 아니라 캐스케이드 대상까지 센다 —
`notice_ai_translations`(`0005:3` cascade), `school_events`(`0017:3-4` cascade),
`notice_cards`. 「공지 38건 · 번역 155건 · 일정 68건이 삭제됩니다」가 보여야 한다.

> ④ 는 이미 `lib/school-crawler-trigger.ts:25-27` `triggerInitialSchoolCrawl` 로 있다.
> 스크립트에만 있고 lib 에 없는 것은 **② notices DELETE 와 ③ watermark 리셋** 둘뿐이다.

**P1-3 공지 검수 · 강제 재추출.** 지금은 사람이 이걸 친다
(`docs/content-extractor-job.md:137-141`):

```
gcloud run jobs execute naranhi-content-extractor \
  --args="--notice-id=<notice_id>,--force,--max-notices=1" --wait
```

화면에서는 공지 목록의 행마다 «재추출» 버튼. 백엔드가 Cloud Run Job overrides 로
같은 args 를 넘긴다 (§8 — **지금 코드로는 안 된다**).

**P2-1 번역 검토 큐 — 데이터 소스가 지금 존재하지 않는다.** §9.3 참조.

### 6.4 화면이 드러내야 할 기능명세 ↔ 구현 불일치

관리자 화면의 부수 효과 중 하나는 «명세와 실제가 다르다»를 눈에 보이게 하는 것이다.
정정은 이 사업의 범위 밖이지만(§2), **화면에는 실제값이 나와야 한다.**

| 명세 | 실제 |
|---|---|
| 3.1.1 **평일** 하루 2회 06:30 / 18:00 (`docs/기능명세서.md:154`) | 매일 06:00 / 18:00 — `0 6 * * *` / `0 18 * * *`, 요일 제한 없음 (`docs/scheduled-crawl-runbook.md:64-65`) |
| 4.2.1 / 4.3.1 급식·시간표 06:00 정기수집 + 08:00 재시도 | **해당 Scheduler 잡이 없다.** 화면 진입 시 즉시 조회 |
| 3.1.7 / 4.4.1 실패 로그 저장 | 전용 실패 로그 테이블 없음 |
| 4.11 푸시 알림 | 미구현 (§2 비목표) |

스케줄러 화면은 **문서가 아니라 Cloud Scheduler API 가 돌려준 실제 cron 과 state**를
표시한다. 문서와 실운영이 이미 어긋나 있다 —
문서는 `naranhi-content-extractor-1900`(`docs/scheduled-crawl-runbook.md:67`),
`naranhi-translation-worker-backstop`(`docs/worker-jobs-runbook.md:114`) 로 적었지만
실제 이름은 다르다고 보고됐다 (정확한 실운영 이름 **미확인** — API 목록으로 확인 후 상수화).

---

## 7. 백엔드 API 설계

### 7.1 판단 — 조회는 Next.js, GCP 제어는 FastAPI

```
브라우저
  │  __Host-naranhi_admin 쿠키
  ▼
Next.js  /api/admin/*   ← requireAdminSession() (이중 방어 ②)
  ├─ 조회·DB 조작 : service_role 로 Supabase 직접
  └─ GCP 제어    : X-Admin-Token 헤더로 FastAPI /admin/* 호출
                        │  ADC
                        ▼
                   run.jobs.run / cloudscheduler.jobs.pause|resume
```

### 7.2 왜 조회를 FastAPI 에 두지 않는가

| 근거 | 실측 |
|---|---|
| **FastAPI 는 지금 사실상 공개 표면이다** | Cloud Run `naranhi-api` 가 `--allow-unauthenticated`. `/notices`(`backend/app/api/notices.py:47`), `/notices/{id}/analyze`(:61), `/notices/translate-text`(:76), `/notices/{id}/translate`(:96), `/notices/{id}/translate/status`(:199), `/capture/ocr`(`backend/app/api/capture.py:13`), `/health`(`backend/app/api/health.py:8`) 전부 인증 의존성이 없다. 이게 실증된 사례가 있다 — `scripts/_hambak_enqueue.py` 는 **Supabase 키를 전혀 안 쓰고** prod 번역 잡을 밀어넣는다 |
| 유일한 인증도 fail-open 분기가 있다 | `backend/app/api/crawler.py:18-37` `_require_internal_token` 만 인증이 걸려 있고, 그것도 토큰 미설정 + `ENVIRONMENT=local` 이면 `return` 으로 통과한다 (`:25-26`) |
| **Next.js 쪽엔 이미 같은 패턴의 선례가 있다** | `app/api/schools/[schoolId]/crawl/route.ts` — `:29` 인증 → `:34-48` 소유권 검사 → `:51` `createSupabaseServiceClient()`. 관리자 라우트는 여기서 «소유권 검사»를 «관리자 세션 검사»로 바꾼 것이다 |
| **service_role 경유가 강제된다** | `app_jobs`(`0036`)와 `school_crawl_state`(`0013:72`)는 RLS 활성 + 정책 0개다. 브라우저 Supabase 클라이언트로는 **아예 못 읽는다.** `school_events` 도 RLS 정책이 «내 자녀의 학교»뿐이라(`0017:86-95`) 관리자는 못 본다. 서버 경유는 선택이 아니라 제약이다 |

**반대로 GCP 제어는 FastAPI 에 둔다.** `backend/app/services/worker_trigger.py:87-108` 이
이미 ADC 로 `run.jobs.run` 을 호출하고, `naranhi-api` 런타임 SA 에 그 권한이 있다
(`docs/worker-jobs-runbook.md:72-82`). 프론트 SA 에 GCP 권한을 새로 주는 것보다
**이미 권한을 가진 쪽에 라우터를 추가**하는 편이 권한 확산을 막는다.

### 7.3 새 FastAPI 관리자 라우터 — 기존 토큰을 재사용하지 않는다

`/admin/*` prefix 로 새 라우터를 만들되, **`_require_internal_token` 을 재사용하지 않는다.**

이유: `crawler.py:25-26` 의 local 예외는 «크롤 트리거» 에는 편의지만
«스케줄러 정지» 에는 허용될 수 없는 fail-open 이다.

새 의존성 `_require_admin_token` 의 규칙:

| 조건 | 응답 |
|---|---|
| `ADMIN_API_TOKEN` 미설정 | **환경 불문 503** — local 예외 없음 |
| 헤더 없음 / 불일치 | 401 (`secrets.compare_digest`) |
| 일치 | 통과 |

`ADMIN_API_TOKEN` 은 `backend/app/core/config.py` 에 필드를 추가하고
Secret Manager 로 주입한다 (`crawler_internal_token` 이 `config.py:65-68` 에 있는 것과 같은 형태).

> **토큰은 브라우저에 절대 가지 않는다.** 호출자는 Next.js **서버**뿐이다.
> 클라이언트 컴포넌트에서 FastAPI `/admin/*` 를 직접 부르는 코드를 만들지 않는다.

### 7.4 엔드포인트 목록

**Next.js Route Handler** (`app/api/admin/`)

| 경로 | 메서드 | 하는 일 |
|---|---|---|
| `/api/admin/login` | POST | 자격 검증 → `admin_sessions` 발급 → 쿠키 |
| `/api/admin/logout` | POST | 세션 `revoked_at` 설정 |
| `/api/admin/jobs` | GET | `app_jobs` 목록 (필터: `job_type`, `status`) |
| `/api/admin/jobs/[id]/retry` | POST | `status='queued'`, `available_at=now()` |
| `/api/admin/schools` | GET | `schools` + `school_crawl_state` 조인 |
| `/api/admin/schools/[id]/recrawl/preview` | GET | **삭제 예정 건수** (notices / translations / events) |
| `/api/admin/schools/[id]/recrawl` | POST | ①②③④ 실행 + 감사 로그 |
| `/api/admin/notices/[id]/reextract` | POST | → FastAPI `/admin/jobs/extractor/run` |
| `/api/admin/schedulers` | GET | → FastAPI `/admin/schedulers` |
| `/api/admin/schedulers/[name]/pause\|resume` | POST | → FastAPI, 감사 로그 |

**FastAPI** (`backend/app/api/admin.py`, prefix `/admin`, 전부 `Depends(_require_admin_token)`)

| 경로 | 메서드 | 하는 일 |
|---|---|---|
| `/admin/schedulers` | GET | Cloud Scheduler 잡 목록 + `state` + `schedule` |
| `/admin/schedulers/{name}:pause` | POST | 화이트리스트 검사 후 pause |
| `/admin/schedulers/{name}:resume` | POST | 화이트리스트 검사 후 resume |
| `/admin/jobs/{job}/run` | POST | Cloud Run Job 실행 (**args overrides 지원** — §8) |

---

## 8. `run.jobs.run` / Scheduler 제어를 어디서 할지

프론트에서 GCP Admin API 를 직접 부를 수 없다 — ADC 자격이 브라우저에 없고,
있어서도 안 된다. 전부 §7.3 의 FastAPI `/admin/*` 를 경유한다.

### 8.1 Cloud Run Job 실행 — 지금 코드로는 부족하다

`backend/app/services/worker_trigger.py:87-108` `_post_run_job` 은 본문이 **리터럴 `json={}`** 이다.

```python
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {credentials.token}", …},
        json={},                      # ← overrides 를 전혀 쓰지 않는다
        timeout=10.0,
    )
```

Cloud Run v2 `jobs.run` 이 지원하는 `overrides.containerOverrides[].args` 를 쓰지 않으므로,
깨워진 Job 은 **배포 시점에 고정된 `--args`** 로만 돈다
(예: `.github/workflows/deploy-api-cloud-run.yml:111`, `:126`).
그래서 「공지 1건 강제 재추출」이 지금 **수동 gcloud 밖에 방법이 없다**
(`docs/content-extractor-job.md:137-141`).

**설계: 기존 함수를 확장하지 말고 별도 함수를 만든다.**

이유가 셋이다. `trigger_worker_for_job_type`(`worker_trigger.py:57-84`)은
① 인메모리 디바운스(`:45-54`)가 걸려 있고 — 관리자가 누른 버튼이 조용히 무시되면 안 된다.
② `except Exception` 으로 **모든 실패를 삼키고 `False` 를 돌려준다** — 관리자에게는
실패 사유가 그대로 보여야 한다.
③ `WORKER_TRIGGER_ENABLED`(`config.py:177-180`) 가 꺼져 있으면 no-op 이다 —
관리자 조작은 이 스위치와 무관해야 한다.

신규 `run_job_with_args(job_name, args: list[str]) -> RunResult` 는
디바운스 없음 / 예외 전파 / `overrides` 채움 / 실행 이름(operation) 반환.

### 8.2 Cloud Scheduler 제어

| 항목 | 내용 |
|---|---|
| 목록 | `GET https://cloudscheduler.googleapis.com/v1/projects/{p}/locations/{l}/jobs` |
| 정지 | `POST …/jobs/{job}:pause` |
| 재개 | `POST …/jobs/{job}:resume` |
| 인증 | ADC — `worker_trigger.py:91-93` 과 같은 방식 (`google.auth.default(scopes=[cloud-platform])`) |
| 필요 IAM | `cloudscheduler.jobs.list` / `.get` / `.pause` / `.resume` — **커스텀 역할**로 최소화. `roles/cloudscheduler.admin` 은 생성·삭제까지 준다 |
| 부여 대상 | `naranhi-api` 런타임 SA (`docs/worker-jobs-runbook.md:67-68` 로 확인 가능) |

**⚠️ 화이트리스트를 코드 상수로 고정한다.** 조작 가능한 잡 이름을 API 인자로
자유롭게 받지 않는다. 안 그러면 관리자 콘솔이 **GCP 프로젝트 전체의 스케줄러 조작 창구**가 된다.

```python
# 실운영 이름으로 확정 후 채운다 (현재 문서와 실제가 어긋나 있음 — §6.4)
CONTROLLABLE_SCHEDULERS = frozenset({ … })
```

**⚠️ location 주의.** Cloud Scheduler 잡의 location 이 Cloud Run region(`asia-northeast3`)과
같은지 **미확인**이다. 목록 API 응답에서 확인한 뒤 상수화한다.

### 8.3 이 화면이 메우는 공백

스케줄러 제어를 화면에 올리면, §1.1 의 첫 번째 증상이 사라진다 —
**절차가 코드가 되므로 사람 기억에 남을 필요가 없다.**
현재 PAUSED 상태인 5개도 화면에서 상태를 보고 재개할 수 있다.
반대 위험(잘못 눌러 수집이 조용히 멈춤)은 §13 에서 다룬다.

---

## 9. 관측 기반 마련

**화면이 보여줄 데이터가 없으면 화면도 없다.** §6 의 P2 세 개는 전부 여기에 걸려 있다.

### 9.1 구조화 로깅 전환

지금 Job 진입점들이 전부 평문이다.

| 파일:줄 | 현재 |
|---|---|
| `backend/app/jobs/crawler_worker.py:175` | `logging.basicConfig(level=INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")` |
| `backend/app/jobs/translation_worker.py:142` | 동일 |
| `backend/app/jobs/scheduled_school_crawler.py:52` | `basicConfig(...)` |
| `backend/app/jobs/scheduled_content_extractor.py:53` | `basicConfig(...)` |
| `backend/app/main.py:14` | `basicConfig(...)` |
| `backend/app/worker_main.py:77` | `basicConfig(...)` |

평문이면 Cloud Logging 의 `severity` 매핑과 구조화 필드를 못 탄다 →
**로그 기반 지표를 만들 수 없고 심각도 필터도 못 건다.** §9.4 의 알림이 여기에 막혀 있다.

**최소 구현:** `logging.Formatter` 서브클래스 하나(~30줄)가
`{"severity": ..., "message": ..., "logger": ..., "job_type": ...}` JSON 한 줄을 찍는다.
새 의존성 없음. 6개 진입점의 `basicConfig` 를 공용 `setup_logging()` 호출로 교체한다.

### 9.2 실행 이력을 DB 에 누적한다 — 역사적 성공률의 유일한 길

크롤 실행 요약이 지금 **stdout JSON 한 줄로만 나가고 사라진다.**
`backend/app/jobs/scheduled_school_crawler.py:40-48` 이 `json.dumps(...)` 로 찍고
`summary.exit_code()` 를 돌려주는 게 전부다.

요약 구조는 이미 잘 정의돼 있다 —
`backend/app/services/scheduled_crawler_service.py:57-78` `ScheduledCrawlerSummary` 14개 키
(`started_at`, `finished_at`, `dry_run`, `force`, `total_registered`, `selected_count`,
`skipped_count`, `processed_count`, `success_count`, `failure_count`, `success_rate`,
`alarm`, `targets[]`, `results[]`).

**설계: 신규 테이블 `crawl_run_history` 에 이 14개 키를 그대로 저장한다.**
Job 종료 직전 insert 1회. 이것이 §6 P2-2 «성공률 추이» 화면의 유일한 데이터 소스다.

**⚠️ 화면이 반드시 구분해야 할 두 가지 함정** (둘 다 실측된 코드 동작이다):

| 함정 | 근거 | 화면이 할 일 |
|---|---|---|
| **아무것도 안 돌아도 «성공»으로 보고된다** | `scheduled_crawler_service.py:335-336` — `success_rate = success_count/processed if processed else 1.0`, `alarm = bool(processed and success_rate < threshold)`. `processed == 0` 이면 성공률 1.0, alarm False | `processed_count == 0` 을 «성공»이 아니라 «미실행»으로 표시 |
| **exit 1 의 사유가 두 가지로 겹친다** | `:77-78` `return 1 if self.alarm else 0` (성공률 미달) vs `scheduled_school_crawler.py:60-73` 예외 시 stderr + `1` (크래시) | 이력에 `outcome` 을 명시적으로 기록해 구분 |

부가: `alarm` 은 이름이 «fail_rate» 인 임계치와 비교하지만 실제로는 **성공률**과 비교한다
(`CRAWLER_SCHEDULE_FAIL_RATE_THRESHOLD`, `config.py:106-111`, 기본 0.5).
오독하기 쉬우니 화면 라벨에는 «성공률 임계치»라고 쓴다.

### 9.3 ⚠️ 번역 검토 큐 — 데이터 소스가 지금 **존재하지 않는다**

이 항목은 요구사항 중 유일하게 «화면을 만들면 되는» 게 아니다.
**신호가 코드에서 사라졌고, 담을 컬럼도 없다.** 실측 경과는 다음과 같다.

| 단계 | 사실 | 근거 |
|---|---|---|
| ① 원래 있었다 | `validation_status text not null default 'human_review_required' check in ('passed','human_review_required','failed')`, `requires_admin_review boolean`, `admin_review_reason text` | `0005_notice_ai_translations.sql:14-17` |
| ② 검수 컬럼이 삭제됐다 | `requires_admin_review`, `admin_review_reason` drop + 검토 인덱스 drop | `0012:6-10` |
| ③ 사유를 담던 컬럼도 삭제됐다 | `alter table … drop column if exists metadata;` | `0020_notice_ai_translations_drop_metadata.sql:1-2` |
| ④ **`admin_review_required` 상태값 자체가 코드에서 사라졌다** | `backend/app/` 전체 grep 결과 **0건**. 남아 있는 건 문서(`docs/translation-quality.md:166`)와 과거 실험 산출물뿐 | 대체 방침: `.agents/translation-quality/iterations/2026-06-02_iter-codex-001/engineering/improvement-plan.md:66-68` |
| ⑤ **대체 신호마저 덮어써진다** | 최종 번역문이 있으면 `validation_status` 를 **무조건 `'passed'` 로 강제**하고, 실패 사유는 평문 `LOGGER.warning` 으로만 남긴다 | `backend/app/services/notice_service.py:778-787` |

```python
# backend/app/services/notice_service.py:778-787
        if _optional_str(pipeline_result.get("final_translation")):
            validation_status = "passed"
            metadata["validation_status"] = validation_status
            if metadata.get("validation_failure_reason"):
                LOGGER.warning(
                    "notice translation saved with validation warning: notice_id=%s target_language=%s reason=%s",
                    …
```

> **정리: 안전장치는 동작하지만 출력을 받는 곳이 아무 데도 없다.**
> `validation_status` 컬럼은 살아 있으나(0012 는 이걸 지우지 않았다) 실질적으로 항상
> `'passed'` 가 들어가고, 진짜 사유(`validation_failure_reason`)는 §9.1 미해결 상태의
> **평문 로그 한 줄**로만 존재한다. 검색도 집계도 안 된다.

**따라서 화면보다 이것이 선행한다** (마이그레이션 `0039`):

```sql
alter table public.notice_ai_translations
  add column if not exists needs_review  boolean not null default false,
  add column if not exists review_reason text;
```

그리고 `notice_service.py:778-787` 을 고친다 — `validation_status` 를 `'passed'` 로
덮어쓰되 **`needs_review = true` 와 `review_reason` 을 함께 기록**한다.
번역문은 그대로 사용자에게 나가고(현재 동작 유지), 검토 큐에도 올라간다.

부분 인덱스 하나면 조회가 끝난다 — `0005:26-27` 이 지웠던 인덱스와 같은 역할이다.

```sql
create index if not exists notice_ai_translations_needs_review_idx
on public.notice_ai_translations (needs_review) where needs_review;
```

### 9.4 실패 알림

지금 없다. 정기 크롤러가 exit 1 을 내지만(`scheduled_crawler_service.py:77-78`)
**그 exit code 를 감시하는 알림이 없다.**

| 알림 | 조건 | 선행 |
|---|---|---|
| Cloud Run Job 실행 실패 | 실행 종료 상태 ≠ 성공 | 없음 — 지금도 만들 수 있다 |
| 크롤 성공률 미달 | `crawl_run_history.alarm = true` | §9.2 |
| 잡 큐 적체 | `app_jobs` 에 `failed` 급증 / `queued` 가 오래 정체 | 없음 |
| 번역 검토 대기 누적 | `needs_review` 건수 임계 초과 | §9.3 |

로그 기반 지표(`severity` 필터)를 쓰는 알림은 **§9.1 이 선행**이다.
`docs/ci-cd-phases.md:126-128` 이 «Sentry 또는 Google Error Reporting 연동 / uptime check /
배포 실패 알림»을 Phase 6 으로 적어둔 것과 겹치지만, 이 사업은 그중
**Job 실패 알림 한 갈래만** 가져온다. 나머지는 §2 비목표.

---

## 10. 범위 밖으로 미룰 것

| 항목 | 왜 미루는가 |
|---|---|
| **푸시 알림** (기능명세 4.11) | 별개 사업. 관리자 화면과 무관 |
| **배포 승인 게이트** (`docs/ci-cd-phases.md:125` GitHub Environments approval) | `main` push 즉시 프로덕션 배포인 것은 사실이지만, 이 사업이 고칠 문제가 아니다 |
| **FastAPI 공개 엔드포인트 전반의 인증** | 사업 A 가 이미 별건으로 분리(`…security-foundation-design.md:46`). 이 사업은 **새 관리자 엔드포인트만** 책임진다 |
| **학교 관계자 권한** | 주면 학교 범위 제한(row scoping)이 필요하고 `profiles.role` 복원이 따라온다 (§5.2). §15 답이 나온 뒤 |
| **명세 ↔ 구현 불일치의 정정** | 화면은 **드러내기만** 한다 (§6.4). 어느 쪽에 맞출지는 운영 결정 |
| **성능 실험 결과 복원** | `scripts/vertex_*.py` 5종이 전부 stdout 전용이고 untracked. `GEMINI_MAX_CONCURRENCY=32` 근거 소실. 재측정은 별건 |
| **문서 위생** | 깨진 절대경로 60건 이상 (`docs/worker-queue-architecture.md:28`, `refactor.md` 40여 건, `schema-migration-plan.md` 21건 — 전부 `/Users/sunnykim/naranhi-project/…`). `docs/supabase/schema.md` 가 0001 시점 23줄에 멈춤. 일괄 상대경로 치환이면 되지만 이 사업 범위 아님 |
| **`lib/supabase/server.ts` 의 `server-only` 누락** | service_role 팩토리(`:36`)가 `import 'server-only'` 없이 노출돼 있다. 비교: `lib/school-crawl-state.ts:1`, `lib/school-crawler-trigger.ts:1` 은 선언함. 사업 D 소관이나, §13 위험표에 남긴다 |
| **staging 환경 분리** | Phase 6 |

---

## 11. 배포 순서

되돌리기 쉬운 것부터. 각 배포는 단독 롤백 가능하다.

| 배포 | 내용 | 확인 |
|---|---|---|
| **0** | (선행) 사업 A `0036`·`0037` 적용 완료, `db-migrate` 워크플로 동작 | `supabase migration list` 정합 |
| **1** | `0038` — `admin_users` / `admin_sessions` / `admin_audit_log` (RLS 활성, 정책 0개) | anon 키로 세 테이블 조회 → 0행 또는 거부 |
| **2** | 관리자 계정 1개 생성 (pgcrypto `crypt`) + 자격 전달 | SQL 로 `crypt(입력, password_hash) = password_hash` 확인 |
| **3** | `middleware.ts` 관리자 게이트 (**맨 앞**) + `lib/admin/session.ts` + `/admin/login` | 로그인 성공, 비로그인 `/admin` → 로그인 화면 |
| **4** | **P0-2 잡 큐 콘솔** (읽기 전용) | `app_jobs` 230행이 화면에 나온다 |
| **5** | **P0-3 학교 수집 상태** (읽기 전용) + `lib/school-crawl-state.ts` select 에 `board_watermarks` 추가 | 학교 8개, `crawl_board_kind` 배지 표시 |
| **6** | §9.1 구조화 로깅 (진입점 6개) | Cloud Logging 에서 severity 필터 동작 |
| **7** | §9.2 `crawl_run_history` + Job 종료 시 insert | 다음 정기 실행 후 행 1개 |
| **8** | FastAPI `/admin/*` 라우터 + `_require_admin_token` + IAM(scheduler 커스텀 역할) | 토큰 없이 호출 → 503/401 |
| **9** | **P1-1 스케줄러 정지/재개** (화이트리스트) | 목록에 실제 state 표시, pause→resume 왕복 |
| **10** | **P1-2 재크롤** (미리보기 → 확인 → 실행) + 감사 로그 | 미리보기 건수 = 실제 삭제 건수 |
| **11** | §8.1 `run_job_with_args` + **P1-3 강제 재추출** | 공지 1건 재추출이 화면에서 완료 |
| **12** | `0039` — `needs_review` / `review_reason` + `notice_service.py:778-787` 수정 | 신규 번역에 값이 채워진다 |
| **13** | **P2-1 검토 큐** + §9.4 알림 | 검토 대기 목록 표시, 실패 알림 수신 |

**4·5 를 9·10·11 보다 앞에 두는 이유:** 읽기 전용 화면이 먼저 있어야
**쓰기 조작의 결과를 화면에서 확인할 수 있다.** 반대 순서면 스케줄러를 정지시켜 놓고
그게 반영됐는지 확인할 방법이 없다.

**12 가 13 의 앞인 이유:** 검토 큐는 §9.3 의 컬럼과 쓰기 경로 없이는 빈 화면이다.

---

## 12. 검증

### 12.1 비인가 접근 — 이 사업의 핵심 검증

| # | 시험 | 통과 기준 |
|---|---|---|
| 1 | 시크릿창에서 `/admin` 접속 | `/admin/login` 으로 이동. 대시보드 내용이 **한 글자도** 응답에 없다 |
| 2 | **`/home` 으로 학부모 세션 획득 후 `/admin`** | 거부. §1.4 의 핵심 제약 검증 |
| 3 | **`/demo` 방문(`ui_preview=true`) 후 `/admin`** | 거부. `middleware.ts:29-34` 구멍 검증 (§3.2) |
| 4 | 학부모 세션으로 `/api/admin/jobs` 직접 호출 | 401. HTML 리다이렉트가 아니라 JSON 401 이어야 한다 |
| 5 | anon 키로 `/rest/v1/admin_users?select=id&limit=1` | `Content-Range` 가 `*/0`, 본문 `[]` (또는 거부) |
| 6 | anon 키로 `/rest/v1/admin_sessions`, `/rest/v1/admin_audit_log` | 동일 |
| 7 | 관리자 쿠키 없이 `/api/admin/schedulers` | 401 |
| 8 | FastAPI `/admin/schedulers` 를 토큰 없이 직접 호출 | **503 또는 401.** 200 이면 §7.3 fail-open 이 재발한 것 |
| 9 | 관리자 세션 쿠키를 학부모 도메인 경로(`/`)에서 읽기 시도 | 못 읽는다 (`Path=/admin`, `HttpOnly`) |
| 10 | 세션 발급 8시간 + 1분 후 접근 | 로그인 화면 |
| 11 | 로그아웃 후 같은 쿠키 재사용 | 거부 (`revoked_at`) |
| 12 | 비밀번호 5회 오입력 → 6회째 **정답** | 잠금(15분). 정답이어도 거부되어야 한다 |
| 13 | 존재하지 않는 계정 vs 존재하는 계정 오답 | 응답 본문·상태코드·소요시간이 구별되지 않는다 |
| 14 | (`profiles.role` 을 복원했다면) 학부모 세션으로 `PATCH /rest/v1/profiles {"role":"admin"}` | 거부. §5.2 의 `revoke update (role)` 검증 |

### 12.2 기능

| 항목 | 방법 | 통과 기준 |
|---|---|---|
| 잡 큐 콘솔 | 화면 vs `scripts/_hambak_jobstatus.py` | 두 결과가 일치 |
| 잡 재시도 | `failed` 잡 1건 재시도 | `status='queued'`, 워커가 집어감 |
| 학교 상태 | 화면 vs `scripts/probe_school_state.py` | `crawl_board_kind` 포함 일치 |
| **재크롤 미리보기** | 미리보기 건수 기록 → 실행 → 실제 삭제 건수 | **두 수가 같다.** 다르면 캐스케이드 계산이 틀렸다 |
| 재크롤 실행 | 실행 후 discover-board 큐 확인 | `app_jobs` 에 `school-discovery:{id}` 생성 |
| 스케줄러 목록 | 화면 vs `gcloud scheduler jobs list` | 이름·cron·state 일치 (문서값이 아니라 API 값) |
| 스케줄러 pause→resume | 왕복 | state 가 `PAUSED` → `ENABLED` |
| 화이트리스트 | 목록에 없는 잡 이름으로 API 직접 호출 | 거부 |
| 강제 재추출 | 공지 1건 재추출 | `docs/content-extractor-job.md:137-141` 수동 실행과 같은 결과 |
| 감사 로그 | 파괴적 작업 3종 실행 후 조회 | 3행, 각각 관리자 id·대상·시각 |
| 구조화 로깅 | Cloud Logging 에서 `severity=ERROR` 필터 | 결과가 나온다 (지금은 안 나온다) |
| 실행 이력 | 정기 크롤 1회 후 | `crawl_run_history` 1행, `processed_count=0` 이면 «미실행» 표시 |
| 검토 큐 | 번역 1건을 게이트 실패시켜 실행 | `needs_review=true` + `review_reason` 기록, 화면에 표시 |

### 12.3 회귀

| 항목 | 통과 기준 |
|---|---|
| 학부모 흐름 | `/home` → 홈, 공지 목록·번역 정상 |
| `middleware.ts` 재배치 | 학부모 인증·리다이렉트 동작 불변 |
| `notice_service.py` 수정 (`0039`) | 번역문은 그대로 사용자에게 나간다 — `needs_review` 는 **표시만** 바꾼다 |
| 백엔드 테스트 | `PYTHONPATH=backend python -m unittest discover backend/tests` 전부 통과 |
| 프론트 | `npm run typecheck && npm run build` — 프론트 테스트 러너는 없다 |

---

## 13. 위험과 롤백

### 13.1 ⚠️ 관리자 화면 자체가 새로운 공격면이다

이 사업은 **파괴적 능력을 하나의 웹 창구에 모은다.** 지금까지는 그 능력이
「service_role 키를 셸에 export 할 수 있는 사람」에게만 있었고, 그건 실질적으로
GCP Secret 접근 권한과 같았다. 이제는 **비밀번호 하나**로 같은 일을 할 수 있게 된다.

모이는 능력의 실제 파괴력:

| 조작 | 결과 |
|---|---|
| 재크롤 | 한 학교의 **공지 전체 + 번역 + 카드 + 일정**이 캐스케이드로 삭제 (`recrawl_trigger.py:51`, `0017:3-4`, `0005:3`) |
| 스케줄러 정지 | 수집이 **조용히** 멈춘다. 지금 5개가 그 상태인데 아무도 알림을 못 받고 있다 |
| Job 강제 실행 | Gemini 호출 비용 발생 |

| 위험 | 영향 | 완화 |
|---|---|---|
| **관리자 세션 탈취** | 위 전부 | 8시간 절대 만료·갱신 없음(§3.5). `HttpOnly`+`Secure`+`SameSite=Strict`+`Path=/admin`. 세션을 DB 에 두어 즉시 회수 가능 |
| **`middleware.ts` 우회 분기로 게이트 통과** | 인증 없이 콘솔 전체 | §3.2 — 관리자 판정을 **모든 분기보다 앞**에 + 라우트/레이아웃 이중 검사. §12.1 #3 이 이걸 시험한다 |
| **학부모 표면의 취약점이 관리자에 전이** | 권한 상승 | 자격 저장소를 물리적으로 분리(§3.4). 쿠키 이름·경로·서명키가 전부 다르다. `profiles.role` 을 복원하지 않아 자기 승격 경로를 만들지 않는다 |
| **실수로 누른 파괴적 버튼** | 공지 소실 | ① 미리보기 필수(§6.3) ② 확인 다이얼로그에 **실제 영향 건수** ③ 감사 로그 ④ 되돌릴 수 없는 작업은 시각적으로 구분 |
| **잘못된 pause 로 수집이 조용히 멈춤** | 며칠간 미수집 | 대시보드 최상단에 **«마지막 성공 실행 시각»** 상시 표시 + PAUSED 배지. §9.4 «잡 큐 적체» 알림 |
| **service_role 키가 관리자 라우트 전반에 노출** | RLS 전면 우회 | 관리자 라우트를 `app/(admin)` + `app/api/admin` 로 격리. ⚠️ `lib/supabase/server.ts` 에 `import 'server-only'` 가 없다 — 이 사업에서 **한 줄 추가**한다 (범위 최소 예외) |
| **GCP 권한 확산** | 콘솔이 프로젝트 전체 조작 창구화 | scheduler 는 **커스텀 역할**(list/get/pause/resume)만. Job 이름·스케줄러 이름 **화이트리스트 상수**(§8.2) |
| **`ADMIN_API_TOKEN` 유출** | FastAPI `/admin/*` 직접 호출 | Secret Manager 로만 주입, env 인라인 금지 (`docs/content-extractor-job.md:79` 와 같은 이유). 호출자는 Next.js 서버뿐 — 브라우저에 절대 내려보내지 않는다 |
| **비밀번호 공유로 감사 추적 무력화** | «누가» 를 알 수 없다 | 사람별 계정((c) 채택 이유 4). 공유가 확인되면 계정 분리 |
| **`0039` 수정이 번역 저장 경로를 깨뜨림** | 번역이 안 보임 | `notice_service.py:778-787` 은 **덧붙이기만** 한다 — `validation_status='passed'` 와 사용자 노출 동작을 바꾸지 않는다. §12.3 회귀로 확인 |
| Scheduler location 불일치 | API 호출 404 | §8.2 — 목록 API 로 확인 후 상수화 (현재 **미확인**) |

### 13.2 롤백

| 배포 | 롤백 |
|---|---|
| 1 (`0038`) | 테이블 3개 drop |
| 2 (계정) | `is_active = false` |
| 3 (게이트) | `middleware.ts` 되돌리기 — 학부모 흐름은 손대지 않았으므로 영향 없음 |
| 4·5 (읽기 화면) | 라우트 삭제. 읽기 전용이라 데이터 영향 0 |
| 6 (로깅) | `setup_logging()` → `basicConfig` 복귀 |
| 7 (이력) | insert 호출 제거. 테이블은 남겨도 무해 |
| 8 (FastAPI) | 라우터 등록 제거. `ADMIN_API_TOKEN` 미설정만으로도 전 엔드포인트가 503 이 된다 |
| 9·10·11 (쓰기 화면) | 라우트 삭제 → 즉시 수동 스크립트로 복귀 (스크립트는 그대로 남겨둔다) |
| 12 (`0039`) | 컬럼 2개 drop, `notice_service.py` 되돌리기 |
| 13 | 알림 정책 삭제 |

> **스크립트를 지우지 않는다.** 화면이 스크립트를 대체하지만, 화면이 고장 났을 때
> 돌아갈 곳이 필요하다. 최소 한 분기(§11 배포 13 이후 3개월)는 병행 유지한다.

---

## 14. 결정 기록 (2026-08-27)

| # | 결정 | 반영 위치 |
|---|---|---|
| **1** | **관리자는 별도 URL 을 갖고, 아이디·비밀번호를 따로 설정한다. 학부모 인증(구글 로그인)과 분리된 체계다** | §3 전체. 특히 §3.3 이 이 결정 때문에 (d) IAP(Google 신원)를 주 수단에서 제외하고, §3.4 가 (c) 를 권고 |
| **2** | **학부모 개발 진입로 `/home` 은 당분간 켜둔다. 관리자 인증은 그것과 무관하게 독립적으로 안전해야 한다** | §1.4 핵심 제약. §3.3 의 판정 기준 자체. §3.4 근거 1. §12.1 #2·#3 이 이를 시험 |
| **3** | **데모는 끝났다** | §6 에 데모 관련 화면을 넣지 않는다. §10 에서 `scripts/probe_demo_schools.py`·`seed-arabic-demo-account.cjs` 를 화면화 대상에서 제외 |

### 이 사업에서 새로 내린 판단

| # | 판단 | 근거 |
|---|---|---|
| 4 | **`profiles.role` 을 1단계에서 복원하지 않는다** | §5.1 — (c) 를 쓰면 불필요하고, 복원 시 `0001:138-141` 의 자기 승격 경로가 생긴다 |
| 5 | 열거값은 enum 이 아니라 `text + CHECK` | §5.2 — `0002` 이후 저장소 전체가 그 방향. 되돌리기 비용 차이 |
| 6 | 관리자 조회는 Next.js, GCP 제어는 FastAPI | §7.1~7.2 — 백엔드가 공개 표면이라는 실측 + RLS 정책 0개 테이블은 service_role 강제 |
| 7 | `_require_internal_token` 을 재사용하지 않는다 | §7.3 — `crawler.py:25-26` 의 local fail-open 이 관리자 제어에 부적합 |
| 8 | 검토 큐보다 데이터 소스 복구가 선행 | §9.3 — 신호가 코드에서 사라졌고 담을 컬럼도 없다 |

---

## 15. 열린 질문

착수 전에 답이 필요한 순서대로.

| # | 질문 | 왜 필요한가 | 답에 따라 달라지는 것 |
|---|---|---|---|
| **1** | **관리자가 몇 명인가?** 앞으로 늘어날 계획이 있는가 | §3.4 의 (b) vs (c) 선택이 여기서 갈린다 | 1명 확정 + 감사 추적 불필요 → (b), `0038` 이 통째로 빠진다. 2명 이상 또는 미정 → (c) |
| **2** | **학교 관계자에게 권한을 줄 것인가?** | 주면 «자기 학교만» 이라는 범위 제한(row scoping)이 필요하다 | 준다 → §5.2 `profiles.role` 복원 + `school_staff` 값 + 모든 조회에 학교 필터 + RLS 재설계. 이 사업의 크기가 1.5배가 된다 |
| **3** | **2단계 인증이 필요한가?** | §3.5 는 «1단계에서 안 한다»로 잡았다 | 필요 → `admin_users.totp_secret` 활성화 + 검증 ~50줄 + 등록 화면. 관리자가 인증기 앱을 쓸 수 있는지 **미확인** |
| 4 | 관리자 콘솔을 나중에 별도 도메인으로 뗄 계획이 있는가 | §4.1 은 1단계 `/admin` 으로 잡되 코드를 옮기기 쉽게 격리한다 | 뗀다 → LB·DNS·인증서 필요 여부 확인, (d) IAP 를 2중 방어로 겹칠 수 있다 |
| 5 | 실제 Cloud Scheduler 잡 이름·location 이 무엇인가 | §8.2 화이트리스트 상수를 채워야 한다 | 문서와 실운영이 이미 어긋나 있다 (§6.4). **미확인** — 착수 시 `gcloud scheduler jobs list` 로 확정 |
| 6 | PAUSED 상태인 5개를 언제 재개하는가 | 재개 자체는 이 사업 밖이지만, §9.2 실행 이력이 쌓이려면 크롤이 돌아야 한다 | 재개 전이면 §11 배포 7 의 확인(«다음 정기 실행 후 행 1개»)이 성립하지 않는다 |
| 7 | 실패 알림을 **어디로** 보내는가 (이메일·Slack·기타) | §9.4 | 채널에 따라 Cloud Monitoring notification channel 설정이 달라진다. **미확인** |

---

## 16. 부록 — 이 스펙이 근거로 삼은 실측

조사 중 확인했으나 본문에 흩어져 있는 사실들을 한곳에 모은다.

| 사실 | 근거 |
|---|---|
| `gcloud scheduler jobs pause` / `resume` 가 저장소 전체에 **0건** | 전수 grep |
| `_hambak_enqueue.py` 는 **Supabase 키 없이** prod 번역 잡을 밀어넣는다 | 백엔드 `/notices/{id}/translate` 가 무인증 (`backend/app/api/notices.py:96`) |
| `admin_review_required` 가 `backend/app/` 에 **0건** | grep. 문서(`docs/translation-quality.md:166`)에만 남음 |
| `notice_ai_translations.metadata` 는 이미 drop | `0020_notice_ai_translations_drop_metadata.sql:1-2` |
| `job_queue_service.py` 에 목록·통계 조회 함수 없음 | 조회 계열은 `:101`, `:119`, `:198` 셋뿐 |
| `worker_trigger.py` 는 `json={}` — overrides 미사용 | `:87-108` |
| `lib/school-crawl-state.ts` select 에 `board_watermarks` 누락 | `:47`, `:74` |
| `lib/supabase/server.ts` 에 `import 'server-only'` 없음 | 비교: `lib/school-crawl-state.ts:1`, `lib/school-crawler-trigger.ts:1` |
| pgcrypto 가 이미 켜져 있음 | `0001_initial_schema.sql:1` |
| bcrypt/argon2 의존성 없음 | `package.json:12-26`, `backend/requirements.txt` |
| Next.js 는 **16.x** 다 (조사 요약의 «15» 는 부정확) | `package.json:18` `"next": "^16.2.4"` |
| `_require_internal_token` 은 토큰 미설정 + non-local 에 **503** (401 아님) | `backend/app/api/crawler.py:26-30` |
| 마이그레이션 `0035` 결번, `0030` 중복 2건 | 파일 목록 실측 |
