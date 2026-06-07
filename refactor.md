

You are a senior database architect auditing a Supabase/PostgreSQL schema.

Goal:
Analyze the current Supabase ERD/schema and identify:
1. Tables that appear unnecessary or unused
2. Duplicate or overlapping tables
3. Duplicate columns across tables that should possibly be normalized
4. Redundant relationships or foreign keys
5. Missing foreign keys based on naming conventions
6. Tables that look like join tables but are incorrectly modeled
7. Enum/status columns that are duplicated or inconsistent
8. Columns that should probably be derived instead of stored
9. Tables that violate clear ownership or domain boundaries
10. Risky schema design choices for future scaling, RLS, or data consistency

Important:
Do not modify the database.
Do not create migrations yet.
Only inspect, reason, and produce a report.

Please examine:
- Supabase schema
- SQL migration files
- Type definitions generated from Supabase
- Any database-related service/repository code
- RLS policies if available
- Seed files if available

Output format:

# Supabase Schema Audit Report

## 1. Executive Summary
Give a short summary of the main schema problems.

## 2. Possible Unused Tables
For each table:
- table name
- why it may be unused
- evidence from codebase
- confidence: low / medium / high
- recommended action: keep / investigate / remove / merge

## 3. Duplicate or Overlapping Tables
For each suspected duplication:
- table A
- table B
- overlapping purpose
- differences
- recommended canonical table
- migration risk

## 4. Redundant Columns
For each issue:
- table
- column
- why it may be redundant
- whether it should be derived, normalized, or removed

## 5. Relationship Problems
Identify:
- missing foreign keys
- redundant foreign keys
- ambiguous ownership
- many-to-many relationships that should use join tables
- join tables that are incorrectly structured

## 6. Naming and Consistency Issues
Find inconsistent names such as:
- user_id vs profile_id
- created_by vs owner_id
- status enums with different values
- plural/singular inconsistencies
- timestamp naming inconsistencies

## 7. RLS / Supabase-Specific Concerns
Check for:
- tables that likely need RLS but may not have it
- ownership columns needed for RLS
- public/private data separation issues
- policies that may become hard to maintain due to schema shape

## 8. Recommended Cleanup Plan
Group recommendations into:
- Safe cleanup
- Needs verification
- Requires migration plan
- Do not touch yet

## 9. Questions for the Product Owner
List questions that must be answered before deleting or merging anything.

Rules:
- Be conservative.
- Do not recommend deleting anything unless there is strong evidence.
- Cite exact files, table names, column names, and code references.
- Prefer practical recommendations over theoretical database purity.




1. 스키마 정리 후보를 `즉시 제거 가능 / 확인 후 제거 / 재설계 필요`로 재분류  
2. 현재 `크롤링 -> 공지 저장 -> 추출/번역 -> 프론트 표시` 흐름에서 실제로 뭐가 꼬일 수 있는지 분석

---

# 1. 스키마 정리 재분류

## A. 즉시 제거 후보
기능 계획이 없고, 현재 코드상 실질 가치가 거의 없는 것들입니다.

### 1) `profiles.role` + `user_role.school_admin`
- 근거:
  - enum 정의: [0001_initial_schema.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0001_initial_schema.sql:3)
  - 타입 정의: [types/database.ts](/Users/sunnykim/naranhi-project/types/database.ts:20)
  - 앱 사용 흔적 없음: role을 읽는 코드 실질 부재
- 판단:
  - 제품 로드맵에 없다고 명시됨
- 권장:
  - 제거 후보

### 2) `notice_ai_translations.requires_admin_review`
### 3) `notice_ai_translations.admin_review_reason`
- 근거:
  - 컬럼 정의: [0005_notice_ai_translations.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0005_notice_ai_translations.sql:14)
  - 저장 시 사실상 고정값: [notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py:346)
- 판단:
  - admin review 기능 계획 없음
- 권장:
  - 제거 후보

### 4) `validation_status` 설계 중 `human_review_required` 중심 흐름
- 근거:
  - DB check: [0005_notice_ai_translations.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0005_notice_ai_translations.sql:14)
  - 프롬프트에는 `human_review_required` 개념이 남아 있음: [prompts.py](/Users/sunnykim/naranhi-project/backend/app/translation/prompts.py:97)
- 판단:
  - review workflow가 없다면 상태 체계가 과합니다
- 권장:
  - `passed / failed` 정도로 단순화 검토

### 5) `schedules.gcal_event_id`
- 근거:
  - 스키마에만 존재: [0001_initial_schema.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0001_initial_schema.sql:76)
  - 실제로는 Google Calendar URL만 생성: [google-calendar.ts](/Users/sunnykim/naranhi-project/lib/google-calendar.ts:11)
- 판단:
  - 지금은 외부 이벤트 동기화 ID가 아님
- 권장:
  - 제거 후보

---

## B. 확인 후 제거 후보
중복 성격이 강하지만, 화면/스크립트/운영 경로 확인이 먼저 필요한 것들입니다.

### 1) `children.school_name`
### 2) `children.neis_office_code`
### 3) `children.neis_school_code`
- 근거:
  - `children.school_id`가 이미 존재: [0001_initial_schema.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0001_initial_schema.sql:30)
  - 생성/수정 시 학교 정보 중복 저장: [actions.ts](/Users/sunnykim/naranhi-project/app/onboarding/actions.ts:143), [settings/actions.ts](/Users/sunnykim/naranhi-project/app/(app)/settings/actions.ts:125)
- 판단:
  - snapshot 아님
  - `schools`와 중복
- 권장:
  - `schools`를 canonical source로 두고 제거 준비

### 4) `profiles.email`
- 근거:
  - auth user email을 복사 저장: [actions.ts](/Users/sunnykim/naranhi-project/app/onboarding/actions.ts:48)
- 판단:
  - `auth.users.email`와 중복 가능성 큼
- 권장:
  - 실제 조회 경로 확인 후 제거 검토

### 5) `profiles.display_name`, `avatar_url`
- 근거:
  - 정의는 있으나 앱 사용 흔적 약함: [0001_initial_schema.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0001_initial_schema.sql:8)
- 권장:
  - 사용처 확인 후 정리

---

## C. 재설계 필요
이건 컬럼 삭제 수준이 아니라 구조 자체를 다시 잡아야 합니다.

### 1) `schedules`
현재 가장 큰 재설계 대상입니다.

- 현재 구조:
  - `notice_id`
  - `child_id`
  - `event_date`
  - title/location/description
- 근거: [0001_initial_schema.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0001_initial_schema.sql:68)

문제:
- 학교 공지에서 나온 일정인데 child별 row로 fanout됨
- child가 많을수록 같은 일정이 복제됨
- DB가 “이 child가 이 notice의 school에 속하는지” 보장하지 않음
- 실제 요구사항도 school-level event면 충분하다고 확인됨

관련 코드:
- 일정 생성: [notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py:563)
- 백필: [schedule-backfill.ts](/Users/sunnykim/naranhi-project/lib/schedule-backfill.ts:10)
- 캘린더 조회는 child별 조회: [calendar/page.tsx](/Users/sunnykim/naranhi-project/app/(app)/calendar/page.tsx:105)

권장 방향:
- `school-level schedules/events` 테이블로 재설계
- 필요하면 나중에 user hide/state만 별도 테이블

### 2) `schools`의 crawler 내부 상태 컬럼
- 대상:
  - `crawl_status`
  - `crawl_error_message`
  - `crawl_result`
  - `crawl_board_url`
  - `crawl_last_checked_at`
- 근거: [0002_school_crawler_state.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0002_school_crawler_state.sql:1)

문제:
- 공용 학교 마스터 데이터와 내부 운영 상태가 섞여 있음
- 현재 `schools`는 인증 사용자 전원 읽기 허용: [0001_initial_schema.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0001_initial_schema.sql:143)

권장:
- `school_crawl_state` 같은 내부 운영 테이블 분리 검토

### 3) `notice_ai_translations` 내부 메타데이터 노출 구조
- 대상:
  - `raw_pipeline`
  - `validation`
  - `ingredient_identity_map`
  - `source_text`
- 근거: [0005_notice_ai_translations.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0005_notice_ai_translations.sql:1)

문제:
- 사용자에게 보여줄 번역 결과와
- 내부 품질 검증 / 파이프라인 디버그 정보가
- 같은 테이블/같은 접근 경계에 있음

권장:
- 사용자-facing 번역 결과와 내부 audit payload 분리

### 4) public attachment bucket
- 근거:
  - public bucket: [0011_notice_attachments_bucket.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0011_notice_attachments_bucket.sql:1)
  - public URL 사용: [attachment_storage.py](/Users/sunnykim/naranhi-project/backend/app/services/attachment_storage.py:61)
- 판단:
  - 학교 공지 첨부는 개인정보/민감정보 가능성이 있어서 기본값 public은 공격적입니다
- 권장:
  - private bucket + signed URL 방향이 맞음

---

# 2. 현재 파이프라인 분석

이제 실제 흐름을 보겠습니다.

## 현재 구조
대략 이렇게 흘러갑니다.

### 1) 학교 크롤링
- 학교 게시판 찾기 + 게시글 후보 추출
- 후보 notice row 저장
- 근거: [crawler.py](/Users/sunnykim/naranhi-project/backend/app/api/crawler.py:41), [school_crawler_service.py](/Users/sunnykim/naranhi-project/backend/app/services/school_crawler_service.py:106)

### 2) 크롤링 직후 background extraction 큐잉
- 크롤러 API가 성공하면 background task로 extractor 실행
- 근거: [crawler.py](/Users/sunnykim/naranhi-project/backend/app/api/crawler.py:64)

### 3) extractor가 `notices.original_text`, `extracted_content`, 상태 저장
- 성공 시 `status = done`
- 근거: [content_extraction_service.py](/Users/sunnykim/naranhi-project/backend/app/services/content_extraction_service.py:677)

### 4) extractor가 자동 번역 수행
- 학교에 연결된 locale 목록 계산 후 번역
- 근거: [content_extraction_service.py](/Users/sunnykim/naranhi-project/backend/app/services/content_extraction_service.py:729)

### 5) 프론트도 별도로 번역 API 호출
- 홈 화면에서 lazy kickoff: [HomeNoticeTranslationKickoff.tsx](/Users/sunnykim/naranhi-project/app/(app)/HomeNoticeTranslationKickoff.tsx:44)
- 상세 화면에서 lazy kickoff: [NoticeLocaleTranslationKickoff.tsx](/Users/sunnykim/naranhi-project/app/(app)/notices/[id]/NoticeLocaleTranslationKickoff.tsx:45)
- 서버 route: [process/route.ts](/Users/sunnykim/naranhi-project/app/api/notices/[noticeId]/process/route.ts:10)

즉:
- extraction 후 자동 번역이 돌고
- 동시에 프론트도 번역을 다시 트리거할 수 있습니다

이게 지금 구조상 가장 위험한 지점입니다.

---

# 3. 실제 문제 후보

## 문제 1) “DB 중복”보다 “동시 번역 경쟁 상태” 가능성이 큼
`notice_ai_translations`는 `unique (notice_id, target_language)`라서 완전한 row 중복은 어느 정도 막습니다.

- 근거: [0005_notice_ai_translations.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0005_notice_ai_translations.sql:20)

하지만 문제는 그 뒤 파생 데이터입니다.

### 왜 위험한가
번역이 끝나면:
- `notice_ai_translations` upsert
- `notice_cards` 갱신
- `schedules` 재생성
- `notices.extracted_content` 안의 summary/source translations 갱신

이 작업들이 모두 separate write입니다.

관련 코드:
- 번역 저장 entrypoint: [notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py:121)
- 카드 갱신: [notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py:497)
- 일정 재생성: [notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py:563)
- source/summary translation blob 갱신: [content_extraction_service.py](/Users/sunnykim/naranhi-project/backend/app/services/content_extraction_service.py:768)

### 핵심 위험
`translate_sources_for_locale()`는 `extracted_content`를 통째로 읽어와서 수정 후 다시 통째로 update합니다.

- 읽기: [content_extraction_service.py](/Users/sunnykim/naranhi-project/backend/app/services/content_extraction_service.py:778)
- 전체 update: [content_extraction_service.py](/Users/sunnykim/naranhi-project/backend/app/services/content_extraction_service.py:819)

즉:
- `vi` 번역이 `extracted_content` 읽음
- 동시에 `en` 번역도 같은 시점의 `extracted_content` 읽음
- 각자 자기 언어만 넣고 통째로 저장
- 마지막 writer가 먼저 저장한 언어를 덮어써 버릴 수 있음

이건 꽤 강한 경쟁 상태입니다.

신뢰도: 높음

---

## 문제 2) `notice_cards`도 병렬 번역 시 덮어쓰기 위험이 있음
카드는 언어별 row 분리가 아니라, 한 row의 `content jsonb` 안에 locale별 콘텐츠를 합치는 방식입니다.

- 조회/슬롯 매칭: [notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py:514)
- merge 후 update: [notice_service.py](/Users/sunnykim/naranhi-project/backend/app/services/notice_service.py:545)

위험:
- 두 번역이 동시에 기존 `content`를 읽고
- 각자 자기 locale만 합쳐서 update하면
- 마지막 write가 앞선 locale 추가분을 날릴 수 있음

이건 `extracted_content`와 같은 패턴의 lost update 문제입니다.

신뢰도: 높음

---

## 문제 3) 자동 번역과 프론트 lazy 번역이 역할 중복
자동 번역:
- extractor 성공 후 `_auto_translate_notice_locales()` 실행
- 근거: [content_extraction_service.py](/Users/sunnykim/naranhi-project/backend/app/services/content_extraction_service.py:729)

프론트 lazy 번역:
- 홈에서도 실행: [HomeNoticeTranslationKickoff.tsx](/Users/sunnykim/naranhi-project/app/(app)/HomeNoticeTranslationKickoff.tsx:47)
- 상세에서도 실행: [NoticeLocaleTranslationKickoff.tsx](/Users/sunnykim/naranhi-project/app/(app)/notices/[id]/NoticeLocaleTranslationKickoff.tsx:48)

즉 같은 notice/locale에 대해:
- 백엔드 auto translate
- 홈 화면 process route
- 상세 화면 process route
가 겹칠 수 있습니다.

프론트 route에도 캐시 체크는 있지만 lock이 아닙니다.
- cachedTranslation 확인: [process/route.ts](/Users/sunnykim/naranhi-project/app/api/notices/[noticeId]/process/route.ts:37)

동시에 두 요청이 들어오면 둘 다 “아직 없음”이라고 보고 backend translate를 호출할 수 있습니다.

신뢰도: 높음

---

## 문제 4) 홈 화면에서 번역 pending notice를 숨기는 UX가 “공지 사라짐”처럼 보일 수 있음
홈 화면은 번역 배치 pending이면 해당 notice들을 목록에서 제외합니다.

- 배치 pending 필터: [HomeNoticeSections.tsx](/Users/sunnykim/naranhi-project/app/(app)/HomeNoticeSections.tsx:40)

즉 사용자는:
- notice가 크롤링되어 들어왔는데
- 번역 시작되면 홈 목록에서 잠깐 사라지고
- 완료되면 다시 나타나는 것처럼 느낄 수 있습니다

이건 DB 중복 문제와 별개로 “뭔가 이상하게 동작한다”는 체감의 직접 원인일 수 있습니다.

신뢰도: 높음

---

## 문제 5) `status = done` 시점이 “번역 완료”가 아니라 “추출 완료”임
extractor 성공 시 notice는 바로 `done`

---

# 4. 리팩토링 결정사항 (2026-06-07)

이번 리팩토링에서는 아래를 기준선으로 둡니다.

## 번역 파이프라인
- 공지 번역의 canonical trigger는 백엔드 extractor 이후 auto translate로 통일한다.
- 프론트의 `/api/notices/[noticeId]/process` kickoff 흐름은 더 이상 기본 경로로 사용하지 않는다.
- 급식 번역은 기존처럼 AI pipeline(`translate-text` with `meal_labels`)을 유지한다.
- 즉, 사용자-facing AI 번역 경로는 `공지`, `급식` 두 종류만 유지한다.

## 프론트 UX
- 번역이 아직 없는 공지는 숨기지 않는다.
- 번역 전에는 사용자 locale 화면에서도 한국어 원문/카드 fallback을 그대로 보여준다.
- 대신 홈 카드와 상세 상단에 `처리중` 배지만 표시한다.
- 전역 배너는 `진행중` 안내 대신 `완료` 알림만 남긴다.

## 상태 관리
- localStorage 배치는 “번역 요청 트리거”가 아니라 “현재 번역 대기 notice 추적” 용도로만 사용한다.
- 상세 화면은 번역 대기 중일 때만 주기적으로 refresh 하여 번역본이 생기면 자연스럽게 전환한다.
- 홈은 pending notice를 필터링하지 않고, 서버가 계산한 `needsTranslation`만 badge로 노출한다.

## 백엔드 안전장치
- `NoticeService.translate_notice()`는 이미 usable한 번역 row가 있으면 즉시 cached result를 반환한다.
- 이로써 수동 재호출이나 중복 endpoint 호출이 들어와도 불필요한 AI 실행을 줄인다.

## 스키마 정리 우선순위
- 즉시 구조 변경은 보류하고, 현재 리팩토링에서는 코드 경로 정리부터 완료한다.
- 다음 migration 후보 우선순위는 아래 순서를 권장한다.
- 1. `notice_ai_translations.requires_admin_review`, `admin_review_reason` 제거 여부 확정
- 2. `children.school_name`, `neis_*` 중복 컬럼 정리
- 3. `schedules`를 child fanout 구조에서 school-level event 구조로 재설계
- 4. `schools`의 crawler 상태 컬럼 분리
- 5. attachment bucket 공개 정책을 private + signed URL로 전환
