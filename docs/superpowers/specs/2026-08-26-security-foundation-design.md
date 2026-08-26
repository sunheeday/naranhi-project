# 사업 A — 보안 기반 · 인증 복구 · DB 배포 자동화

기준일: 2026-08-26
상태: 설계 (구현 전)
선행: 없음 / 후행: 사업 D(DB 정리), 사업 F(관리자 페이지)

---

## 1. 배경

조사에서 확인된 프로덕션 상태 세 가지가 이 사업의 출발점이다.

| 확인 사항 | 근거 |
|---|---|
| `app_jobs` 230행이 anon 키로 전량 조회됨 | 운영 PostgREST 직접 조회 (2026-08-26). 다른 테이블은 전부 0행 |
| 프로덕션 웹이 인증 없이 열림 | `.github/workflows/deploy-cloud-run.yml:84` `TEST_ENTRY_BYPASS=true` + `middleware.ts:19-27` |
| 첨부 버킷이 공개 | `supabase/migrations/0011_notice_attachments_bucket.sql:6-8` (주석에 "보안 미적용" 자인) |

여기에 구조적 문제가 하나 더 있다. **마이그레이션이 CI로 적용되지 않는다.**
`ci.yml` / `deploy-*.yml` 어디에도 `supabase db push`가 없고, 운영 문서가 대시보드
SQL Editor 수동 실행을 안내한다(`docs/scheduled-crawl-runbook.md:23-28`).
그 결과 `0030`이 두 개(`0030_notice_ai_translations_add_translated_title.sql`,
`0030_school_events_end_date.sql`) 존재한다.

> 실측 확인: 두 `0030` 모두 실제 DB에 **적용되어 있다**(운영 컬럼 조회로 확인).
> 즉 지금 데이터 문제는 없다. 문제는 **앞으로 자동화를 붙일 때** 드러난다 (§7.4).

사업 D(DB 정리)는 마이그레이션 6~7개를 만든다. 그것을 손으로 넣기 시작하면
같은 사고가 반복된다. 그래서 **배포 자동화가 DB 정리의 선행 조건**이다.

---

## 2. 목표 / 비목표

### 목표

1. anon 키로 내부 작업 큐가 읽히지 않는다.
2. 학부모가 구글 계정으로 로그인하고, 14일간 재로그인 없이 쓴다.
3. 개발·시연용 진입로가 **명시적으로 켤 때만** 열린다.
4. 공지 첨부는 **그 학교에 자녀를 등록한 사용자만** 받을 수 있다.
5. `main` 머지 시 마이그레이션이 DB에 자동 적용된다.

### 비목표 (이 사업에서 하지 않는다)

- **관리자 인증** — 별도 URL·계정 체계는 사업 F에서 다룬다. 여기서는 학부모 인증만 복구한다.
- **백엔드 FastAPI 엔드포인트 인증** — `/notices/*`, `/capture/ocr`가 무인증인 문제는 별건으로 남긴다.
- **service_role RLS 우회 정리** — 프론트 렌더 경로가 승격 클라이언트를 상시 쓰는 문제(`lib/server-cache.ts` 등)는 사업 D에서 다룬다.
- **스키마 정리** — 죽은 컬럼(`schools.crawl_*` 등) 제거는 사업 D.
- **데모 데이터 분리** — 사업 D.

---

## 3. 작업 단위

| | 단위 | 크기 | 되돌리기 |
|---|---|---|---|
| A1 | 작업 큐 접근 차단 | SQL 1줄 | 1줄 |
| A2 | 인증 복구 + 개발 진입로 | 설정 + 라우트 1개 | env 되돌리기 |
| A3 | 첨부 비공개 + 학부모 스코프 | 백엔드·프론트 읽기 경로 | 버킷 공개 복구 |
| A4 | DB 배포 자동화 | 워크플로 1개 + 이력 정합 | 워크플로 삭제 |

A1은 이미 작성·검증 완료 (`supabase/migrations/0036_app_jobs_rls.sql`, 브랜치 `fix/app-jobs-rls`).

---

## 4. A1 — 작업 큐 접근 차단

### 설계

```sql
alter table public.app_jobs enable row level security;
```

정책을 **만들지 않는다**. RLS 활성 + 정책 0개 = anon/authenticated 전면 차단.
접근 경로는 service_role(백엔드 `job_queue_service`, 운영 스크립트)뿐이고
service_role은 RLS를 우회한다.

### 근거

- 프론트 전 경로(`.from` / `.rpc` / PostgREST 직접 fetch / Realtime)에 `app_jobs` 접근 **0건** 확인.
- 번역 상태 폴링 UI는 백엔드 API 경유 (`lib/notices.ts:42-70` → `backend/app/api/notices.py:199`).
- 백엔드에 anon 클라이언트가 **존재 불가** — `backend/app/core/supabase.py:10-15`가 유일 팩토리이고
  service_role 키 없으면 `RuntimeError`. `config.py`에 anon 키 설정 필드 자체가 없다.
- 동일 패턴 선례: `0013_school_crawl_state.sql:72` (RLS 활성, 정책 0개, 백엔드가 정상 upsert 중).

### 부수 영향

`scripts/_hambak_jobstatus.py`는 앞으로 service_role 키로만 동작한다.
anon 키로 돌리면 에러가 아니라 **빈 배열**이 와서 조용히 오진된다.
해당 파일 docstring에 명시한다.

---

## 5. A2 — 인증 복구 + 개발 진입로

### 5.1 현재 상태 — 전부 이미 구현되어 있다

| 필요한 것 | 위치 | 상태 |
|---|---|---|
| 구글 OAuth 로그인 | `app/(auth)/login/actions.ts:22`, `LoginButtons.tsx:74` | 구현됨 |
| OAuth 콜백 | `app/auth/callback/route.ts` | 구현됨 |
| 개발용 즉시 로그인 | `app/api/auth/dev-login/route.ts` | 구현됨 |
| 온보딩 (학교·학년·반·이름·언어·식이) | `app/onboarding/actions.ts:18-30` `SaveChildInput` | 구현됨 |
| 학교 검색 (NEIS) | `app/onboarding/SchoolSearchInput.tsx` → `app/api/schools/search` | 구현됨 |

**막고 있는 것은 배포 설정 한 줄이다.**

### 5.2 변경

**(a) 우회 경로를 하나로 통합한다**

지금 우회 스위치가 사실상 둘이다 — `TEST_ENTRY_BYPASS`(전 경로 무인증 통과)와
`DEV_LOGIN_ENABLED`(개발 계정 즉시 로그인). 사용자 결정에 따라 개발 진입로는
당분간 켜두므로, **스위치가 둘로 남으면 나중에 하나를 꺼도 열려 있게 된다.**

따라서 이 사업에서:

- `.github/workflows/deploy-cloud-run.yml:84`의 `TEST_ENTRY_BYPASS=true` **제거**
- `middleware.ts:19-27`의 `TEST_ENTRY_BYPASS` 분기 **제거**
- `lib/test-entry-bypass.ts` **제거** (§6.3(e) 데모 종료 결정과 같은 작업)
- 우회는 **`DEV_LOGIN_ENABLED` 하나로만** 제어한다

결과: 로그인 없이 들어오는 길은 `/home` 하나만 남고, env 한 줄로 닫을 수 있다.

**(b) `/home` 개발 진입로**

신규 라우트 `app/home/route.ts` — `DEV_LOGIN_ENABLED`가 참일 때만 `/api/auth/dev-login`으로
넘기고, 아니면 `/login`으로 리다이렉트한다.

**사용자 결정 (2026-08-26): 당분간 프로덕션에서도 항상 켠다.** 나중에 명시적으로
끄라고 할 때 끈다.

> ⚠️ **따라서 A2는 "인증을 강제하는 것"이 아니라 "인증 경로를 되살리는 것"이다.**
> `/home`이 열려 있는 동안은 로그인 없이 들어올 길이 계속 존재한다.
> 이 사업의 실질 효과는 셋으로 좁혀진다 —
> ① 로그인한 사용자라는 개념이 생긴다(A3의 전제) ② 정상 사용자는 구글 로그인 흐름을 탄다
> ③ 나중에 `DEV_LOGIN_ENABLED=false` 한 줄로 완전히 닫을 수 있다.
>
> 구현 요건: 이 경로는 **반드시 단일 env(`DEV_LOGIN_ENABLED`)로만 제어**되어야 하고,
> 끄는 순간 다른 우회 경로가 남지 않아야 한다. `middleware.ts`의 `TEST_ENTRY_BYPASS`
> 분기와 `lib/test-entry-bypass.ts`는 이 사업에서 제거해 **우회 경로를 하나로 통합**한다.
> 스위치가 두 개면 하나를 끄고도 열려 있게 된다.

**(c) 14일 세션 — 코드만으로 달성된다**

Supabase 세션은 access token(단명, 기본 1시간)과 refresh token(장명)으로 나뉜다.
사용자가 다시 로그인하지 않으려면 **브라우저가 refresh token을 14일간 들고 있으면 된다.**

- **조치**: `lib/supabase/server.ts`의 `@supabase/ssr` 쿠키 옵션에 `maxAge: 60*60*24*14`
- **프로젝트 설정 변경 불필요**: Supabase 기본값은 refresh token에 시간 제한(time-box)이
  없고 회전 방식으로 갱신된다. 따라서 쿠키 수명이 곧 자동 로그인 기간이 된다.

> 사용자 확인 1건만: 대시보드 → Authentication → Sessions 에
> "Time-box user sessions"가 **켜져 있고 14일보다 짧으면** 알려줄 것.
> 꺼져 있으면(기본값) 아무 조치도 필요 없다.

**(d) 데모 진입 경로 제거**

`lib/test-entry-bypass.ts`가 화이트리스트 3개 학교에 대해 service_role로
`schools` insert + 크롤 트리거까지 수행한다. 데모 종료 결정(§6.3(e))에 따라
**이 파일과 호출부를 제거한다.** 가드를 추가하는 게 아니라 삭제다 —
남겨두면 새 데모 데이터가 계속 생길 수 있고, (a)의 "스위치 하나" 원칙에도 어긋난다.

### 5.3 로그인 이후 흐름

기존 흐름을 그대로 쓴다. 변경 없음.

```
/login → 구글 OAuth → /auth/callback
  → 프로필 없으면 /onboarding
      학교 검색(NEIS) → 학년·반·아이 이름·언어·식이제한 입력
      → children insert + 학교 최초 크롤 트리거
  → 있으면 /
```

---

## 6. A3 — 첨부 비공개 + 학부모 스코프

### 6.1 현재 구조

| 지점 | 코드 |
|---|---|
| 업로드 | `backend/app/services/attachment_storage.py:62,76` — `get_public_url()` 결과를 저장 |
| 저장 위치 | `notices.extracted_content.sources[].public_url` / `.storage_path` |
| 읽기 | `lib/notices.ts:334,379`, `lib/demo-school.ts:966` |
| 버킷 | `notice-attachments`, `public = true` |
| 오브젝트 키 | `{notice_id}/{sha256[:16]}{ext}` (`attachment_storage.py:24-33`) |

**현재 노출 등급**: 열거는 불가능하다(`storage.objects`에 정책 0개 → list API 거부,
키도 추측 불가). 따라서 "URL을 아는 사람은 인증 없이 영구히 받을 수 있음"이다.
`app_jobs`처럼 키 하나로 전량 덤프되는 등급은 아니다.

### 6.2 목표 구조

```
버킷 private
  ↓
프론트가 첨부를 보여줄 때
  1. 세션에서 user 확인
  2. children.school_id ⊇ notice.school_id 인지 확인
  3. 통과하면 service_role로 storage_path에 대한 서명 URL 발급 (단명)
  4. 실패하면 첨부를 렌더하지 않는다
```

### 6.3 설계 결정

**(a) `public_url`을 저장하지 않는다.**
`extracted_content.sources[].public_url` 쓰기를 중단하고 `storage_path`만 남긴다.
URL은 **읽는 시점에** 발급한다. 저장된 URL은 만료 개념이 없어서 목표와 모순된다.

**(b) 발급 지점은 Next.js 서버 라우트 하나로 모은다.**
신규 `app/api/notices/[noticeId]/attachments/[sourceId]/route.ts`.
프론트는 이 경로만 알고, 서명 URL은 이 라우트가 302로 넘긴다.
→ 서명 URL이 HTML에 박히지 않고, 접근 검사를 한 곳에서만 한다.

**(c) 서명 URL 수명은 짧게 (기본 5분).**
링크 공유·리퍼러 유출의 창을 좁힌다.

**(d) 기존 데이터 이행.**
실측: source 108건 중 `public_url` 53건 / `storage_path` **42건**.
**`public_url`은 있는데 `storage_path`가 없는 건이 존재한다.**
→ 이행 스크립트가 `public_url`에서 오브젝트 키를 역산해 `storage_path`를 채운다.
역산 실패분 처리는 (f) 참조 — **재추출하지 않고 포기한다.**

**(e) 데모 학교 — 예외를 두지 않는다.**
**사용자 결정 (2026-08-26): "데모는 끝났다. 데모 학교는 뺀다."**

따라서 스코프 검사에 예외를 만들지 않는다. 데모 학교 첨부는 검사를 통과하지 못하고,
그게 의도된 동작이다. 데모 시드 자체의 제거는 사업 D에서 다루되,
**이 사업에서는 새 데모 데이터가 생기지 않도록 진입점만 막는다**
(`lib/test-entry-bypass.ts` 제거 — §5.2(d)와 같은 작업).

**(f) 기존 첨부 이행 실패분 — 재추출하지 않는다.**
**사용자 결정 (2026-08-26): "이제부터 다시 가정통신문 받을 거다. 재추출하지 마라."**

`storage_path` 역산이 실패하는 첨부(최대 11건 추정)는 **포기한다.**
해당 source의 `public_url`을 제거해 프론트가 렌더하지 않게 하고,
`errors`에 `attachment_orphaned_pre_private_bucket` 를 남긴다.
이 방침은 사업 C의 크롤 재가동 방침("밀린 것 말고 지금부터 새로 오는 것만")과 일치한다.

### 6.4 마이그레이션

```sql
update storage.buckets set public = false where id = 'notice-attachments';
```

`storage.objects` 정책은 추가하지 않는다(현재 0개 = service_role 전용 유지).
서명 URL 발급이 service_role로 이뤄지므로 정책이 필요 없다.

---

## 7. A4 — DB 배포 자동화

### 7.1 목표

`main` 머지 → `supabase db push` → 마이그레이션 자동 적용.

### 7.2 필요한 자격증명

| 값 | 종류 | 출처 | 넣는 곳 |
|---|---|---|---|
| `SUPABASE_ACCESS_TOKEN` | 시크릿 | Supabase 계정 → Access Tokens | GitHub Secrets |
| `SUPABASE_DB_PASSWORD` | 시크릿 | 프로젝트 설정 → Database | GitHub Secrets |
| `SUPABASE_PROJECT_REF` | 공개값 | 프로젝트 설정 → General | GitHub Variables |

> 앞의 둘은 **사용자가 직접 넣는다.** 값을 대화에 노출하지 않는다.
> 사용자 Supabase 역할이 Owner임을 확인했으므로 발급 권한에 문제가 없다.

### 7.3 워크플로 설계

```
PR       → supabase db diff --linked  (적용하지 않고 차이만 보고)
main 머지 → supabase db push          (실제 적용)
```

PR에서 `push`하지 않는 이유: 프로덕션 DB가 하나뿐이라 PR 단계 적용은 되돌릴 수 없다.

### 7.4 ⚠️ 마이그레이션 이력 정합 — 이 단위의 진짜 위험

지금까지 **모든 마이그레이션이 대시보드에서 수동 실행**됐다.
Supabase CLI는 `supabase_migrations.schema_migrations` 테이블로 적용 여부를 판단하는데,
수동 실행은 그 이력을 남기지 않았을 가능성이 높다.

**이 상태에서 `db push`를 처음 돌리면 CLI가 0001부터 전부 재실행을 시도한다.**

대부분은 `create table if not exists` / `add column if not exists`라 멱등하지만,
그렇지 않은 것이 섞여 있다 — 예: `0018_drop_legacy_schedules.sql`은 `drop table schedules`
한 줄이고, `0009`는 `schema_migrations` 행을 직접 UPDATE한다.

**따라서 A4의 첫 단계는 워크플로 작성이 아니라 이력 확인이다.**

1. `supabase_migrations.schema_migrations`의 실제 내용을 확인한다.
2. 비어 있거나 불완전하면 `supabase migration repair --status applied <version>`으로
   0001~0035를 적용됨으로 표시한다(실행하지 않고 이력만 기록).
3. `0030` 중복은 CLI가 버전 문자열로 이력을 관리하므로 **한쪽만 기록된다.**
   둘 다 실제 적용되어 있으므로 데이터 영향은 없다. 이력에 `0030` 하나만 남는 것을
   **수용하고 문서에 기록**한다. 파일 rename은 하지 않는다 — rename하면 CLI가
   미적용으로 보고 재실행을 시도한다.
4. `db diff`가 깨끗한지 확인한 뒤에야 `db push`를 켠다.

### 7.5 향후 규율

- 새 마이그레이션 번호는 **0037부터**. `0035`는 `docs/기능명세서-자녀-개인일정.md`가
  `child_personal_schedules`용으로 예약, `0036`은 A1이 사용.
- 파일명 중복 번호 금지. PR 체크에 번호 중복 검사를 넣는다.

---

## 8. 배포 순서

되돌리기 쉬운 것부터, 서로의 전제가 되는 순서로.

| 배포 | 내용 | 확인 |
|---|---|---|
| **1** | A4 이력 정합 (`migration repair`) + `db diff` 확인 | diff 없음 |
| **2** | A4 워크플로 추가 (PR은 diff만) | PR에서 diff 리포트 동작 |
| **3** | **A1** — `0036` 자동 적용으로 통과시킨다 | anon 조회 230행 → 0행 |
| **4** | A3 백엔드: `public_url` 쓰기 중단, `storage_path` 이행 스크립트 | 신규 추출에 `storage_path` 존재 |
| **5** | A3 프론트: 첨부 라우트 + 스코프 검사 (버킷은 아직 공개) | 로그인 사용자가 첨부 열람 가능 |
| **6** | A2 — 우회 해제 + `/home` 게이트 + 세션 14일 | 구글 로그인 → 온보딩 → 홈 |
| **7** | A3 버킷 비공개 전환 | 직접 URL 접근 실패, 앱 경유 성공 |

**6번이 5번보다 뒤인 이유**: 스코프 검사가 동작하려면 로그인한 사용자가 있어야 한다.
반대로 5번 전에 6번을 하면, 인증은 살아났는데 첨부 경로가 아직 공개라 어중간하다.

**7번이 마지막인 이유**: 버킷을 먼저 잠그면 이행이 안 끝난 첨부가 즉시 깨진다.

---

## 9. 검증

| 항목 | 방법 | 통과 기준 |
|---|---|---|
| A1 | anon 키로 `/rest/v1/app_jobs?select=id&limit=1` | `Content-Range`가 `*/0`, 본문 `[]` |
| A1 회귀 | 번역 잡 enqueue → 상태 폴링 화면 | 진행 상태가 정상 표시 |
| A2 | 시크릿창에서 서비스 URL 접속 | `/login`으로 이동 |
| A2 | 구글 로그인 → 온보딩 → 홈 | 자녀 1건 생성, 공지 목록 표시 |
| A2 | 14일 세션 | 쿠키 만료 시각이 발급 +14일 |
| A2 | `/home` (프로덕션) | `DEV_LOGIN_ENABLED` 없으면 `/login` |
| A3 | 로그인 사용자가 자기 학교 공지 첨부 다운로드 | 성공 |
| A3 | 다른 학교 공지의 첨부 URL 직접 호출 | 거부 |
| A3 | 저장된 옛 `public_url` 직접 호출 (7번 배포 후) | 거부 |
| A4 | PR 생성 | diff 리포트가 코멘트/로그에 표시 |
| A4 | `main` 머지 | 마이그레이션 적용, 이력에 기록 |

---

## 10. 위험과 롤백

| 위험 | 영향 | 완화 |
|---|---|---|
| **`db push` 첫 실행이 과거 마이그레이션을 재실행** | `drop table` 등 파괴적 구문 재실행 | §7.4 이력 정합을 **먼저** 수행. `db diff`가 깨끗할 때만 push 활성화 |
| 우회 해제로 시연 불가 | 데모 못 보여줌 | `DEV_LOGIN_ENABLED`로 계정 로그인 경로 확보 |
| 첨부 이행 누락분이 깨짐 | 일부 공지(최대 11건)에서 첨부 안 보임 | **수용한다** (§6.3(f) 결정). 7번 배포 전 결측 건수를 세어 기록하고, 해당 source의 `public_url`을 제거해 깨진 링크가 아니라 «첨부 없음»으로 보이게 한다 |
| 서명 URL 5분이 짧아 다운로드 실패 | 대용량 첨부 | 발급 시점이 아니라 클릭 시점에 발급(302 리다이렉트 구조라 자연히 해결) |
| Supabase refresh token 설정이 14일 미만 | 자동 로그인 조기 만료 | 대시보드 설정 확인이 선행 |

각 배포는 단독 롤백이 가능하다. A1은 `disable row level security`,
A2는 env 되돌리기, A3는 버킷 `public = true` 복구, A4는 워크플로 삭제.

---

## 11. 결정 기록 (2026-08-26)

착수 전 열려 있던 질문 4건은 모두 답이 나왔다.

| # | 질문 | 결정 | 반영 위치 |
|---|---|---|---|
| 1 | `/home` 개발 진입로를 프로덕션에 켤 것인가 | **켠다.** 나중에 명시적으로 끄라고 할 때 끈다 | §5.2(b) |
| 2 | 세션 14일을 어떻게 달성할 것인가 | **쿠키 `maxAge` 14일로 처리.** Supabase 기본값은 refresh token 시간제한이 없어 프로젝트 설정 변경 불필요 (대시보드에서 time-box가 켜져 있는지만 확인) | §5.2(c) |
| 3 | 데모 학교를 스코프 예외로 둘 것인가 | **두지 않는다.** 데모 종료. 진입점(`lib/test-entry-bypass.ts`)을 제거한다 | §6.3(e) |
| 4 | 이행 실패 첨부를 재추출할 것인가 | **재추출하지 않는다.** 포기하고 렌더에서 제외 | §6.3(f) |

### 남은 판단 (이 사업의 blocker는 아님)

- **사업 F 착수 전까지**: 관리자 계정 정책 — 인원수, 계정 보관 위치, 접근 경로,
  학교 관계자 권한 부여 여부. `profiles.role` 과 `user_role` enum 이 `0012` 에서
  삭제됐으므로 되살리는 마이그레이션이 필요하다.

---

## 12. 준비물

권한·자격증명·도구 목록은 [2026-08-26-prerequisites.md](./2026-08-26-prerequisites.md) 참조.

이 사업(A) 착수에 필요한 최소 셋:

1. `supabase login` — CLI에 액세스 토큰 등록
2. GitHub Secret `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_PASSWORD` + Variable `SUPABASE_PROJECT_REF`
3. Supabase Google Provider 활성 여부 + Google OAuth 리디렉션 URI 등록 확인

---

## 13. 다음 단계

이 스펙 승인 후 `superpowers:writing-plans`로 구현 계획을 작성한다.
구현은 서브에이전트로 분담하되, 배포 순서(§8)의 경계를 넘지 않는다.
