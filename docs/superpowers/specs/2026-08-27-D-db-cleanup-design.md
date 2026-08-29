# 사업 D — DB 정리 · 기존 스키마 계획 완주

기준일: 2026-08-27
상태: 설계 (구현 전)
선행: **사업 A(보안 기반 · 인증 복구 · DB 배포 자동화) 완료** / 후행: 사업 F(관리자 페이지)

---

## 1. 배경

### 1.1 이건 새 설계가 아니다

이 저장소에는 이미 정리 계획이 있다. `schema-migration-plan.md`(2026-06-07, 599줄)가
6단계로 «죽은 컬럼 제거 → 중복 저장의 canonical 통일 → 꼬일 구조 분리»를 잡아뒀고,
그중 **Phase 1·2·5는 실제로 끝났다**(`0012`, `0014`~`0016`, `0017`/`0018`).
Phase 4는 새 테이블을 만들고 백필까지 했지만 **원본 컬럼을 지우는 마지막 배포에서 멈췄다**.
Phase 3은 시작조차 안 했다.

이 사업은 **그 계획의 미완료 단계를 마저 끝내는 것**이다. 새로 설계하는 부분은
계획 수립 이후(6월~8월) 추가된 것들 — `app_jobs`(0027), `notice_card_translations`(0026),
데모 시드(`lib/demo-school.ts`), 그리고 `types/database.ts` 드리프트 — 에 한정된다.

### 1.2 성능 문제가 아니다. 구조 문제다

운영 DB 실측 규모 (2026-08-26):

| 테이블 | 행 수 |
|---|---|
| `notices` | 38 |
| `schools` | 8 |
| `children` | 9 |
| `profiles` | 10 |
| `notice_ai_translations` | 155 |
| `school_events` | 68 |
| `app_jobs` | 230 |
| `meals` | 102 |

**38행짜리 테이블은 인덱스가 없어도 안 느리다.** 이 사업이 지금 필요한 이유는
속도가 아니다. 지금 고치지 않으면 **나중에는 못 고치게 되기 때문**이다.

- 컬럼을 지우는 마이그레이션은 행이 38개일 때와 38만 개일 때 위험도가 다르다.
  지금은 잠금 시간이 사실상 0이고, 실수해도 되돌릴 데이터가 적다.
- 데모 데이터가 운영 테이블에 섞여 있는데, 지금은 그 비율이 커서 **눈에 보인다.**
  진짜 사용자 데이터가 쌓이면 문자열 매칭으로 골라내는 일이 위험해진다.
- 중복 저장(번역 4곳·원문 2곳)은 지금은 «약간 지저분»이지만, 재구축 스크립트
  (`scripts/rebuild_school_events.py`, `scripts/sweep_footer_dates.py`,
  `lib/schedule-backfill.ts`)가 **이미 세 개나 생겼다.** 이 스크립트들의 존재 자체가
  네 곳이 서로 어긋나고 있다는 증거다.

즉 **지금이 가장 싸고 가장 안전한 시점**이다.

### 1.3 사업 A 위에 얹힌다 — 선행 조건

사업 A가 두 가지를 깔아준다. 둘 다 이 사업의 전제다.

| 사업 A가 하는 것 | 사업 D가 그 위에서 얻는 것 |
|---|---|
| A4 — 마이그레이션 이력 정합(`migration repair`) + `supabase db push` 자동화 | 이 사업이 만드는 마이그레이션 7~9개를 **손으로 넣지 않아도 된다** |
| A2 — `TEST_ENTRY_BYPASS` 제거, 인증 경로 복구 | service_role RLS 우회 13곳 중 **조건부 우회 8곳이 자동 소멸**(§12) |
| A2 — `lib/test-entry-bypass.ts` 제거 | **새 데모 데이터가 더 이상 생기지 않는다** → 이 사업은 이미 들어간 것만 치우면 된다 |

> ⚠️ **A4 이력 정합 전에는 이 사업의 어떤 마이그레이션도 만들지 않는다.**
> 사업 A 조사 결과 원격 이력에 0001~0033만 기록되어 있고,
> `0030_school_events_end_date.sql`과 `0034_child_dietary_restrictions.sql`은
> **DB에 적용되어 있으나 이력에 없다**(손으로 넣고 기록을 안 남긴 것).
> 이 상태에서 `db push`를 돌리면 CLI가 재실행을 시도한다.
> (이 이력 실측은 사업 A의 조사 결과이며 이 문서에서 재확인하지 않았다 — «미확인».)

---

## 2. 목표 / 비목표

### 목표

1. `schema-migration-plan.md`의 **Phase 3·4를 완료**하고 계획 문서를 «완료»로 닫는다.
2. `schools`에서 크롤러 상태 컬럼 6개가 사라지고, 크롤 상태의 정본이 `school_crawl_state` 하나가 된다.
3. `types/database.ts`가 **손으로 관리되지 않는다.** CI가 드리프트를 잡는다.
4. 데모 데이터가 운영 테이블에서 사라지고, 문자열 매칭이 아닌 방법으로 식별된다.
5. 코드가 실제로 도는 쿼리에 인덱스가 있다(지금 필요해서가 아니라, 나중에 필요할 때 이미 있어야 하니까).
6. 깨진 스크립트가 고쳐지거나 지워진다. «있는데 안 도는 것»이 남지 않는다.

### 비목표 (이 사업에서 하지 않는다)

- 🔴 **번역 이력·감사 payload 제거 (기존 계획의 Phase 6).**
  **사용자 결정 (2026-08-27): "과거 번역 정보 필요할 수도 있으니까 이 부분은 남겼으면 좋겠다."**
  `notice_ai_translations`는 이미 `0019`/`0020`/`0024`/`0025`로 컬럼 5개가 제거된 상태이고,
  **여기서 중단한다.** 남은 10개 컬럼(`translated_text`, `translated_title`,
  `translated_location`, `validation_status`, `source_language` 등)은 **하나도 지우지 않는다.**
  §11의 중복 저장 정리도 «삭제»가 아니라 «canonical 정의»로만 다룬다.
- **관리자 권한 체계 복구** — `profiles.role` / `user_role` enum 되살리기는 사업 F.
  이 사업의 §9(profiles 정리)는 `role`을 건드리지 않는다(이미 `0012`에서 삭제됨).
- **백엔드 FastAPI 엔드포인트 인증** — 사업 A 비목표 그대로 유지.
- **첨부 버킷 비공개 전환** — 사업 A(A3)가 한다. 이 사업은 `notice-originals` 유령 버킷만 치운다.
- **추출/번역 품질** — 사업 C.
- **`meals` ↔ `schools` FK 도입** — §13에 설계는 적지만 **이번 사업에서 실행하지 않는다**(열린 질문 3).

---

## 3. 기존 계획 대비 진행 현황 — 확정본

`schema-migration-plan.md`의 6단계를 마이그레이션 파일을 직접 읽어 검증했다.

| Phase | 계획 내용 | 실제 상태 | 근거 |
|---|---|---|---|
| **1** | `notice_ai_translations.requires_admin_review` / `admin_review_reason`, `schedules.gcal_event_id`, `profiles.role`, `user_role` enum, review 인덱스 제거 | ✅ **완료** | `0012_phase1_schema_cleanup.sql:6-18` — 5개 항목 전부 한 파일에 있음 |
| **2** | `children.school_name`, `neis_office_code`, `neis_school_code` 제거 | ✅ **완료** | `0014`(soft detach) → `0015`(null 백필) → `0016_drop_children_duplicated_school_fields.sql:32-35`. `0016:1-21`이 «미해결 자녀 0건» 가드까지 검증 후 drop |
| **3** | `profiles.email`, `display_name`, `avatar_url` 정리 | ❌ **미실행** | `profiles`를 건드린 마이그레이션은 `0001`(생성)과 `0012`(role drop) **둘뿐**. 세 컬럼 모두 살아 있음 |
| **4** | `schools` crawler 상태 분리 | ⚠️ **90% — 원본 컬럼 미삭제** | `0013_school_crawl_state.sql:1-73`이 테이블 생성 + 백필 + 인덱스 + 트리거 + RLS까지 했으나 **`schools`의 crawl_* 6컬럼과 인덱스 2개를 drop하지 않음** |
| **5** | `schedules` → `school_events` | ✅ **완료** | `0017_school_events.sql`(생성 + dedupe 백필 + 인덱스 2 + 트리거 + RLS) → `0018_drop_legacy_schedules.sql:1` `drop table if exists public.schedules;` |
| **6** | `notice_ai_translations` 슬림화 | ⏸ **일부 진행 후 의도적 중단** | `0019`(source_text·ingredient_identity_map·validation·raw_pipeline), `0020`(metadata), `0023`(→`notices.source_hard_facts` 이관), `0024`, `0025`. **사용자 결정에 따라 여기서 종료** — 비목표(§2) |

### 3.1 표에서 고친 것

브리핑에 적힌 진행 상태 대비 세 곳을 교정했다.

| 항목 | 브리핑 | 검증 결과 |
|---|---|---|
| Phase 4 계획 컬럼 수 | 5개(`crawl_status`, `crawl_error_message`, `crawl_result`, `crawl_board_url`, `crawl_last_checked_at`) | **6개.** `crawl_board_kind`가 계획 문서(`schema-migration-plan.md:210-218`)에서 빠져 있으나 `0002_school_crawler_state.sql:4`가 실제로 추가했고 `0013:4`가 새 테이블에 그대로 옮겼다. **CHECK 제약 `schools_crawl_board_kind_check`(`0002:19-21`)도 함께 사라진다**(컬럼 drop 시 자동) |
| 마이그레이션 개수 | 37개 | **35개 파일.** `0001`~`0034` + `0036`. **`0035`는 결번**(사업 A §7.5가 `child_personal_schedules`용으로 예약), **`0030`은 번호 중복 2개** |
| Phase 5 잔여 | "production 반영 전 row count 재확인" | `0018`이 실제로 drop을 실행했고 `schedules` 참조는 코드 전체에서 `scripts/seed-arabic-demo-account.cjs:494,504` **두 줄뿐**(§10) |

---

## 4. 작업 단위

되돌리기 쉬운 것부터. **파괴적 변경은 항상 뒤에 온다.**

| | 단위 | 크기 | 되돌리기 | 절 |
|---|---|---|---|---|
| **D1** | `types/database.ts` 자동 생성 전환 | npm 스크립트 1 + CI 잡 1 | 스크립트·잡 삭제 | §5 |
| **D2** | 인덱스 6개 추가 | SQL 6줄 (additive) | `drop index` | §6 |
| **D3** | 저위험 위생 — 트리거 2 · 중복 정책 1 · 유령 버킷 1 | SQL ~10줄 | 역 SQL | §7 |
| **D4** | 깨진 스크립트 처리 | 파일 1개 삭제 (또는 재작성) | `git revert` | §10 |
| **D5** | 데모 데이터 분리·제거 | 코드 + 데이터 삭제 SQL | 시드 재실행 | §11 |
| **D6** | **Phase 4 완결** — `schools.crawl_*` 제거 | 코드 2블록 → 컬럼 6 + 인덱스 2 | 2배포 분리 | §8 |
| **D7** | **Phase 3** — `profiles` 정리 | 코드 4곳 → 컬럼 2~3 | 2배포 분리 | §9 |
| **D8** | 죽은 컬럼·상태 제거 | 컬럼 1 + CHECK 1 + 데드코드 | 역 SQL | §13.1 |
| **D9** | 타입·모델링 교정 | 제약 3~4개 | 역 SQL | §13.2 |
| **D10** | service_role RLS 우회 정리 | 렌더 경로 5~13곳 | 코드 되돌리기 | §12 |
| **D11*** | 경쟁 상태 해소 | 백엔드 1함수 + DB 함수 1 | 코드 되돌리기 | §14 |
| **D12*** | 중복 저장 canonical 정의 | 문서 + 읽기 경로 | — | §15 |

\* **D11·D12는 «포함 여부 미결»이다.** 설계는 제시하되 착수 승인은 열린 질문(§19)에 남긴다.

---

## 5. D1 — `types/database.ts` 자동 생성 전환

### 5.1 현재 상태 — 손으로 쓰고 있고, 이미 어긋났다

`types/database.ts`(449줄)는 `supabase gen types`의 산출물이 **아니다.**

| 증거 | 위치 |
|---|---|
| 모든 테이블의 `Relationships: []`가 비어 있음 | `types/database.ts:41,90,124,154,225,261,277,300,325,368,404,425` (12곳 전부) |
| `Views` / `Enums` / `CompositeTypes`가 자리표시자 | `types/database.ts:428-447` — `[_ in never]: never` |
| `gen:types` npm 스크립트 없음 | `package.json:5-11` — `dev/build/start/lint/typecheck` 5개뿐 |
| `supabase` CLI가 devDependency에 없음 | `package.json:26-32` |

**실측 드리프트 4건:**

| # | 어긋난 곳 | 실제 스키마 | 타입 파일 |
|---|---|---|---|
| 1 | `app_jobs` **테이블 통째로 누락** | `0027_app_jobs.sql:1-17` (14컬럼) | 선언 없음 |
| 2 | `school_crawl_state.board_watermarks` 누락 | `0033_school_crawl_state_board_watermarks.sql:5` | `types/database.ts:92-125`에 없음 |
| 3 | `schools.crawl_*` 6개가 잔존 | `0013` 이후 정본이 아님 (D6에서 삭제 예정) | `types/database.ts:51-56, 67-72, 82-87` |
| 4 | `validation_status` 유니언 불일치 | DB 기본값 `'human_review_required'`, CHECK는 3값 (`0005:14-15`) | `types/database.ts:7` = `'passed' \| 'failed'` — **기본값을 포함조차 안 함** |

부수 발견: `docs/supabase/schema.md`도 stale이다. 마지막 커밋 2026-05-20(`29b3c38`)이고
`schedules`를 여전히 살아 있는 테이블로 서술(`docs/supabase/schema.md:13`)하며,
`school_events` · `school_crawl_state` · `notice_card_translations` · `app_jobs` ·
`notice_ai_translations` · `subject_translations`가 전부 빠져 있다.

### 5.2 설계

```
package.json scripts:
  "gen:types": "supabase gen types typescript --linked --schema public > types/database.generated.ts"
```

**두 파일로 나눈다.**

| 파일 | 성격 | 관리 |
|---|---|---|
| `types/database.generated.ts` | `supabase gen types` 산출물. **손으로 고치지 않는다** | `npm run gen:types` |
| `types/database.ts` | 기존 경로 유지. generated를 re-export하고, 앱이 쓰는 **의미 별칭**(`SupportedLocale`, `NoticeStatus`, `CardType`, `SchoolCrawlBoardKind`, `NoticeAiValidationStatus`)만 손으로 정의 | 사람 |

이렇게 나누는 이유: 현재 파일의 `types/database.ts:3-7` 5개 유니언 타입은
**DB에 enum이 없고 text + CHECK로 표현된 것들**이라 `gen types`가 만들어주지 못한다
(`gen types`는 `string`으로 뱉는다). 그 5줄을 지키려면 분리가 필요하다.
전 저장소가 `@/types/database`를 import하므로 import 경로 변경은 0건이다.

### 5.3 CI 드리프트 검사

`.github/workflows/ci.yml`의 `validate-web` 잡에 스텝 추가:

```
- gen:types 를 임시 파일로 실행
- git diff --exit-code 로 types/database.generated.ts 와 비교
- 다르면 실패, "npm run gen:types 를 돌리고 커밋하세요" 안내
```

자격증명은 사업 A(A4)가 이미 등록한 `SUPABASE_ACCESS_TOKEN` + `SUPABASE_PROJECT_REF`를 재사용한다.
**추가로 발급할 시크릿이 없다.**

> ⚠️ 순서 제약: 이 검사는 `db push`가 끝난 뒤 상태를 기준으로 판단해야 한다.
> PR 단계에서는 **아직 적용되지 않은 마이그레이션 때문에 항상 실패한다.**
> 따라서 **PR에서는 경고(continue-on-error), `main` push에서만 차단**으로 시작한다.

### 5.4 부수 작업

`docs/supabase/schema.md`를 현재 스키마로 다시 쓰거나, D1의 generated 파일을
정본으로 삼고 **이 문서를 삭제**한다 (열린 질문 아님 — 재작성을 기본으로 한다).

---

## 6. D2 — 인덱스 추가

38행에서는 아무 차이도 안 난다. **지금 넣는 이유는 나중에 넣기가 어렵기 때문이다**
(운영 중 `create index`는 `concurrently`가 필요하고, 그건 트랜잭션 밖에서 돌아야 해서
마이그레이션 파일에 넣기 까다롭다).

### 6.1 우선순위별 목록

| # | 인덱스 | 우선 | 근거 쿼리 | 현재 상태 |
|---|---|---|---|---|
| 1 | `notice_cards (notice_id)` | 🔴 | 아래 표 | **`notice_cards`에는 PK(`notice_cards_pkey`) 하나뿐.** 마이그레이션 전체에 `notice_cards` 인덱스 생성문이 `0001` PK 외 0건 |
| 2 | `children (user_id)` (비부분) | 🟠 | `lib/server-cache.ts:97, 119` — `.eq('user_id', userId)` 단독 | 기존 `children_user_school_id_idx`가 `(user_id, school_id) WHERE school_id IS NOT NULL` 부분 인덱스(`0003:13-15`)라, 조건 없는 `WHERE user_id=?`는 부분 조건을 증명 못 해 **못 탄다** |
| 3 | `notices (school_id, status, created_at DESC)` | 🟠 | `app/(app)/page.tsx:266-274` — `.eq('school_id').eq('status','done').order('created_at' desc).limit(50)` | `notices_school_id_idx`는 `school_id` 단일. 정렬·필터가 인덱스 밖 |
| 4 | `notices (status, created_at)` (전체 커버) | 🟡 | `content_extraction_service.py:1162`, `:1241` — `.in_('status', ['pending','error','processing'])` | `notices_extraction_claim_idx`의 조건이 `status IN ('pending','error')`(`0007:16`), `notices_extraction_stale_processing_idx`가 `status='processing'`(`0007:24`). **세 값을 한 번에 묻는 쿼리는 어느 쪽에도 안 맞아 시퀀셜 스캔** |
| 5 | `app_jobs (job_key, created_at DESC)` / `app_jobs (started_at)` | 🟡 | `job_queue_service.py:108`(`completed_recently`), `:125`(`latest_job`), `:152`(`.lt("started_at", cutoff)`) | `app_jobs_active_job_key_idx`가 `WHERE status IN ('queued','processing')` 부분(`0027:22-24`) → **완료된 잡을 job_key로 찾는 위 두 쿼리는 밖** |
| 6 | `children (school_id)` | 🟢 | `content_extraction_service.py:1013-1015` — `.eq('school_id', school_id)` 단독. + RLS `school events select own school`(`0017:86-95`)의 `children.school_id = school_events.school_id` | 복합 인덱스의 **선두 컬럼이 아니라** 못 탄다. **이 항목은 이번 조사에서 새로 발견한 것** |

### 6.2 🔴 1번 — `notice_cards(notice_id)` 상세

`notice_cards`는 `notice_id`로만 조회되는데 그 컬럼에 인덱스가 없다. 호출처 실측:

| 계층 | 위치 |
|---|---|
| 프론트 렌더 | `lib/notices.ts:133`, `lib/schedule-backfill.ts:50`, `app/(app)/page.tsx:322` |
| API 라우트 | `app/api/notices/[noticeId]/process/route.ts:99`, `app/api/notices/translation-batch-status/route.ts:75` |
| 백엔드 | `notice_service.py:916`, `:1036`, `:1046`, `:1066`, `:1074`, `:1080`, `:1254`, `:1271` |
| 데모 시드 | `lib/demo-school.ts:1152`, `:1360`, `:1367`, `:1374`, `:1380` |
| **RLS 정책 2개** | `0006/0009` `notice cards select own school`, `0008` `notice cards select own school notice` — **둘 다 매 행마다 `notices.id = notice_cards.notice_id` 조인**(§7.2) |
| **FK 캐스케이드** | `0001:61` `references notices(id) on delete cascade` — 인덱스 없는 FK는 부모 삭제 시 전체 스캔 |

### 6.3 🟠 2번 — `children(user_id)`의 정확한 근거

> **브리핑 교정.** 브리핑은 «RLS 정책 5개가 `EXISTS (SELECT 1 FROM children WHERE user_id=auth.uid())`를 돌아 전 테이블 읽기 성능에 영향»이라고 했다. 검증 결과 정책은 **6개**이고, 그중 4개는 `user_id`와 `school_id`를 **함께** 걸기 때문에 기존 부분 인덱스 `(user_id, school_id) WHERE school_id IS NOT NULL`을 **탈 수 있다**(등호 비교가 NOT NULL을 함의하므로 Postgres가 부분 조건을 증명한다).

`children` EXISTS 서브쿼리를 쓰는 정책 6개:

| # | 테이블 | 정책 | 마이그레이션 | 기존 부분 인덱스로 커버? |
|---|---|---|---|---|
| 1 | `notices` | `notices select own school` | `0003:30-40` | ✅ (user_id + school_id) |
| 2 | `notice_cards` | `notice cards select own school` | `0006:52-62` / `0009:53-63` | ✅ |
| 3 | `notice_cards` | `notice cards select own school notice` | `0008:10-21` | ✅ (중복 정책 — §7.2) |
| 4 | `notice_ai_translations` | `notice ai translations select own school notice` | `0008:35-46` | ✅ |
| 5 | `school_events` | `school events select own school` | `0017:86-95` | ⚠️ **school_id만** → 6번 인덱스가 필요 |
| 6 | `notice_card_translations` | `notice card translations select own school` | `0026:21-32` | ✅ (3중 조인이라 가장 무거움) |

따라서 **`children(user_id)` 비부분 인덱스의 진짜 근거는 RLS가 아니라 `lib/server-cache.ts`의
`.eq('user_id', userId)` 단독 쿼리 2개**(`:97`, `:119`)와, `children` 자신의
`children manage own` 정책(`0001:148-151`, `auth.uid() = user_id`)이다.

부수 관찰: 정책 6개 모두 `auth.uid()`를 `(select auth.uid())`로 감싸지 않아 행마다 재평가된다.
이건 인덱스와 별개의 최적화이고, 38행 규모에서는 무의미하므로 **이번 사업 범위 밖으로 둔다**.

### 6.4 롤백

전부 additive다. 각 인덱스는 `drop index if exists` 한 줄로 되돌아간다.
기존 인덱스를 지우지 않는다 — `children_user_school_id_idx`도 그대로 둔다
(복합 조회는 여전히 그쪽이 낫다).

---

## 7. D3 — 저위험 위생

### 7.1 `updated_at` 트리거 누락 2건

컬럼은 있는데 트리거가 없다. 즉 **UPDATE해도 `updated_at`이 안 바뀐다.**

| 테이블 | 컬럼 도입 | 트리거 | 실제 영향 |
|---|---|---|---|
| `notice_card_translations` | `0026:7` | **없음** | 코드도 수동으로 안 채운다(`notice_service.py:1110-1121` upsert payload에 `updated_at` 없음) → **삽입 시각에 영원히 고정** |
| `app_jobs` | `0027:15` | **없음** | 코드가 수동으로 채운다(`job_queue_service.py:224` 등). 누락 경로가 있으면 조용히 stale |

조치: 두 테이블에 `set_updated_at()` 트리거를 붙인다. 함수는 `0001:105-111`에 이미 있고
다른 6개 테이블(`profiles`, `notices`, `schools`, `notice_ai_translations`,
`school_crawl_state`, `school_events`)이 같은 패턴을 쓴다.

`app_jobs`는 트리거를 붙인 뒤 `job_queue_service.py`의 수동 `updated_at` 세팅을 남겨도
무해하다(트리거가 덮어쓴다). **코드 변경 없이 SQL만으로 끝난다.**

### 7.2 `notice_cards` 중복 RLS 정책

| 정책 | 마이그레이션 | USING |
|---|---|---|
| `notice cards select own school` | `0006:52-62`, `0009:44-66`이 재보장 | `EXISTS(notices JOIN children ON children.school_id = notices.school_id WHERE notices.id = notice_cards.notice_id AND children.user_id = auth.uid())` |
| `notice cards select own school notice` | `0008:10-21` | **위와 동일 + `notices.school_id is not null`** |

두 번째 정책의 추가 조건 `notices.school_id is not null`은 **`0006:81`이 `school_id`를
NOT NULL로 만든 이후 항상 참**이다. 즉 두 정책은 논리적으로 동일하다.
PERMISSIVE 정책이라 결과는 OR로 합쳐져 같지만, `notice_cards` SELECT마다
거의 같은 EXISTS 서브쿼리가 **두 번** 평가된다.

조치: `0008`이 만든 `notice cards select own school notice`를 **drop**한다.
(`0006`/`0009` 쪽을 남기는 이유: `0009`가 idempotent 가드로 재생성까지 하고 있어
그쪽이 실질적 정본이다.)

> 참고: `notice_ai_translations`는 중복이 아니다. `0006:42`가 구 정책
> `notice ai translations select own notice`를 drop하고 `0008:35`가 새 정책을
> 만드는 순서라 하나만 남는다.

### 7.3 유령 스토리지 버킷 `notice-originals`

| 사건 | 위치 |
|---|---|
| 생성 (private, 10MB, 이미지/PDF) | `0001_initial_schema.sql:243-254` |
| 정책 3개 생성 | `0001:256-278` |
| 정책 3개 **전부 drop** | `0006:92-94` (`0009:101-103` 재실행) |
| 유일한 참조 테이블 `document_files` **drop** | `0006:65` (`0009:68`) |
| 버킷 삭제 | ❌ **안 됨.** `0006:91` 주석: *"bucket 자체는 Supabase Dashboard > Storage 에서 수동으로 삭제할 것"* |

코드 참조 0건. **마이그레이션이 스스로 «수동으로 지우라»고 적어두고 3개월간 안 지워진 것**이다.

조치: `delete from storage.buckets where id = 'notice-originals';`
버킷이 비어 있는지 먼저 확인하는 가드를 붙인다(오브젝트가 있으면 FK로 실패한다 — 그때는 중단).

---

## 8. D6 — Phase 4 완결: `schools.crawl_*` 제거

### 8.1 현재 지형

| 사실 | 근거 |
|---|---|
| `schools`에 crawl_* **6컬럼**이 살아 있음 | `0002_school_crawler_state.sql:3-8`. `0013`이 drop하지 않음 |
| 죽은 인덱스 2개도 살아 있음 | `schools_crawl_status_idx`(`0002:26`), `schools_crawl_last_checked_at_idx`(`0002:29`). drop된 적 없음 |
| CHECK 제약도 남아 있음 | `schools_crawl_board_kind_check`(`0002:19-21`) — 컬럼 drop 시 자동 소멸 |
| 새 테이블 쪽에만 있는 컬럼이 생김 | `school_crawl_state.board_watermarks`(`0033:5`) — **두 테이블의 스키마가 이미 갈라졌다** |
| 타입 파일도 여전히 선언 | `types/database.ts:51-56, 67-72, 82-87` |

**읽기는 이미 완전히 이전됐다.**

| 읽는 쪽 | 대상 |
|---|---|
| TS 전부 | `lib/school-crawl-state.ts:44-57, 66-80` → `school_crawl_state`만 |
| `lib/server-cache.ts:136` | `getSchoolCrawlerState()` 경유 → `school_crawl_state` |
| `app/api/schools/[schoolId]/crawl/route.ts:54` | 동일 |
| `backend/.../scheduled_crawler_service.py:239-249, 267-282` | `schools`에서는 **`id,name`만** 읽고 crawl_*는 `school_crawl_state`에서 |

TS의 `.from('schools')` 20곳을 전수 확인한 결과, **crawl_* 컬럼을 select하는 곳은 0건**이다.
읽는 것은 `id, name, address, homepage_url, neis_office_code, neis_school_code`뿐.

### 8.2 🔴 삭제를 막고 있는 것 — 두 블록

**(1) `backend/app/services/school_crawler_service.py:624-643` — 이중 쓰기**

```python
624:        school_payload: dict[str, Any] = {
625:            "crawl_status": result.status,
626:            "crawl_error_message": result.error_message,
627:            "crawl_result": result.to_dict(),
628:            "crawl_last_checked_at": state_payload["crawl_last_checked_at"],
629:        }
630:        if result.homepage_url:
631:            school_payload["homepage_url"] = result.homepage_url
632:        if result.verified and result.board_url:
633:            school_payload["crawl_board_url"] = state_payload.get("crawl_board_url")
634:            school_payload["crawl_board_kind"] = state_payload.get("crawl_board_kind")
635:
636:        supabase.table("schools").update(school_payload).eq("id", result.school_id).execute()
640:        supabase.table("school_crawl_state").upsert(state_payload, on_conflict="school_id").execute()
```

`state_payload`(607-620)와 값이 완전히 같다. 같은 값을 두 테이블에 두 번 쓴다.
두 문장이 트랜잭션으로 묶여 있지도 않아, 636이 성공하고 640이 실패하면 두 테이블이 갈린다
(예외는 `:644-645`에서 `RuntimeError`로 뭉뚱그려진다).

> ⚠️ **브리핑 교정: 「`schools` UPDATE를 통째로 제거」하면 안 된다.**
> `homepage_url`(630-631)은 **`schools`에만 있고 `school_crawl_state`에는 없다**
> (`0013`에 미포함, `types/database.ts:92-125`에도 없음).
> 크롤러가 크롤 대상 URL을 얻는 유일한 경로가 `school_crawler_service.py:360`
> (`_context_from_school_row`)이고, 그 값이 `schools.homepage_url`이다.
> 따라서 **`school_payload`에서 crawl_* 6키만 빼고, `homepage_url` 백필은 남긴다.**
> `homepage_url`이 없으면 payload가 빈 dict가 되므로 **`if school_payload:` 가드를 추가**한다.

**(2) `scripts/seed-arabic-demo-account.cjs:275-288` — `schools` upsert에 crawl_* 6개 포함**

TS/JS 쪽에 남은 유일한 `schools.crawl_*` 쓰기다. D4(§10)에서 이 스크립트를 처리하면
자동으로 해소된다. **D6는 D4 이후에 온다.**

### 8.3 폴백 경로 — 이미 사실상 도달 불가

`school_crawler_service.py:327-351` `_fetch_school_row()`:

```python
330:        supabase.table("schools").select("*")     # crawl_* 까지 통째로 긁어옴
338:    row = dict(result.data[0])
339:    state_result = supabase.table("school_crawl_state").select("school_id,crawl_board_url,...")
349:    if state_result.data:
350:        row.update(dict(state_result.data[0]))    # 상태 행이 있으면 덮어씀
```

> **브리핑 교정.** 이건 «명시적 폴백 코드»가 아니다. `select("*")`가 죽은 컬럼까지
> 긁어오기 때문에 **우연히** 생기는 폴백이다. 상태 행이 없을 때만 `schools`의
> 낡은 값이 살아남는다.

그리고 **상태 행이 없는 학교는 이제 생기지 않는다:**

| 학교 생성 경로 | 상태 행 보장 |
|---|---|
| 온보딩 | `app/onboarding/actions.ts:115, 144, 160` — `ensureSchoolCrawlerState()` |
| 설정에서 학교 변경 | `app/(app)/settings/actions.ts:87, 116, 132` — 동일 |
| 테스트 우회 (사업 A에서 제거) | `lib/test-entry-bypass.ts:217` — 동일 |
| 데모 시드 | `lib/demo-school.ts:1286-1302` — `school_crawl_state` upsert |
| 기존 8개 학교 | `0013:28-58`이 전부 백필 |

즉 **폴백은 이미 죽어 있다.** 그래도 구조적으로 없애기 위해
`:331`의 `select("*")`를 `select("id,name,address,homepage_url,neis_office_code,neis_school_code")`로
좁힌다. 이렇게 하면 컬럼을 지운 뒤에도 이 코드가 그대로 돈다.

### 8.4 배포 설계 (2배포 필수)

| 배포 | 변경 | 되돌리기 |
|---|---|---|
| **D6-a (코드)** | ① `school_crawler_service.py:624-634`에서 crawl_* 6키 제거 + `if school_payload:` 가드 ② `:331` `select("*")` → 명시 컬럼 목록 ③ `types/database.ts`에서 `schools.crawl_*` 제거(D1 이후면 `gen:types` 재실행으로 자동) | 코드 되돌리기. **DB는 아직 그대로라 즉시 원복 가능** |
| **D6-b (DB)** | `alter table public.schools drop column if exists crawl_status, crawl_error_message, crawl_result, crawl_board_url, crawl_board_kind, crawl_last_checked_at;` + `drop index if exists schools_crawl_status_idx, schools_crawl_last_checked_at_idx;` | ⚠️ **복구 마이그레이션 필요.** 값 복구는 `school_crawl_state`에서 역백필 가능 |

**D6-a 배포 후 최소 1회 크롤을 돌려 `school_crawl_state`만으로 정상 동작하는지 확인한 뒤에
D6-b로 넘어간다.** 두 배포를 같은 PR에 넣지 않는다.

`homepage_url`은 **남긴다.** 이 사업에서 건드리지 않는다.

---

## 9. D7 — Phase 3: `profiles` 정리

### 9.1 현재 컬럼과 사용처

`profiles`를 건드린 마이그레이션은 `0001:8-18`(생성)과 `0012:15-16`(`role` drop) 둘뿐이다.

| 컬럼 | 읽는 곳 | 쓰는 곳 | 판정 |
|---|---|---|---|
| `id` | 다수 | `app/onboarding/actions.ts:74`, `app/api/auth/dev-login/route.ts:68` | 유지 |
| `email` | `app/onboarding/actions.ts:62, 76-77`, `app/api/auth/dev-login/route.ts:63, 69` | 같은 두 곳 | **읽는 유일한 목적이 «자기가 방금 쓴 값 다시 쓰기»** — `auth.users.email`이 canonical |
| `display_name` | `app/onboarding/actions.ts:62, 78`, `dev-login/route.ts:63, 70` | 같은 두 곳 | 동일. **UI에서 렌더하는 경로 0건** |
| `avatar_url` | ❌ **0건** | ❌ **0건** | `types/database.ts:17,27,36` 세 줄이 전부. **완전 사망** |
| `locale` | `dev-login/route.ts:71`, `process/route.ts:145-146`, `upload/route.ts:80-81`, `content_extraction_service.py:1042` | `onboarding/actions.ts:79`, `app/api/locale/route.ts:27`, `dev-login/route.ts:71` | 유지 |
| `native_language` | 위와 같은 4곳(항상 `locale`과 함께) | `onboarding/actions.ts:80`, `dev-login/route.ts:72` | §9.2 |
| `created_at` / `updated_at` | 0건 (트리거 `0001:113-115`) | 트리거 | 유지 |

`components/`, `lib/`에는 `profiles` 접근이 **전혀 없다.**
Python 프로덕션 코드에서 `profiles` 접근은 `content_extraction_service.py:1032-1045` **한 곳**뿐이다.

### 9.2 ⚠️ `locale` / `native_language` — 브리핑 교정

브리핑은 «`app/onboarding/actions.ts:79-80`이 같은 값을 둘 다에 쓴다. 완전 중복»이라고 했다.
**앞 절반은 맞고 뒤 절반은 틀리다.**

```ts
// app/onboarding/actions.ts:72-83
79:      locale: input.locale,
80:      native_language: input.locale,     // ← 온보딩 시점엔 같은 값
```

그러나:

| 사실 | 근거 |
|---|---|
| `locale`은 이후 갱신된다 | `app/api/locale/route.ts:25-28` — `locale`만 update |
| `native_language`는 **갱신 경로가 없다** | 저장소 전체에서 `native_language` 쓰기는 `onboarding/actions.ts:80`과 `dev-login/route.ts:72` 둘뿐 |
| → 언어를 바꾸면 **두 값이 영구히 갈라진다** | |
| 백엔드는 **둘의 합집합**을 번역 대상 locale로 쓴다 | `content_extraction_service.py:1042-1043`, 테스트 `backend/tests/test_content_extraction_service.py:404-406, 459-460`이 그 분기를 검증 |
| TS 쪽에서는 `native_language`가 **도달 불가 fallback** | `process/route.ts:145-149`, `upload/route.ts:80-84` — `locale`이 `not null default 'ko'`이고 유효값만 기록되므로 2순위에 도달하지 않음 |

즉 **의미가 있다.** `locale` = «지금 보고 싶은 언어», `native_language` = «온보딩 때 고른 모국어».
`native_language`가 살아 있어야 «UI는 한국어로 바꿨지만 번역본은 모국어로도 만들어 둔다»가 성립한다.

**결정: `native_language`를 지우지 않는다.** 대신 의도를 명시한다 —
`0001:14`의 컬럼 주석 추가 + `app/onboarding/actions.ts:80`에 «온보딩 1회 고정» 주석.

한편 이 설계가 의도된 것인지, 아니면 갱신 경로를 만들다 만 것인지는 **미확인**이다.
설정 화면에 «모국어» 항목이 없으므로 사용자가 나중에 바꿀 방법이 없다 — 열린 질문(§19 Q4).

### 9.3 설계

| 컬럼 | 조치 | 이유 |
|---|---|---|
| `avatar_url` | 🔴 **삭제** | 읽기·쓰기 0건. 위험 0 |
| `email` | 🟠 **삭제** | `auth.users.email`이 canonical. 유일한 소비자가 «자기가 쓴 걸 다시 읽어 다시 쓰는» 루프. 백엔드는 `profiles`에서 email을 안 읽는다 |
| `display_name` | 🟠 **삭제** | UI 렌더 경로 0건. 사용자 이름은 `children.name`으로 표시된다(`app/(app)/page.tsx:258`) |
| `locale` | 유지 | |
| `native_language` | 유지 + 주석 | §9.2 |

> ⚠️ `email`/`display_name` 삭제는 **운영/문의 대응 시 프로필 스냅샷이 필요한가**에 달려 있다.
> `schema-migration-plan.md:188-196`도 같은 질문을 남겼다.
> `auth.users`에서 조회 가능하므로 기능 손실은 없지만, **service_role 없이는 못 본다.**
> 열린 질문 아님 — **삭제를 기본으로 하되, 사용자가 «남겨라» 하면 `avatar_url`만 지운다.**

### 9.4 배포 (2배포)

| 배포 | 변경 |
|---|---|
| **D7-a (코드)** | `onboarding/actions.ts:61-64, 72-83`과 `dev-login/route.ts:61-65, 75-77`에서 `email`/`display_name` select·upsert 제거. 타입 재생성 |
| **D7-b (DB)** | `alter table public.profiles drop column if exists email, display_name, avatar_url;` |

RLS 정책 3개(`0001:130-141`)는 전부 `auth.uid() = id`만 보므로 **영향 없다.**

---

## 10. D4 — 깨진 스크립트 처리

### 10.1 `scripts/seed-arabic-demo-account.cjs` — 15곳 이상에서 깨졌다

마지막 커밋: `4b331ae` / **2026-06-04** / "chore: add arabic demo seed flow".
그 이후 `0012`~`0034`가 적용되며 스키마가 바뀌었고, 스크립트는 방치됐다.

| 위반 | 줄 | 근거 |
|---|---|---|
| `.from('schedules')` delete | **494** | `0018:1` 테이블 drop |
| `.from('schedules')` insert | **504** (payload 505-512) | 동일 |
| `profiles.role: 'parent'` | **260** | `0012:16` |
| `children.school_name` | **315** | `0016:33` |
| `children.neis_office_code` | **318** | `0016:34` |
| `children.neis_school_code` | **319** | `0016:35` |
| `notice_ai_translations.source_text` | 444 | `0019:2` |
| `..source_hard_facts` | 446 | `0024` |
| `..target_hard_facts` | 447 | `0025` |
| `..ingredient_identity_map` | 448 | `0019:3` |
| `..validation` | 449-451 | `0019:4` |
| `..metadata` | 452 | `0020` |
| `..raw_pipeline` | 453-455 | `0019:5` |
| `..requires_admin_review` | 457 | `0012:9` |
| `..admin_review_reason` | 458 | `0012:10` |
| `schools.crawl_*` 직접 upsert | 275-284 | drop되진 않았지만 `0013` 이후 정본이 `school_crawl_state` (§8.2) |

누락된 신규 스키마도 많다: `translated_title`(`0030`), `translated_location`(`0031`),
`notices.event_dates`/`event_location`/`source_hard_facts`(`0021`~`0023`),
`school_events`(`0017`) 미시드, `notice_card_translations`(`0026`) 미시드,
`children.dietary_restrictions`(`0034`) 미설정.

**실행 순서상 첫 실패는 `main()`(189-198)의 191행 `upsertProfile` — 두 번째 스텝에서 즉사한다.**
즉 이 스크립트는 **지금 전혀 돌지 않는다.**

### 10.2 결정: 삭제한다

| 선택지 | 평가 |
|---|---|
| 고친다 | 15곳 이상을 고쳐야 하고, 고쳐도 **`lib/demo-school.ts`(1537줄)와 기능이 겹친다**. 데모 종료 결정(§17)과 정면으로 충돌 |
| **삭제한다** ✅ | 사용자 결정 «데모는 끝났다»와 일치. D5(데모 데이터 제거)와 같은 방향. D6의 `schools.crawl_*` 마지막 쓰기도 함께 사라진다 |

**조치: `scripts/seed-arabic-demo-account.cjs` 삭제.**
그리고 이 파일이 참조하던 `demo-assets/` 관련 자산이 있다면 함께 정리한다
(단 `lib/demo-school.ts:667,681,766,855`가 참조하는 `demo-assets/attachments/*`는
**저장소에 존재하지 않고** 디스크에서 읽지도 않는다 — JSON 문자열로만 저장 — 이므로 별개다).

### 10.3 다른 스크립트는 깨지지 않았다

`scripts/` 45개 파일을 전수 확인한 결과 **드롭된 스키마 요소를 참조하는 다른 스크립트는 없다.**
오탐 후보를 하나씩 검증했다:

| 스크립트 | 매칭 토큰 | 판정 |
|---|---|---|
| `scripts/_diag_notice.py:21`, `_gather_locations.py:18`, `_review_schools.py:40`, `rebuild_school_events.py:63-68` | `source_hard_facts`, `source_text`, `metadata` | ✅ **정상.** `notices.source_hard_facts`는 `0023`으로 **추가**되어 살아 있다. 나머지는 인메모리 파이프라인 dict |
| `scripts/run_iteration.py:130`, `scaffold_translation_quality_iteration.py:68`, `validate_translation_iteration.py:36` | `role` | ✅ **오탐.** JSON 픽스처의 `"role": "training"\|"held_out"` |
| `scripts/_hambak_probe.py:37`, `probe_school_state.py:49`, `probe_demo_schools.py:45` | `neis_*` | ✅ **정상.** `0016`이 지운 건 `children` 쪽뿐, `schools`는 그대로 |
| `scripts/apply_locations.py:86`, `_apply_ru_ar.py:58` | `notice_ai_translations` PATCH | ✅ **정상.** 현행 `translated_location`(`0031`)만 씀 |

참고: `scripts/` 45개 중 **git 추적 대상은 5개뿐**이다
(`run_iteration.py`, `scaffold_translation_quality_iteration.py`,
`seed-arabic-demo-account.cjs`, `translation_quality_driver.py`,
`validate_translation_iteration.py`). 나머지는 untracked 로컬 스크래치이므로
이 사업의 관리 대상이 아니다.

---

## 11. D5 — 데모 데이터 제거

### 11.1 현재 — 문자열 매칭으로 식별한다

`lib/demo-school.ts`(1537줄)가 쓰는 테이블:

| 테이블 | 연산 | 줄 |
|---|---|---|
| `schools` | update | 1276-1284 |
| `school_crawl_state` | upsert | 1286-1302 |
| `notices` | delete → upsert ×2 | 1328-1344 |
| `notice_ai_translations` | upsert ×2 | 1347-1356 |
| `notice_cards` | delete ×2 → upsert ×2 | 1359-1382 |
| `notice_card_translations` | upsert ×2 | 1385-1394 |
| `school_events` | upsert | 1398-1401 |
| `meals` | upsert | 1497-1512 |

식별자는 **플래그가 아니라 문자열**이다:

| 신호 | 값 | 위치 |
|---|---|---|
| 학교 이름 | `'Naranhi School'` | `lib/demo-school.ts:7` |
| NEIS 교육청 코드 | **`'DEMO'`** | `:10` |
| NEIS 학교 코드 | **`'NARANHI001'`** | `:11` |
| 판정 함수 | `isDemoSchoolSelection()` — `(officeCode==='DEMO' && schoolCode==='NARANHI001') \|\| schoolName.toLowerCase()==='naranhi school'` | `:906-919` |
| 공지 UUID prefix | `0d0b8f4c-76a0-4baf-9f41-8f7c2a7d20XX` | `:83, 201, 315, 417, 519, 595, 694, 779` |
| detail_url 스킴 | `'demo://naranhi-school/...'` | `:84, 202, 316, 418, 520` |
| `crawl_result.source` | `'demo'` / `'demo_reused'` | `:1016, 1182, 1296` |
| `source_post_uid` prefix | `demo-...` | `:1012, 1178` |
| 검색 주입 트리거 | `'naranhi' \| 'demo' \| '나란히'` | `:930` |

삭제도 문자열 매칭이다(`:1316-1332`):
`detail_url.startsWith('demo://') || crawl_result.source === 'demo' || === 'demo_reused'`.
그리고 **`schools` 행 자체와 `meals`의 `DEMO/NARANHI001` 행은 한 번도 삭제되지 않는다.**
데모 학교를 만드는 길은 있어도 폐기하는 길이 없다.

`lib/test-entry-bypass.ts`도 별도로 실제 학교 3개
(부천부흥중 `J10/7581020`, 동인천중 `E10/7341072`, 인천함박초 `E10/7341063` —
`lib/test-entry-bypass.ts:33-61`)를 운영 DB에 insert하고 크롤까지 트리거한다.
**사업 A(A2)가 이 파일을 제거한다.**

### 11.2 안전한 식별 방법

문자열 매칭은 두 가지가 위험하다 —
① 진짜 학교 이름에 «데모»가 들어갈 수 있다
② 시드가 바뀌면 삭제 조건이 조용히 어긋난다.

**설계: 삭제 대상을 «학교 1개»로 좁히고, 그 학교 id를 앵커로 FK를 따라간다.**

```
1. 단 하나의 UUID를 확정한다:
     select id from public.schools
     where neis_office_code = 'DEMO' and neis_school_code = 'NARANHI001';
   → 결과가 정확히 1건이 아니면 마이그레이션을 raise exception 으로 중단한다.

2. 그 school_id 하나만 앵커로 쓴다. 이후 어떤 조건에도 문자열을 쓰지 않는다.
```

이유: `schools.neis_office_code`/`neis_school_code`는 애플리케이션이 만드는 값이 아니라
데모 시드가 넣은 **고정 상수**이고(`lib/demo-school.ts:10-11`), 실제 NEIS는
`'DEMO'`라는 교육청 코드를 쓰지 않는다. 그리고 이 값 조합은
`schools_neis_office_code_neis_school_code_key`(`0001:27`) 유니크 제약을 탄다.

### 11.3 삭제 순서 (FK 의존)

실제 FK 정의를 확인한 결과, 대부분 CASCADE가 걸려 있어 **`notices` 삭제만으로
하위가 전부 따라온다**. 그러나 명시적으로 순서를 지켜 실행한다(가시성 + 건수 확인).

| 순서 | 대상 | 조건 | FK |
|---|---|---|---|
| 1 | `notice_card_translations` | `notice_card_id in (select id from notice_cards where notice_id in (…))` | `0026:3` cascade from `notice_cards` |
| 2 | `notice_cards` | `notice_id in (select id from notices where school_id = :demo)` | `0001:61` cascade from `notices` |
| 3 | `notice_ai_translations` | 동일 | `0005:3` cascade from `notices` |
| 4 | `school_events` | `school_id = :demo` | `0017:3-4` cascade 양쪽 |
| 5 | `notice_hides` | `notice_id in (…)` | `0004:3` cascade from `notices` |
| 6 | `notices` | `school_id = :demo` | — |
| 7 | `meals` | `office_code = 'DEMO' and school_code = 'NARANHI001'` | ⚠️ **FK 없음**(§13.2) — 이것만 코드 문자열에 의존할 수밖에 없다 |
| 8 | `school_crawl_state` | `school_id = :demo` | `0013:2` cascade from `schools` |
| 9 | `children` | `school_id = :demo` | ⚠️ `0016:26-30`이 **`ON DELETE RESTRICT`** → 데모 학교에 붙은 자녀가 있으면 10번이 실패한다. **먼저 세고, 있으면 중단하고 사용자에게 보고** |
| 10 | `schools` | `id = :demo` | — |

> ⚠️ 9번이 이 작업의 진짜 위험이다. `children` 9행 중 데모 학교에 붙은 게 있으면
> **실제 사용자 계정이 데모 학교를 쓰고 있다는 뜻**이다. 그 경우 자동 삭제하지 않고
> 사용자에게 보고한다(§18).

### 11.4 코드 제거

| 파일 | 조치 |
|---|---|
| `lib/demo-school.ts` (1537줄) | **삭제** |
| `app/(app)/settings/DemoSchoolPicker.tsx` | **삭제** (사업 A가 `test-entry-bypass`를 지우면 어차피 무의미) |
| `app/onboarding/actions.ts:7, 46, 170` | import·호출 제거 |
| `app/(app)/settings/actions.ts:6, 45, 142` | 동일 |
| `app/(app)/page.tsx:10, 248, 255` | 동일 |
| `app/(app)/meals/page.tsx:4-7, 115, 124, 126` | 동일 |
| `app/api/schools/search/route.ts:3, 23, 26` | `maybeInjectDemoSchoolResult` 제거 → **NEIS 검색 결과만 반환** |

`lib/demo-school.ts`의 export 중 `getDemoMealSourceCodes`(`:1420`)와
`DEMO_NOTICE_SEED_IDS`(`:905`)는 이미 **호출처가 없는 dead export**다.

### 11.5 배포 순서

**코드 먼저, 데이터 나중.** 코드가 살아 있는 동안 데이터를 지우면
다음 렌더에서 `ensureDemoSchoolSeed()`가 다시 뿌린다.

| 배포 | 내용 |
|---|---|
| **D5-a** | 위 코드 제거 배포 → 새 데모 데이터가 생기지 않음을 확인 |
| **D5-b** | §11.3 삭제 마이그레이션 |

---

## 12. D10 — service_role RLS 우회 정리

### 12.1 현재 — 두 종류가 섞여 있다

TS의 `createSupabaseServiceClient()`(`lib/supabase/server.ts:36-52`) 호출 20곳을
전수 분류했다. 로그인 사용자 렌더 경로에 있는 것이 **13곳**이고, 그중 성격이 둘로 갈린다.

**(A) `TEST_ENTRY_BYPASS` 조건부 — 사업 A가 자동 해결한다 (8곳)**

| 위치 | 형태 |
|---|---|
| `app/(app)/page.tsx:227-229` | `testEntryBypass ? createSupabaseServiceClient() : createSupabaseServerClient()` — **주 클라이언트를 통째로 스왑** |
| `app/(app)/calendar/page.tsx:98-100` | 동일 |
| `app/(app)/meals/page.tsx:97-99` | 동일 |
| `lib/notices.ts:109-110` | 동일. `:102` 주석이 "RLS에 의해 본인 자녀의 학교 공지만 반환된다"고 주장하지만 **이 분기에서는 거짓** |
| `app/api/schools/[schoolId]/crawl/route.ts:21-26` | 소유권 검증을 우회 |

> 🔴 그리고 `.github/workflows/deploy-cloud-run.yml:84`가 **프로덕션에 `TEST_ENTRY_BYPASS=true`를
> 설정하고 있다.** 즉 지금 홈·캘린더·급식·공지상세의 주 DB 클라이언트가 service_role이다.
> **이건 사업 A(A2)가 그 env를 제거하는 순간 자동으로 닫힌다.** 이 사업이 할 일이 없다.

**(B) 상시 service_role — 이 사업의 실제 대상 (5곳)**

전부 `lib/server-cache.ts`다.

| # | 함수 | 줄 | 쿼리 | 스코핑 |
|---|---|---|---|---|
| 1 | `fetchSchoolsByIds` | 79-83 | `schools` `.in('id', schoolIds)` | 호출자 신뢰 |
| 2 | `getLatestChildForUser` | 93-100 | `children` `.eq('user_id', userId)` | **코드** |
| 3 | `getChildrenForUser` | 115-120 | `children` `.eq('user_id', userId)` | **코드** |
| 4 | `getSchoolSummary` | 135-136 | `school_crawl_state` | ⚠️ **소유권 검증 없음** |
| 5 | `getHiddenNoticeIds` | 153-157 | `notice_hides` `.eq('user_id', userId)` | **코드** |

### 12.2 ⚠️ 왜 여기가 service_role인가 — 게으름이 아니다

`lib/server-cache.ts`의 5곳은 전부 **`unstable_cache()` 콜백 안**에 있다
(`:91, 113, 133, 151`). Next.js의 `unstable_cache` 콜백은 요청 스코프 밖에서 실행되므로
**쿠키를 읽을 수 없고, 따라서 사용자 세션이 붙은 anon 클라이언트를 만들 수 없다.**

즉 이건 아키텍처 제약이다. 그래서 코드가 RLS가 할 일을 손으로 재현하고 있다 —
`userId`를 캐시 키에 넣고(`:107, 127, 145, 163`) 쿼리에 `.eq('user_id', userId)`를 건다.

**위험**: `userId`를 잘못 넘기는 순간 크로스테넌트 유출이다. RLS는 «못 넘기게» 막지만
코드 스코핑은 «안 넘기기로 약속»한다.

### 12.3 설계 — 세 가지 선택지

| 안 | 내용 | 얻는 것 | 잃는 것 |
|---|---|---|---|
| **①** | `unstable_cache`를 버리고 anon 클라이언트 + `cache()`(요청 스코프)로 전환 | RLS가 실제로 작동. 정책 13개가 주 경로에도 적용 | 요청 간 캐시 소멸 → 홈 렌더당 DB 왕복 증가. TTL 15~30초짜리 캐시의 이점을 잃음 |
| **②** | `unstable_cache`를 유지하되, **호출자가 세션에서 검증한 userId만** 넘긴다는 계약을 타입·검사로 강제 | 성능 유지. 사고 확률 감소 | RLS는 여전히 우회. «약속»이 «강제»가 되지는 않음 |
| **③** | 4번(`getSchoolSummary`)만 고친다 — 소유권 검증이 **아예 없는** 유일한 곳 | 최소 변경으로 최대 위험 제거 | 나머지 4곳의 구조적 문제는 그대로 |

**권고: ③을 이번 사업에 넣고, ①은 별건으로 미룬다.**

이유: ①은 DB 정리가 아니라 **렌더 아키텍처 변경**이다. 홈·캘린더·급식 세 화면의 데이터 흐름을
다시 짜야 하고, 사업 D의 나머지 단위와 성격이 완전히 다르다.
반면 4번은 «`schoolId`만 알면 아무 학교의 크롤 상태를 읽을 수 있다»는
명확한 결함이고, 호출부(`app/(app)/page.tsx:261`)가 이미 `child.school_id`를 갖고 있으므로
**`userId`를 함께 받아 소유권을 확인하는 것으로 끝난다.**

**범위 결정은 열린 질문(§19 Q2)으로 남긴다.**

### 12.4 올바른 패턴 — 이미 저장소 안에 있다

`app/api/schools/[schoolId]/crawl/route.ts`:

| 단계 | 줄 |
|---|---|
| anon 클라이언트 | `:28` `createSupabaseServerClient()` |
| 인증 확인 (실패 시 401) | `:29-32` |
| **소유권 검증** — `children` where `user_id = user.id` and `school_id = schoolId` | `:34-40` |
| 거부 (403 `school_not_allowed`) | `:46-48` |
| **그 후 승격** | `:51` `createSupabaseServiceClient()` |

이 패턴을 §12.3 ③에 그대로 적용한다.

---

## 13. D8 · D9 — 죽은 것 제거와 모델링 교정

### 13.1 D8 — 죽은 컬럼·상태

| # | 대상 | 근거 | 조치 |
|---|---|---|---|
| 1 | `school_events.source_language` | 모든 쓰기가 `'ko'` 하드코딩 — `notice_service.py:1176`, `lib/schedule-backfill.ts:91`, `lib/demo-school.ts:1069`, 그리고 백필 SQL `0017:50`. 읽는 곳 0건. **정보량 0** | `drop column` |
| 2 | `notice_ai_translations.validation_status`의 `'human_review_required'` | DB 기본값(`0005:14`)인데 코드는 `'passed'`(`notice_service.py:659, 749, 779`, `orchestrator.py:443`)와 `'failed'`만 쓴다. 프롬프트도 `"passed\|failed"`(`prompts.py:882`). `types/database.ts:7`의 TS 유니언은 **기본값을 포함조차 안 한다** | ⚠️ 컬럼은 **남긴다**(비목표 §2 — 번역 이력 보존). **기본값과 CHECK만 `'passed'`/`'failed'` 2값으로 좁힌다.** 기존 행에 `'human_review_required'`가 있으면 먼저 세고, 있으면 `'failed'`로 이행할지 사용자에게 묻는다 |
| 3 | `notice_cards`의 `type='schedule'` 읽기 경로 | `_build_notice_cards()`(`notice_service.py:1638-1664`)는 **`action` 카드만 만든다.** 그런데 `lib/schedule-backfill.ts:49-53`이 `.eq('type','schedule')`로 조회하고 `:152-183`이 정규식으로 날짜·"장소:"를 파싱한다 | 데드 코드로 보이나 **과거 데이터에 `type='schedule'` 행이 남아 있을 수 있다 — «미확인»**. D8 착수 전 `select count(*) from notice_cards where type='schedule'`로 실측 후 판단 |
| 4 | `profiles.avatar_url` | §9.3 | D7에 포함 |
| 5 | 유령 버킷 `notice-originals` | §7.3 | D3에 포함 |

### 13.2 D9 — 타입·모델링 교정

| # | 문제 | 근거 | 설계 |
|---|---|---|---|
| 1 | `meals.calories text` — 숫자를 텍스트로 | `0001:89` | `numeric`으로 변경. 값은 NEIS가 `"612.3 Kcal"` 형태로 주므로 **파싱 실패분이 있을 수 있다.** 먼저 `select calories from meals where calories !~ '^[0-9.]+'`로 세고, 0건이면 `alter ... using` 캐스트. 아니면 새 컬럼 `calories_kcal numeric` 추가 후 이행 |
| 2 | 🔴 `schools`의 UNIQUE가 사실상 작동하지 않음 | `0001:23-27` — `neis_office_code`/`neis_school_code` 둘 다 nullable인데 `unique(둘)`. **Postgres 기본 `NULLS DISTINCT`이므로 코드 없는 학교는 무한 중복 가능** | 두 컬럼에 `NOT NULL` 부여. 단 `0016:12-13`이 이미 «자녀가 붙은 학교는 NEIS 코드가 채워져 있다»를 강제했으므로 **자녀 없는 학교에만 결측이 있을 수 있다** — 먼저 센다. 결측이 0건이면 `set not null`, 있으면 그 학교를 지우거나 보충 |
| 3 | `children.school_id` nullable vs 불변식 불일치 | `0001:33` nullable. 그런데 `0016:1-21`이 «school_id 없는 자녀 0건»을 강제한 뒤 `0016:26-30`이 FK를 `ON DELETE RESTRICT`로 바꿨다 | `set not null`. 이 변경 후 `children_user_school_id_idx`(`0003:13-15`)의 `WHERE school_id IS NOT NULL` 조건이 항상 참이 되므로 **부분 인덱스를 전체 인덱스로 재생성**(D2 2번과 통합) |
| 4 | `school_events.event_kinds jsonb` vs `children.dietary_restrictions text[] + CHECK` — **같은 저장소, 5일 차이, 정반대 해법** | `0028`(2026-06-09) `event_kinds jsonb default '["event"]'`, **값 도메인 CHECK 없음** / `0034`(2026-06-14) `dietary_restrictions text[] not null` + `children_dietary_restrictions_array_check`(`0034:12-23`) | **`0034`가 옳다.** `event_kinds`를 `text[] + CHECK (event_kinds <@ array['event','deadline'])`로 전환. 값은 `'["event"]'` / `'["deadline"]'` 두 가지뿐(`0028:5-9`)이라 이행이 간단하다 |
| 5 | `school_events` UNIQUE가 `end_date`를 안 본다 | `0017:12` `unique(notice_id, event_date)`. `0029:25-27`이 같은 이름으로 재확인. 그런데 `0030_school_events_end_date.sql`이 기간 개념을 도입 | 같은 공지에 «같은 시작일, 다른 종료일»인 두 이벤트가 **저장 불가능**하다. 실제로 그런 케이스가 있는지 **미확인** — 실측 후 판단. 있으면 `unique(notice_id, event_date, end_date)`로 확장 |
| 6 | `meals`가 `schools`와 FK 없음 | `0001:80-93` — `office_code`/`school_code` **text**로만 키. 다른 테이블은 전부 `school_id uuid` | 설계: `meals.school_id uuid references schools(id)` 추가 + NEIS 코드로 백필. ⚠️ **이번 사업에서 실행하지 않는다** — `meals`는 학교와 1:N이 아니라 «NEIS 코드 단위 전역 공유 캐시»로 설계되어 있고(`0032:4` 주석이 그 패턴을 명시), FK를 붙이면 캐시 공유 모델이 깨진다. 열린 질문 3 |

---

## 14. D11 — 경쟁 상태 (⚠️ 포함 여부 미결)

### 14.1 검증 결과 — 3건이 아니라 2건이다

`refactor.md` §3이 지목한 «신뢰도 높음» 3건을 현재 코드로 검증했다.

| refactor.md 주장 | 검증 결과 |
|---|---|
| ① `translate_sources_for_locale()` lost update | ⚠️ **부분 성립.** 락 **안에서 re-read**(`content_extraction_service.py:980`)하므로 **동일 프로세스 내에서는 안전하다.** 그러나 락이 프로세스 내 `asyncio.Lock`이라 **프로세스 간에는 여전히 취약** |
| ② `notice_cards.content` locale merge lost update | ❌ **불성립 — `0026`으로 이미 해소됨.** locale별 콘텐츠는 `notice_card_translations` **행**으로 분리되었고(`notice_service.py:1110-1121`, `on_conflict="notice_card_id,target_language"`), `notice_cards.content`는 `{"ko": {...}}` 하나만 담으며(`notice_service.py:1721-1727`) `target_language == "ko"`일 때만 갱신된다(`:820-825`). **jsonb 병합이 없다** |
| ③ 프론트 lazy 번역 ↔ 백엔드 auto 번역 겹침 | ✅ **성립, 그러나 완화되어 있음.** §14.3 |

> **브리핑 교정: ②는 이미 고쳐졌다.** 그리고 그 해법이 바로 «언어별 행 분리»다 —
> 즉 **이 저장소는 이미 올바른 패턴을 한 번 적용한 적이 있다.** ①에 같은 해법을 쓰면 된다.

### 14.2 ① 의 정확한 지형

| 항목 | 위치 |
|---|---|
| 함수 | `backend/app/services/content_extraction_service.py:917-1007` |
| 1차 READ (락 밖) | `:928` |
| 락 정의 | `:29` `_SOURCE_TRANSLATION_LOCKS: dict[str, asyncio.Lock] = {}` — **모듈 전역 dict** |
| 락 획득 | `:978-979` |
| 2차 READ (락 안) | `:980` |
| 통째 UPDATE (락 안) | `:1003` `sb.table("notices").update({"extracted_content": latest_extracted})` |
| 통째 UPDATE (락 **밖**) | `:1006-1007` — `:979-1004` 블록이 항상 `return`하므로 **도달 불가 데드코드** |

**락이 무력해지는 조건**: `translate_sources_for_locale()`가 **서로 다른 3종 프로세스**에서 호출된다.

| # | 진입점 | 위치 |
|---|---|---|
| 1 | translation worker Job | `backend/app/jobs/translation_worker.py:53` |
| 2 | crawler worker Job → ContentExtractionService | `backend/app/jobs/crawler_worker.py:9` → `content_extraction_service.py:373` |
| 3 | scheduled content extractor Job | `backend/app/jobs/scheduled_content_extractor.py:9` → 동일 |
| 4 | API 인라인 (`background=false`일 때만) | `backend/app/api/notices.py:184-190` |

그리고 API Service(`naranhi-api`)는 `--max-instances` 미지정이라
**Cloud Run 기본 100 인스턴스까지 오토스케일**한다(`.github/workflows/deploy-api-cloud-run.yml:71-99`).
worker Job들은 `--parallelism`/`--tasks` 미지정이라 실행당 task는 1개지만,
`worker_trigger.py:57-108`의 `run.jobs.run` 호출이 **동일 Job의 execution을 동시에 여러 개 띄우는 것을
막지 않는다** (디바운스가 `worker_trigger.py:30-31, 45-54`의 **인메모리**라 API 인스턴스마다 독립).

게다가 translation worker는 배치 10개를 `asyncio.gather`로 동시 처리한다
(`translation_worker.py:111-113`, 워크플로 args `--batch-size,10`).

**판정: 경쟁 상태는 실재한다. 신뢰도 높음.**

### 14.3 ③ 의 지형 — 완화되어 있다

`refactor.md` §4가 «프론트 kickoff를 기본 경로로 쓰지 않는다»고 적었으나, **코드는 살아 있다.**

| 트리거 | 위치 |
|---|---|
| 홈 | `app/(app)/page.tsx:462-465` |
| **캘린더** (refactor.md 미언급) | `app/(app)/calendar/page.tsx:252` |
| 상세 | `app/(app)/notices/[id]/page.tsx:321-326` |
| 실제 fetch | `lib/notice-translation-batch.ts:37-42` → `POST /api/notices/{id}/process` |
| 캐시 체크(락 아님) | `app/api/notices/[noticeId]/process/route.ts:37-56` |

그러나 완화 장치가 두 겹 있다:

| 장치 | 위치 |
|---|---|
| `background: true` → 항상 job queue 경유 | `process/route.ts:68-73` |
| 쿨다운 — 같은 job_key가 최근 완료됐으면 재등록 안 함 | `backend/app/api/notices.py:124-127` → `job_queue_service.py:101-117` |
| **job_key 유니크 부분 인덱스** — `app_jobs_active_job_key_idx WHERE status IN ('queued','processing')` | `0027:22-24`, 사용처 `job_queue_service.py:55-56, 83-84` |

즉 «동시에 두 번역이 실행»되는 것은 **DB 유니크 인덱스가 막고 있다.**
(단 `enqueue`/`claim`의 원자성 세부는 **미확인**.)

**따라서 ③은 «중복 실행» 문제가 아니라 «죽었다고 문서에 적힌 경로가 살아 있다»는
문서-코드 불일치 문제다.** 조치는 코드 삭제가 아니라 `refactor.md` 갱신, 또는
kickoff 3곳 제거 중 하나다.

### 14.4 설계 — ①을 어떻게 고칠 것인가

세 가지 안. **`0026`의 선례(언어별 행 분리)가 있다는 점이 판단에 중요하다.**

| 안 | 방법 | 장점 | 단점 |
|---|---|---|---|
| **A. 언어별 행 분리** | `extracted_content.sources[].translations[locale]`을 새 테이블 `notice_source_translations(notice_id, source_index, target_language, translated_text)`로 옮긴다 | ⭐ **`0026`이 이미 검증한 패턴.** 경쟁 상태가 구조적으로 사라짐. RLS 경계도 깔끔 | 읽기 경로 변경 필요 — `lib/notices.ts:316-323`, `:241-251`. 마이그레이션 + 백필 |
| **B. DB 함수로 원자적 병합** | `jsonb_set`을 쓰는 `security definer` 함수를 만들어 «읽고-고치고-쓰기»를 한 문장으로 | 스키마 변경 없음. 읽기 경로 무변경 | jsonb 경로 조작이 SQL에 박힘. `0007`의 `claim_notice_extractions`가 같은 패턴이라 전례는 있음 |
| **C. 낙관적 잠금** | `notices`에 `extracted_content_version int` 추가, `update ... where version = :read_version` → 0행이면 재시도 | 최소 변경 | 재시도 루프를 코드에 넣어야 함. 8언어면 경합 시 재시도가 잦아짐 |

**권고: A.** 이유는 세 가지 —
① 저장소에 이미 같은 해법(`0026`)이 있어 일관성이 생긴다
② 경쟁 상태를 «줄이는» 게 아니라 «없앤다»
③ §15의 «번역 4중 저장»에서 canonical을 정하는 문제와 **같은 작업으로 합쳐진다**.

### 14.5 왜 열린 질문인가

이건 DB 정리가 아니라 **번역 파이프라인 변경**이다.
`translate_sources_for_locale()`은 사업 C(추출 수리)의 사정권 안에 있고,
사업 C가 이 함수를 손대는 계획이라면 **두 사업이 같은 파일을 동시에 고치게 된다.**

**사용자에게 «DB 정리에 포함할지» 물었을 때 답을 못 받았다. §19 Q1로 남긴다.**

---

## 15. D12 — 중복 저장 정리 (⚠️ 포함 여부 미결)

> **전제: 사용자 결정에 따라 「삭제」는 하지 않는다.** 과제는 **canonical을 정의하는 것**이다.
> 「무엇을 지울까」가 아니라 「무엇이 정본이고, 나머지는 무엇으로 부를까」를 정한다.

### 15.1 번역이 네 곳에 있다

| # | 저장소 | 쓰기 | 읽기 (렌더) |
|---|---|---|---|
| 1 | `notice_ai_translations.translated_text` | `notice_service.py:808` → `:811-815` upsert | `lib/notices.ts:123-130` → `:164` `translatedBodyText` → `:318` **본문 카드 본문** |
| 2 | `notices.extracted_content.sources[].translations[locale]` | `content_extraction_service.py:999` → `:1003` | `lib/notices.ts:316-323` — **첨부 카드 본문만**. 본문 카드는 #1이 먼저 잡는다(`:318`의 `isBody && translatedBodyText` 분기) |
| 3 | `notices.extracted_content.summary.translations[locale]` | `content_extraction_service.py:991` → `:1003` | `lib/notices.ts:357-367` → `:194` → 상세 요약 카드 `app/(app)/notices/[id]/page.tsx:263-269` |
| 4 | `notice_card_translations.translated_content` | `notice_service.py:1110-1121` upsert | `lib/notices.ts:145-151` → `:165-184` → `app/(app)/notices/[id]/page.tsx:273` |

**중복의 실체는 #1 ↔ #2다.** 같은 한국어 본문을 두 번 번역해 두 곳에 저장한다:

- `translate_notice()`가 `notices.original_text` **전체**를 번역해 #1에 넣는다
- `translate_sources_for_locale()`가 `sources[].refined_text` **각각**을 다시 번역해 #2에 넣는다
- 그런데 `original_text`는 `refined_text`들의 concat이다(§15.2)

렌더 시 본문 카드는 #1을, 첨부 카드는 #2를 쓴다. 즉
**#2의 «본문 source 분»은 저장되지만 읽히지 않는다.**
다만 지울 수 없다 — `hasCompleteTranslatedSources()`(`lib/notices.ts:241-251`)와
`process/route.ts:173-183`이 **그 존재 여부를 «번역 완료» 판정에 쓰고 있기 때문**이다.

#3(summary)과 #4(cards)는 소비자가 다르므로 중복이 아니다. 파생물이다.

### 15.2 원문이 두 곳에 있다

| 저장소 | 쓰기 |
|---|---|
| `notices.original_text` | `content_extraction_service.py:786-790` → `:792-800` |
| `notices.extracted_content.sources[].refined_text` | 같은 UPDATE 문 안에서 함께 저장 |

**확인: 전자는 후자의 concat이 맞다.** `_full_body_text()`(`content_extraction_service.py:667-684`)가
본문 carrier의 `refined_text` + 각 첨부의 `refined_text`를
`"## 첨부: {파일명}\n\n{text}"` 헤더로 구분해 `\n\n`으로 이어붙인다.
fallback 체인은 `_full_body_text()` → `primary["refined_text"]` → `result.raw_text`(`:786-790`).

### 15.3 추출된 사실이 네 곳에 있다

| # | 저장소 | 쓰기 | 읽기 |
|---|---|---|---|
| 1 | `notices.source_hard_facts` | `notice_service.py:836` → `:843` (`ko`일 때만) | **백엔드만** — `notice_service.py:1232-1245` `_notice_has_canonical_artifacts()`. 프론트 렌더 0건 |
| 2 | `notices.due_date` / `event_dates` / `event_location` | `notice_service.py:833-835` → `:843` | 홈 D-day는 `due_date`만(`app/(app)/page.tsx:269, 331-333`). 백필 입력 `lib/schedule-backfill.ts:21, 69-70, 89`. **`event_dates`/`event_location`을 직접 렌더하는 프론트 경로 0건** |
| 3 | `school_events` 행 | 백엔드 `notice_service.py:1166-1184` upsert + `:1186-1191` 정리 / **프론트도 독립적으로** `lib/schedule-backfill.ts:98-101` | 캘린더 `app/(app)/calendar/page.tsx:118-124`, 홈 D-day fallback `app/(app)/page.tsx:335-343, 391-395` |
| 4 | `notice_cards` schedule 카드 | ❌ **현재 코드는 만들지 않는다** — `_build_notice_cards()`(`notice_service.py:1638-1664`)는 `action` 카드만 | 그럼에도 읽는 쪽이 살아 있다 — `lib/schedule-backfill.ts:49-53, 152-183` |

**동기화 장치가 없다.** 그 증거가 재구축 스크립트 3개다:

| 스크립트 | 하는 일 |
|---|---|
| `lib/schedule-backfill.ts` | `notices` + `notice_cards`에서 `school_events`를 재생성 |
| `scripts/rebuild_school_events.py` | `notices.source_hard_facts`를 백엔드 함수에 다시 넣어 `school_events` 재계산 |
| `scripts/sweep_footer_dates.py` | `school_events`에서 «게시일/푸터 날짜»인 행을 찾아 삭제 |

### 15.4 canonical 정의 (제안)

| 도메인 | canonical | 나머지의 지위 | 근거 |
|---|---|---|---|
| **공지 원문** | `extracted_content.sources[].refined_text` | `notices.original_text`는 **파생 캐시** — 재계산 가능(`_full_body_text()`) | concat의 방향이 sources → original_text |
| **본문 번역** | `notice_ai_translations.translated_text` | `sources[].translations[locale]`의 «본문분»은 **파생 캐시**. 첨부분은 canonical | 본문 렌더가 실제로 #1을 쓴다(`lib/notices.ts:318`) |
| **카드 번역** | `notice_card_translations.translated_content` | 유일본 | `0026`이 이미 정리 |
| **요약 번역** | `extracted_content.summary.translations[locale]` | 유일본 | 소비자 하나 |
| **추출된 사실** | `notices.source_hard_facts` | `due_date`/`event_dates`/`event_location`은 **파생 인덱스**, `school_events`는 **파생 뷰** | `rebuild_school_events.py`가 실제로 이 방향으로 재계산한다 |

**이 정의가 주는 것**: 「어긋났을 때 어느 쪽을 믿을지」가 정해진다.
그러면 `rebuild_school_events.py`가 일회성 스크립트가 아니라
**정본에서 파생물을 재생성하는 공식 절차**가 된다.

### 15.5 이번 사업에서 할 일 / 안 할 일

| 할 일 | 안 할 일 |
|---|---|
| 위 표를 코드 주석과 `docs/supabase/`에 명문화 | 어떤 저장소도 **삭제하지 않는다** (사용자 결정) |
| `lib/notices.ts:241-251`의 «완료 판정»이 파생 캐시(#2)를 보는 것을 canonical(#1)을 보도록 바꿀지 검토 | 번역 파이프라인 재작성 |
| §14.4 A안을 택하면 #2가 자연히 테이블로 이동 → 두 작업 통합 | |

**§14와 마찬가지로 착수 승인은 §19 Q1에 묶는다.**

---

## 16. 배포 순서

원칙은 `schema-migration-plan.md:516-522`를 그대로 따른다 —
**코드 선배포 → 백필 → 읽기 전환 → 삭제. destructive는 항상 마지막.**

| 배포 | 단위 | 내용 | 성격 | 확인 |
|---|---|---|---|---|
| **0** | — | **사업 A 완료** (이력 정합 + `db push` + `TEST_ENTRY_BYPASS` 제거) | 선행 | `db diff` 깨끗 |
| **1** | D1 | `gen:types` 스크립트 + `database.generated.ts` 최초 생성 | 도구 | `npm run typecheck` 통과 |
| **2** | D2 | 인덱스 6개 | additive | `explain`으로 인덱스 사용 확인 |
| **3** | D3 | 트리거 2 + 중복 정책 drop + 유령 버킷 delete | 저위험 | 정책 수 감소, 버킷 사라짐 |
| **4** | D4 | `scripts/seed-arabic-demo-account.cjs` 삭제 | 코드만 | — |
| **5** | D5-a | 데모 시드 코드 제거 (`lib/demo-school.ts` 등) | 코드만 | 새 데모 데이터 미생성 |
| **6** | D5-b | 데모 데이터 삭제 마이그레이션 | 🔴 파괴적 | §11.3 순서대로, 건수 로그 |
| **7** | D6-a | `school_crawler_service.py` 이중 쓰기 제거 + `select("*")` 좁히기 | 코드만 | **크롤 1회 성공** |
| **8** | D6-b | `schools.crawl_*` 6컬럼 + 인덱스 2개 drop | 🔴 파괴적 | 크롤 재확인 |
| **9** | D7-a | `profiles.email`/`display_name` 쓰기 제거 | 코드만 | 온보딩 정상 |
| **10** | D7-b | `profiles` 3컬럼 drop | 🔴 파괴적 | 로그인 → 온보딩 → 홈 |
| **11** | D8 | `school_events.source_language` drop + `validation_status` CHECK 축소 | 🔴 파괴적 | 캘린더·번역 정상 |
| **12** | D9 | `meals.calories`, `schools` NOT NULL, `children.school_id` NOT NULL, `event_kinds` | 🔴 파괴적 | 사전 카운트가 전부 0일 때만 |
| **13** | D10 | `getSchoolSummary` 소유권 검증 (범위 미정) | 코드만 | 남의 학교 상태 조회 실패 |
| **14** | D1 CI | 드리프트 검사를 `main`에서 차단 모드로 전환 | 도구 | 일부러 어긋내면 CI 실패 |
| **—** | D11·D12 | **미결** — §19 Q1 | | |

### 순서의 이유

- **1번이 맨 앞인 이유**: 이후 모든 컬럼 삭제가 타입 재생성을 요구한다. 손으로 고치면 또 어긋난다.
- **4·5번이 6번보다 앞인 이유**: 시드 코드가 살아 있는데 데이터를 지우면 다음 렌더가 다시 뿌린다.
- **4번이 7번보다 앞인 이유**: `seed-arabic-demo-account.cjs:275-288`이 `schools.crawl_*`의
  마지막 쓰기다. 이걸 먼저 없애야 D6가 «쓰는 곳 0건»이 된다.
- **7번과 8번을 나누는 이유**: 코드만 되돌리면 즉시 원복 가능한 구간을 만들기 위해.
  7번 배포 후 **실제 크롤을 1회 돌려** `school_crawl_state`만으로 되는지 확인한 뒤 8번으로 간다.
- **12번이 뒤인 이유**: 사전 카운트 쿼리가 전부 0을 낼 때만 실행 가능하다.
  하나라도 0이 아니면 그 항목은 이번 사업에서 빠지고 별건이 된다.

---

## 17. 결정 기록

| # | 질문 | 결정 | 반영 |
|---|---|---|---|
| 1 | 번역 이력·감사 payload를 마저 제거할 것인가 (기존 Phase 6) | ❌ **하지 않는다.** "과거 번역 정보 필요할 수도 있으니까 이 부분은 남겼으면 좋겠다" → **명시적 비목표.** `notice_ai_translations`의 남은 10컬럼을 하나도 지우지 않는다. §15도 «삭제»가 아니라 «canonical 정의»로만 다룬다 | §2 비목표, §13.1-2, §15 |
| 2 | 데모 데이터를 어떻게 할 것인가 | ✅ **운영 DB에서 분리(삭제)한다.** "데모는 끝났어" | §11 (D5) |
| 3 | 왜 지금인가 | **데이터가 38건뿐인 지금이 가장 싸고 안전한 시점.** 성능이 아니라 «나중에 못 고치게 되기 전에»가 근거 | §1.2 |

### 사업 A에서 넘어온 전제

| 사업 A 결정 | 사업 D에 미치는 영향 |
|---|---|
| A2 — `lib/test-entry-bypass.ts` 제거 | 데모 진입점이 사라져 D5가 «이미 들어간 것만» 치우면 된다 |
| A2 — `TEST_ENTRY_BYPASS` env 제거 | service_role 조건부 우회 8곳이 자동 소멸 (§12.1) |
| A3 — 데모 학교를 스코프 예외로 두지 않음 | D5의 방향과 일치 |
| A4 — `db push` 자동화 | D의 마이그레이션 7~9개를 손으로 넣지 않아도 된다 |

---

## 18. 검증

| # | 항목 | 방법 | 통과 기준 |
|---|---|---|---|
| 1 | D1 최초 생성 | `npm run gen:types && npm run typecheck` | 통과. `database.generated.ts`에 `app_jobs` · `board_watermarks` 존재 |
| 2 | D1 드리프트 검사 | 일부러 타입 한 줄을 고치고 CI 실행 | 실패 + 안내 메시지 |
| 3 | D2 인덱스 | `explain (analyze) select ... from notice_cards where notice_id = ?` | `Index Scan` (Seq Scan 아님) |
| 4 | D3 트리거 | `app_jobs` 한 행을 update | `updated_at`이 바뀜 |
| 5 | D3 정책 | `select count(*) from pg_policies where tablename='notice_cards'` | **2 → 1** |
| 6 | D3 버킷 | `select count(*) from storage.buckets where id='notice-originals'` | 0 |
| 7 | D5 사전 | 데모 학교에 붙은 `children` 건수 | **0이어야 진행.** 0이 아니면 중단하고 사용자에게 보고 |
| 8 | D5 사후 | `select count(*) from notices n join schools s on s.id=n.school_id where s.neis_office_code='DEMO'` | 0 |
| 9 | D5 회귀 | 로그인 → 홈 → 캘린더 → 급식 | 데모 학교가 검색·화면 어디에도 안 나옴 |
| 10 | D6-a | 실제 학교 1개 크롤 트리거 → `school_crawl_state` 확인 | `crawl_status`·`crawl_last_checked_at` 갱신 |
| 11 | D6-a | 같은 학교의 `schools.crawl_status` 확인 | **갱신되지 않음** (이중 쓰기 끊김 증명) |
| 12 | D6-a | `homepage_url`이 없는 학교로 크롤 | `.update({})` 에러 없음 (`if school_payload:` 가드) |
| 13 | D6-b | `select column_name from information_schema.columns where table_name='schools'` | crawl_* 6개 없음, `homepage_url` **있음** |
| 14 | D6-b 회귀 | 온보딩에서 새 학교 등록 → 최초 크롤 | 정상 |
| 15 | D7-a | 온보딩 완주 | `profiles` 행 생성, `locale`·`native_language` 기록 |
| 16 | D7-b | 로그인 → 온보딩 → 홈 → 공지 상세 | 전 화면 정상 |
| 17 | D8-2 사전 | `select count(*) from notice_ai_translations where validation_status='human_review_required'` | 0이면 그대로 진행, 아니면 사용자에게 문의 |
| 18 | D8-3 사전 | `select count(*) from notice_cards where type='schedule'` | 실측 후 §13.1-3 판단 |
| 19 | D9-1 사전 | `select count(*) from meals where calories !~ '^[0-9.]+$' and calories is not null` | 0이면 캐스트, 아니면 새 컬럼 안 |
| 20 | D9-2 사전 | `select count(*) from schools where neis_office_code is null or neis_school_code is null` | 0이면 `set not null` |
| 21 | D9-3 사전 | `select count(*) from children where school_id is null` | 0이면 `set not null` |
| 22 | D9-5 사전 | `select count(*) from school_events where end_date is not null` | 실측 후 §13.2-5 판단 |
| 23 | D10 | 다른 사용자의 `schoolId`로 홈 렌더 시도 | 크롤 상태가 노출되지 않음 |
| 24 | 전체 회귀 | `npm run lint && npm run typecheck && npm run build` + `python -m unittest discover backend/tests` | 통과 |

---

## 19. 위험과 롤백

| 위험 | 영향 | 완화 |
|---|---|---|
| 🔴 **사업 A의 이력 정합 전에 마이그레이션을 만든다** | `db push` 첫 실행이 과거 파괴적 구문을 재실행 (`0018:1` `drop table schedules` 등) | **사업 A 완료가 배포 0번.** `db diff`가 깨끗할 때만 착수 |
| 🔴 **데모 학교에 실제 사용자의 자녀가 붙어 있다** | `0016:26-30`의 `ON DELETE RESTRICT`로 삭제 실패, 또는 강제 시 사용자 계정 파손 | 검증 7번 — **0이 아니면 중단하고 사용자에게 보고.** 자동 판단하지 않는다 |
| 🟠 **D6-b 후 크롤이 깨진다** | 학교 크롤 전면 정지 | D6-a·D6-b를 **다른 배포로 분리**하고 사이에 실제 크롤 1회 확인(검증 10·11). 되돌리기는 `school_crawl_state`에서 역백필 |
| 🟠 **`homepage_url`을 실수로 함께 지운다** | 크롤러가 대상 URL을 잃음 (`school_crawler_service.py:360`이 유일 경로), `homepage_missing` 실패 | 마이그레이션에 `homepage_url`을 **적지 않는다.** 검증 13번이 존재를 확인 |
| 🟠 **`profiles.email` 삭제 후 운영 문의 대응이 막힌다** | 사용자 식별이 `auth.users` 조회로만 가능 | 삭제 전 `auth.users`에서 조회 가능함을 실증. 사용자가 «남겨라» 하면 `avatar_url`만 지움 (§9.3) |
| 🟡 **D1 CI 드리프트 검사가 PR을 상시 실패시킨다** | 개발 흐름 정지 | PR은 경고(continue-on-error), `main`에서만 차단. 배포 14번에서 전환 (§5.3) |
| 🟡 **D9의 `set not null`이 실패한다** | 마이그레이션 롤백 | 전부 **사전 카운트 쿼리로 0 확인 후에만** 실행(검증 19~21). 0이 아니면 그 항목만 별건으로 분리 |
| 🟡 `notice_cards`에 `type='schedule'` 옛 행이 남아 있다 | §13.1-3의 «데드 코드» 판단이 틀림 | 검증 18번으로 실측. **미확인 상태로 삭제하지 않는다** |
| 🟢 D2 인덱스가 계획을 악화시킨다 | 이론적. 38행에서는 무의미 | `drop index` 한 줄 |

각 배포는 단독 롤백이 가능하다.
D1은 스크립트·CI 잡 삭제, D2는 `drop index`, D3는 역 SQL,
D4·D5-a·D6-a·D7-a·D10은 `git revert`,
D5-b·D6-b·D7-b·D8·D9는 **복구 마이그레이션이 필요**하다(값 복구 경로는 각 절에 기록).

---

## 20. 열린 질문

| # | 질문 | 왜 답이 필요한가 | 기본안 |
|---|---|---|---|
| **Q1** | **경쟁 상태(§14)와 중복 저장 canonical(§15)을 이 사업에 포함할 것인가?** | 둘 다 DB 정리가 아니라 **번역 파이프라인 변경**이고, `translate_sources_for_locale()`은 사업 C의 사정권 안이다. 포함하면 두 사업이 같은 파일을 동시에 고친다 | **미포함.** 설계만 남기고 사업 C에 인계 |
| **Q2** | **service_role RLS 우회 정리(§12)의 범위는?** ① 전부(`unstable_cache` 포기) ② 계약 강화만 ③ `getSchoolSummary` 하나만 | ①은 홈·캘린더·급식 렌더 아키텍처 변경이라 사업 D의 성격과 다르다. 성능(캐시 TTL 15~30초)을 포기할지가 핵심 | **③.** 소유권 검증이 아예 없는 유일한 곳만 |
| **Q3** | **`meals`에 `school_id` FK를 붙일 것인가?**(§13.2-6) | `meals`는 «NEIS 코드 단위 전역 공유 캐시»로 설계돼 있다(`0032:4`가 그 패턴을 명시). FK를 붙이면 캐시 공유 모델이 깨진다 | **붙이지 않는다.** 현 설계가 의도된 것으로 본다 |
| **Q4** | **`profiles.native_language`를 사용자가 바꿀 수 있어야 하는가?**(§9.2) | 지금은 온보딩 1회 고정이고 설정 화면에 항목이 없다. 이게 의도인지 미완성인지 **미확인** | **현행 유지 + 주석으로 의도 명시** |
| **Q5** | `profiles.email` / `display_name`을 정말 지워도 되는가 (운영 문의 대응 스냅샷) | `schema-migration-plan.md:188-196`도 같은 질문을 남겼다. `auth.users`에서 조회 가능하지만 service_role이 필요하다 | **지운다.** «남겨라»면 `avatar_url`만 |
| **Q6** | `docs/supabase/schema.md`(2026-05-20 stale)를 다시 쓸 것인가 삭제할 것인가 | D1이 generated 타입을 정본으로 만들면 이 문서의 역할이 애매해진다 | **다시 쓴다.** 테이블 목록 + RLS 요약만 남기고 컬럼 목록은 generated에 위임 |

---

## 21. 준비물

사업 A의 [2026-08-26-prerequisites.md](./2026-08-26-prerequisites.md)를 그대로 쓴다.
**이 사업이 추가로 요구하는 것은 없다.**

| 필요한 것 | 출처 | 상태 |
|---|---|---|
| `supabase` CLI 로그인 | 사업 A §1-2 (prerequisites) | 사업 A에서 해결 |
| GitHub Secret `SUPABASE_ACCESS_TOKEN` | 사업 A §2-1 | 사업 A에서 등록 |
| GitHub Variable `SUPABASE_PROJECT_REF` | 사업 A §2-1 | 동일 |
| 운영 DB 읽기 권한 (사전 카운트 쿼리용) | service_role 키 | 이미 있음 |

D1의 CI 드리프트 검사는 위 셋을 **재사용**한다. 새 시크릿 발급 없음.

---

## 22. 다음 단계

1. **§19 Q1·Q2에 답을 받는다.** 나머지는 기본안으로 진행 가능.
2. **사업 A 완료를 확인한다** — `db diff`가 깨끗하고 `db push`가 `main`에서 돈다.
3. 이 스펙 승인 후 `superpowers:writing-plans`로 구현 계획을 작성한다.
   구현은 서브에이전트로 분담하되 **배포 순서(§16)의 경계를 넘지 않는다.**
   특히 `-a`/`-b`로 나뉜 단위(D5·D6·D7)를 **한 PR에 합치지 않는다.**
4. 완료 후 `schema-migration-plan.md`에 Phase 3·4 완료를 기록하고,
   Phase 6은 «사용자 결정으로 중단»으로 명시해 문서를 닫는다.
