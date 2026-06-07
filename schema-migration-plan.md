# Schema Migration Plan

기준일: 2026-06-07

이 문서는 현재 스키마를 공격적으로 정리하기 위한 실행 계획서다.
목표는 아래 3가지다.

1. 실제 제품에서 쓰지 않는 컬럼과 상태를 제거한다.
2. 중복 저장을 줄이고 canonical source를 하나로 맞춘다.
3. 장기적으로 꼬일 구조(`schedules`, `schools` crawler state, translation audit payload)를 분리한다.

주의:
- 이 문서는 실행 계획서이면서 진행 현황 기록이다.
- 각 phase는 가능한 한 작은 배포 단위로 나눈다.
- destructive change는 항상 `코드 선배포 -> 백필 -> 읽기 경로 전환 -> 삭제` 순서를 따른다.

---

## 0. 전체 우선순위

가장 먼저 해야 할 것:

1. `notice_ai_translations.requires_admin_review`, `admin_review_reason` 제거
2. `schools`의 crawler 상태 분리
3. `schedules` child fanout 구조 재설계

그 다음:

4. `children.school_name`, `neis_office_code`, `neis_school_code` 정리
5. `profiles.email`, `display_name`, `avatar_url`, `role` 정리
6. `notice_ai_translations` 내부 audit/debug payload 제거

---

## Phase 1. 즉시 제거 가능한 컬럼 정리

### 대상

- `notice_ai_translations.requires_admin_review`
- `notice_ai_translations.admin_review_reason`
- `schedules.gcal_event_id`
- `profiles.role`
- enum `user_role.school_admin`

### 근거

- review workflow는 제품 플로우에 없음
- 현재 번역 완료/실패만 쓰고 있음
- `gcal_event_id`는 실제 동기화 ID로 쓰이지 않음
- role 기반 분기 사용 흔적이 약함

### 선행 작업

1. 코드에서 해당 필드 읽기 제거
2. 타입 정의 regenerated target 확인
3. 테스트 fixture에서 해당 필드 제거

### 코드 영향 범위

- [backend/app/services/notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py)
- [app/api/notices/[noticeId]/process/route.ts](/Users/sunnykim/naranhi-project/app/api/notices/[noticeId]/process/route.ts)
- [types/database.ts](/Users/sunnykim/naranhi-project/types/database.ts)
- review 관련 테스트 fixture 전반

### 마이그레이션 순서

1. 애플리케이션에서 필드 참조 제거
2. migration으로 index/drop column 실행
3. 타입 재생성
4. API 응답 shape 재검증

### SQL 초안

```sql
alter table public.notice_ai_translations
  drop column if exists requires_admin_review,
  drop column if exists admin_review_reason;

drop index if exists notice_ai_translations_review_idx;

alter table public.schedules
  drop column if exists gcal_event_id;

alter table public.profiles
  drop column if exists role;

drop type if exists public.user_role;
```

### 검증

- 공지 상세 번역 조회
- 홈 공지 목록 조회
- 번역 batch status route 호출
- 공지 번역 저장 테스트

### 롤백

- 컬럼 restore migration 필요
- enum 복구 필요
- 이 phase는 삭제형이라 롤백 비용이 낮지 않음
- 따라서 반드시 코드 선배포 이후 실행

---

## Phase 2. `children` 중복 학교 정보 제거 준비

### 대상

- `children.school_name`
- `children.neis_office_code`
- `children.neis_school_code`

### 현재 문제

- `children.school_id`가 있는데 학교 정보 snapshot이 아닌 값까지 같이 중복 저장 중
- 홈/급식/캘린더에서 child row를 읽을 때 학교 마스터 대신 child 중복 컬럼을 보고 있음

### 목표 구조

- `children`는 `school_id`만 소유
- 학교 이름/NEIS 코드는 `schools`에서 조회
- child는 “어느 학교에 속하는가”만 표현

### 선행 작업

1. `schools`에 `neis_office_code`, `neis_school_code`, `name`가 항상 채워지는지 확인
2. 누락된 학교 데이터 백필
3. 서버 캐시와 급식 조회를 join 기반으로 변경

### 코드 영향 범위

- [lib/server-cache.ts](/Users/sunnykim/naranhi-project/lib/server-cache.ts)
- [app/(app)/meals/page.tsx](/Users/sunnykim/naranhi-project/app/(app)/meals/page.tsx)
- [app/onboarding/actions.ts](/Users/sunnykim/naranhi-project/app/onboarding/actions.ts)
- [app/(app)/settings/actions.ts](/Users/sunnykim/naranhi-project/app/(app)/settings/actions.ts)

### 추천 작업 순서

1. `getLatestChildForUser()`와 `getChildrenForUser()`를 `children -> schools` join 기반으로 변경
2. 온보딩/설정 저장 시 child에 학교 중복 필드 저장 중단
3. 기존 children rows의 중복 필드 사용처가 0이 된 뒤 drop

### SQL 초안

```sql
alter table public.children
  drop column if exists school_name,
  drop column if exists neis_office_code,
  drop column if exists neis_school_code;
```

### 검증

- 온보딩 후 홈 진입
- 설정에서 학교 재선택
- 급식 페이지 조회
- 캘린더 backfill 동작

### 롤백

- 컬럼 복구보다 먼저, 애플리케이션이 `schools` join으로 안전하게 동작하는지 검증해야 함
- 이 phase는 반드시 2회 배포로 나눈다

배포 1:
- 읽기 경로 전환

배포 2:
- 컬럼 삭제

---

## Phase 3. `profiles` 정리

### 대상

- `profiles.email`
- `profiles.display_name`
- `profiles.avatar_url`

### 판단 기준

- `email`은 `auth.users.email`을 canonical로 쓸 수 있으면 제거
- `display_name`, `avatar_url`는 실제 제품 UI에서 읽지 않으면 제거

### 선행 확인 질문

1. 추후 사용자 프로필 화면 계획이 있는가
2. 소셜 로그인 공급자 avatar를 별도 보관할 필요가 있는가
3. 운영/문의 대응에서 profile email snapshot이 필요한가

### 권장 순서

1. 코드 검색으로 모든 read/write 경로 확인
2. 미사용이면 write 제거
3. profile 조회에서 제거
4. 컬럼 삭제

### SQL 초안

```sql
alter table public.profiles
  drop column if exists email,
  drop column if exists display_name,
  drop column if exists avatar_url;
```

---

## Phase 4. `schools` crawler 상태 분리

### 대상

- `schools.crawl_status`
- `schools.crawl_error_message`
- `schools.crawl_result`
- `schools.crawl_board_url`
- `schools.crawl_last_checked_at`

### 현재 문제

- 학교 마스터와 내부 운영 상태가 한 row에 섞여 있음
- `schools`는 사용자 읽기 경계에 가까운데 crawler state는 내부 운영 정보임
- RLS와 public/private 경계가 흐려짐

### 목표 구조

신규 테이블:

- `school_crawl_state`
  - `school_id pk/fk`
  - `crawl_status`
  - `crawl_error_message`
  - `crawl_result`
  - `crawl_board_url`
  - `crawl_last_checked_at`
  - `created_at`
  - `updated_at`

### 추천 작업 순서

1. `school_crawl_state` 생성
2. 기존 `schools` 컬럼 데이터 백필
3. crawler/service/API 읽기 경로를 새 테이블로 전환
4. 프론트가 더 이상 `schools.*crawl_*`를 읽지 않게 변경
5. 기존 컬럼 삭제

### 코드 영향 범위

- [lib/server-cache.ts](/Users/sunnykim/naranhi-project/lib/server-cache.ts)
- [lib/school-crawler-trigger.ts](/Users/sunnykim/naranhi-project/lib/school-crawler-trigger.ts)
- [app/onboarding/actions.ts](/Users/sunnykim/naranhi-project/app/onboarding/actions.ts)
- [app/(app)/settings/actions.ts](/Users/sunnykim/naranhi-project/app/(app)/settings/actions.ts)
- [app/api/schools/[schoolId]/crawl/route.ts](/Users/sunnykim/naranhi-project/app/api/schools/[schoolId]/crawl/route.ts)
- [backend/app/services/school_crawler_service.py](/Users/sunnykim/naranhi-project/backend/app/services/school_crawler_service.py)
- [backend/app/services/scheduled_crawler_service.py](/Users/sunnykim/naranhi-project/backend/app/services/scheduled_crawler_service.py)

### SQL 초안

```sql
create table public.school_crawl_state (
  school_id uuid primary key references public.schools(id) on delete cascade,
  crawl_status text not null default 'pending',
  crawl_error_message text,
  crawl_result jsonb,
  crawl_board_url text,
  crawl_last_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.school_crawl_state (
  school_id,
  crawl_status,
  crawl_error_message,
  crawl_result,
  crawl_board_url,
  crawl_last_checked_at
)
select
  id,
  crawl_status,
  crawl_error_message,
  crawl_result,
  crawl_board_url,
  crawl_last_checked_at
from public.schools
on conflict (school_id) do nothing;
```

후속 삭제:

```sql
alter table public.schools
  drop column if exists crawl_status,
  drop column if exists crawl_error_message,
  drop column if exists crawl_result,
  drop column if exists crawl_board_url,
  drop column if exists crawl_last_checked_at;
```

### 검증

- 온보딩에서 학교 크롤링 시작
- 설정에서 학교 재선택 후 재크롤링
- scheduled crawler 배치
- 홈 empty/collecting 상태 UI

### 롤백

- 새 테이블 유지한 채 읽기 경로만 원복 가능
- 컬럼 삭제는 마지막 배포에서만 수행

---

## Phase 5. `schedules` 재설계

### 현재 문제

- 한 공지의 일정이 `child_id`별로 복제됨
- 동일 학교 형제 수만큼 row가 늘어남
- `notice_id + child_id + event_date`는 제품 의미보다 저장 편의에 가까운 구조
- 현재 D-day와 calendar가 같은 테이블을 서로 다른 의미로 소비하고 있음

### 목표 구조

신규 테이블:

- `school_events`
  - `id`
  - `school_id`
  - `notice_id`
  - `event_date`
  - `title`
  - `location`
  - `description`
  - `source_language`
  - `created_at`
  - `updated_at`

선택적 보조 테이블:

- `user_hidden_events`
  - `user_id`
  - `event_id`

### 설계 원칙

- 이벤트는 school-level entity
- user/child별 개인 상태만 별도 테이블로 둔다
- D-day용 마감일은 이미 `notices.due_date`가 있으므로 `school_events`와 의미를 분리한다

### 추천 작업 순서

1. `school_events` 생성
2. 기존 `schedules` 데이터를 school-level로 dedupe 백필
3. `notice_service`를 `school_events` dual write로 전환
4. 홈과 캘린더 조회를 `school_id` 기반으로 변경
5. onboarding/calendar backfill 로직을 `school_events` 기준으로 교체
6. 기존 `schedules` write 중단
7. 기존 `schedules` drop

### 코드 영향 범위

- [backend/app/services/notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py)
- [lib/schedule-backfill.ts](/Users/sunnykim/naranhi-project/lib/schedule-backfill.ts)
- [app/(app)/calendar/page.tsx](/Users/sunnykim/naranhi-project/app/(app)/calendar/page.tsx)
- [app/(app)/page.tsx](/Users/sunnykim/naranhi-project/app/(app)/page.tsx)
- onboarding의 schedule backfill 경로

### SQL 초안

```sql
create table public.school_events (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id) on delete cascade,
  notice_id uuid not null references public.notices(id) on delete cascade,
  event_date date not null,
  title text not null,
  location text,
  description text,
  source_language text not null default 'ko',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (notice_id, event_date)
);
```

백필 개념:

```sql
insert into public.school_events (
  school_id, notice_id, event_date, title, location, description, source_language
)
select distinct
  n.school_id,
  s.notice_id,
  s.event_date,
  s.title,
  s.location,
  s.description,
  'ko'
from public.schedules s
join public.notices n on n.id = s.notice_id
where n.school_id is not null;
```

### 검증

- 홈 D-day 표시
- 캘린더 월간/주간 조회
- 번역 후 일정 재생성
- 신규 child 추가 시 예전 공지가 캘린더에 보이는지 확인
- school-level event가 형제 수와 무관하게 1건만 생성되는지 확인

### 롤백

- 새 테이블 write를 끄고 old `schedules` read/write로 되돌릴 수 있어야 함
- 따라서 한 배포 안에서 old table drop까지 가지 않는다

권장 배포:

1. dual write
2. read switch
3. old backfill 검증
4. old table 삭제

### 현재 상태

- 완료:
  - [supabase/migrations/0017_school_events.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0017_school_events.sql)
  - [backend/app/services/notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py)에서 `school_events` dual write 추가
  - [lib/schedule-backfill.ts](/Users/sunnykim/naranhi-project/lib/schedule-backfill.ts) `school_events` 기준 backfill 전환
  - [app/(app)/calendar/page.tsx](/Users/sunnykim/naranhi-project/app/(app)/calendar/page.tsx) read switch
  - [app/(app)/page.tsx](/Users/sunnykim/naranhi-project/app/(app)/page.tsx) D-day fallback read switch
  - [supabase/migrations/0018_drop_legacy_schedules.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0018_drop_legacy_schedules.sql)
  - [backend/app/services/notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py) legacy `schedules` write 제거
- 남음:
  - production 반영 전 실제 row count와 hidden dependency 재확인

---

## Phase 6. `notice_ai_translations` slim table + DB audit 제거

### 현재 문제

한 테이블에 아래가 모두 들어있다.

- 사용자 표시용 번역 결과
- validation/debug payload
- raw pipeline output
- ingredient identity/debug metadata
- source_text

이 구조는 RLS 경계와 장기 저장 비용 측면에서 좋지 않다.

### 목표 구조

유지 테이블:

- `notice_ai_translations`
  - `notice_id`
  - `target_language`
  - `translated_text`
  - `validation_status`
  - `created_at`
  - `updated_at`

1차 제거 대상:

- `source_text`
- `validation`
- `raw_pipeline`
- `ingredient_identity_map`
- `metadata`

2차 제거 대상:

- `source_hard_facts`
- `target_hard_facts`

대신:

- 번역 실행 시 필요한 내부 디버그 정보는 DB에 저장하지 않는다.
- 백엔드 서비스 실행 시 structured application log로만 남긴다.
- 운영 중 장기 보관이 필요하면 DB가 아니라 로그 수집 시스템에서 조회한다.

현재 판단:

- `source_hard_facts`, `target_hard_facts`는 아직 [lib/schedule-backfill.ts](/Users/sunnykim/naranhi-project/lib/schedule-backfill.ts)와 cached restore 경로에서 기능적으로 사용 중이라 2차 제거로 미룬다.
- `source_text`, `validation`, `raw_pipeline`, `ingredient_identity_map`는 사용자 표시나 현재 제품 동작에 직접 필요하지 않으므로 먼저 제거한다.
- `metadata`는 title patch 외의 제품 의존을 제거한 뒤 1.5차로 제거한다.

진행 업데이트:

- `school_events` backfill은 더 이상 `notice_ai_translations`를 읽지 않고 `notices.event_dates`를 canonical source로 사용한다.
- 따라서 남은 `hard_facts` 의존은 주로 `notice_cards`, cached restore, `due_date`/`event_dates` 생성 시점에 한정된다.

### 추천 순서

1. 현재 payload를 읽는 코드 경로 제거
2. 번역 저장 path에서 1차 debug payload DB 저장 중단
3. 번역 서비스에서 필요한 정보만 structured logger로 기록
4. 1차 slim migration 실행
5. `metadata` 저장 의존 제거 후 별도 drop
6. `school_events`/cached restore가 `hard_facts` 없이도 동작하도록 바꾼 뒤 2차 컬럼 삭제

### 주의

- `schedule-backfill.ts`가 현재 `source_hard_facts`, `target_hard_facts`, `metadata`를 읽고 있으므로 이 경로를 먼저 제거하거나 새 source로 바꿔야 한다
- 운영 디버깅은 SQL 조회가 아니라 애플리케이션 로그 조회 기준으로 전환해야 한다
- 로그에는 개인정보/원문 전문이 과도하게 남지 않도록 마스킹 규칙을 먼저 정해야 한다

---

## 배포 전략

### 원칙

- destructive migration은 항상 마지막
- read path 전환 전에 dual write 가능하면 dual write
- RLS 변경은 application read/write path 전환 직전/직후에 묶는다

### 추천 배포 묶음

배포 A:
- Phase 1

배포 B:
- Phase 4 시작
- `school_crawl_state` 생성 + dual read/write

배포 C:
- Phase 2 읽기 경로 전환

배포 D:
- Phase 5 시작
- `school_events` 생성 + dual write
- 홈/캘린더/onboarding read-backfill switch

배포 E:
- legacy `schedules` write 제거
- old `schedules` 검증

배포 F:
- old `schedules` drop

배포 G:
- Phase 6 slim/audit 분리

## 실행 전 체크리스트

- `types/database.ts` regeneration 절차 확인
- supabase migration naming 규칙 확인
- production data volume 확인
- `schedules`, `notice_ai_translations`, `schools` row count 파악
- RLS policy 영향 검토
- translation debug payload를 어떤 운영 루틴이 직접 조회하는지 검색 완료

---

## 가장 먼저 만들 migration 3개

### 1. `drop_unused_translation_review_columns`

포함:
- `requires_admin_review`
- `admin_review_reason`
- review index 제거

이유:
- 가장 리스크가 낮고 현재 제품 가치가 거의 없음

### 2. `create_school_crawl_state`

포함:
- 신규 테이블 생성
- 기존 데이터 백필

이유:
- 마스터 데이터와 운영 상태 분리를 시작하는 핵심 step

### 3. `create_school_events`

포함:
- 신규 school-level 일정 테이블 생성
- dedupe 백필

이유:
- 가장 구조적인 문제를 푸는 첫 단계

---

## 권장 다음 작업

1. `schedules` 최종 drop 전 production data 검증 쿼리 작성
2. `school_events` production row shape spot check
3. `notice_ai_translations` slim화 전에 debug payload 의존 경로 제거
4. debug/audit payload를 DB 대신 backend structured log로 남기는 저장 경로 설계
