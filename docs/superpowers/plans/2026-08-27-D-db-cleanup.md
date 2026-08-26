# DB 정리 · 기존 스키마 계획 완주 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `schema-migration-plan.md`가 6월에 멈춰 세운 Phase 3·4를 끝내고, 손으로 관리되던 `types/database.ts`를 CI가 지키는 생성물로 바꾸고, 운영 테이블에 섞인 데모 데이터를 문자열이 아니라 FK 로 걷어내고, 실제로 도는 쿼리에 인덱스를 깔고, 「있는데 안 도는 것」을 없앤다.

**Architecture:** 되돌리기 쉬운 것부터 앞에 둔다. ① 타입 생성 파이프라인을 먼저 깔아 이후 모든 컬럼 삭제가 자동으로 타입에 반영되게 하고 ② additive 한 인덱스·트리거·정책 위생을 얹고 ③ 데모 코드를 죽인 뒤 데모 데이터를 지우고 ④ `schools.crawl_*` 와 `profiles` 죽은 컬럼을 각각 「코드 선배포 → 확인 → 컬럼 삭제」 2배포로 떼어내고 ⑤ 죽은 컬럼·느슨한 타입을 조인다. 파괴적 변경은 전부 뒤쪽이고, 각 Task 는 단독 롤백이 가능하다.

**Tech Stack:** Next.js 15 App Router, `@supabase/ssr`, Supabase(Postgres + Storage, 도쿄 리전), Python 3.12 FastAPI, `supabase-py`, GitHub Actions, Supabase CLI

**Spec:** [docs/superpowers/specs/2026-08-27-D-db-cleanup-design.md](../specs/2026-08-27-D-db-cleanup-design.md)

**원류 문서:** [schema-migration-plan.md](../../../schema-migration-plan.md) (Phase 3·4), [refactor.md](../../../refactor.md) (§3 경쟁 상태)

## Global Constraints

- **선행 조건 — 사업 A 완료가 이 계획의 배포 0번이다.** 세 가지를 전제한다.
  - A4 가 원격 마이그레이션 이력을 정합시켰다 (`supabase migration list`의 Local·Remote 열이 전부 일치). **이력이 어긋난 상태에서 `db push` 를 돌리면 `0018:1` `drop table schedules` 같은 과거 파괴적 구문을 재실행한다.**
  - A4 의 `.github/workflows/db-migrate.yml` 이 **머지 시 자동 적용**을 담당한다. **이 계획의 마이그레이션은 전부 그 통로로만 나간다.** 어떤 Task 도 `supabase db push` 를 손으로 돌리지 않는다 (`--dry-run` 확인은 허용).
  - A2 가 `TEST_ENTRY_BYPASS` 와 `lib/test-entry-bypass.ts` 를 제거했다. 이 계획은 그 심볼이 이미 없다고 가정하고 쓴다.
- **마이그레이션 번호**: 이 계획은 **0045 부터** 쓴다. `0035`(자녀 개인일정 예약), `0036`·`0037`(사업 A), `0038`(사업 F), `0039~0044`(사업 E)는 **비워 둔다.** 사업 A 의 `scripts/check_migration_numbers.py` 가 중복을 CI 에서 잡는다. 파일명은 `^\d{4}_[a-z0-9_]+\.sql$` 를 지킨다.
- **프로젝트 ref**: `aoihmzewthgyoxtejfwo` (공개값). **DB 비밀번호는 필요 없다** — CLI 가 액세스 토큰으로 임시 로그인 역할을 만든다. `SUPABASE_DB_PASSWORD` 를 요구하는 단계를 만들지 말 것.
- **열쇠 취급**: 서비스 키·토큰을 명령줄 인자나 URL 쿼리에 넣지 않는다. 값 출력 금지. 사전 카운트 스크립트는 전부 `os.environ` 에서 읽고 `Authorization` 헤더로만 보낸다.
- **번역 이력은 남긴다 (사용자 결정 2026-08-27).** `notice_ai_translations` 의 남은 10 컬럼을 **하나도 지우지 않는다.** 기존 계획의 Phase 6 은 실행하지 않는다. §15(중복 저장)는 「삭제」가 아니라 「canonical 정의」로만 다룬다.
- **데모는 끝났다 (사용자 결정).** 데모 시드 코드와 데모 데이터를 제거한다. 데모를 예외로 두는 분기를 새로 만들지 않는다.
- **파괴적 변경은 4단계로 쪼갠다**: 코드 선배포 → 백필/확인 → 읽기 전환 → 삭제. `-a`/`-b` 로 나뉜 Task 를 **한 PR 에 합치지 않는다.**
- **사전 카운트가 0 이 아니면 그 항목은 이번 사업에서 빠진다.** 자동 판단하지 않고 중단하고 보고한다.
- **테스트 실행**:
  - 백엔드: `PYTHONPATH=backend python -m unittest discover backend/tests`
  - 프론트: `npm run typecheck` + `npm run build` (**프론트 테스트 러너가 없다** — `package.json` 에 test 스크립트 없음)
- **커밋 메시지**: 한국어, `type(scope): 요약` 형식.

---

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `types/database.generated.ts` | `supabase gen types` 산출물. 손으로 고치지 않는다 | 신규 (Task 1) |
| `types/database.ts` | generated 재수출 + 의미 별칭 5개 | **전면 교체** (Task 1) |
| `package.json` | `gen:types` 스크립트 | 수정 (Task 1) |
| `.github/workflows/ci.yml` | 타입 드리프트 경고 | 수정 (Task 2) |
| `.github/workflows/db-migrate.yml` | 적용 후 드리프트 차단 | 수정 (Task 16, 사업 A 가 생성) |
| `supabase/migrations/0045_indexes_for_hot_paths.sql` | 인덱스 6종 | 신규 (Task 3) |
| `supabase/migrations/0046_low_risk_hygiene.sql` | 트리거 2 · 중복 정책 · 유령 버킷 | 신규 (Task 4) |
| `scripts/seed-arabic-demo-account.cjs` | 깨진 데모 시드 | **삭제** (Task 5) |
| `scripts/audit_demo_data.py` | 데모·쇼케이스 실측 + 이관 대상 확인 | 신규 (Task 6) |
| `lib/demo-school.ts` | 데모 시드 (1537줄) | **삭제** (Task 7) |
| `app/(app)/settings/DemoSchoolPicker.tsx` | 데모 학교 선택 UI | **삭제** (Task 7) |
| `app/api/schools/search/route.ts` | 데모 학교 검색 주입 | 수정 (Task 7) |
| `supabase/migrations/0047_remove_demo_school_data.sql` | 자녀 이관 + 데모·쇼케이스 삭제 | 신규 (Task 8) |
| `backend/app/services/school_crawler_service.py` | 크롤 결과 저장 이중 쓰기 | 수정 (Task 9) |
| `backend/tests/test_school_crawler_state_write.py` | `schools` 백필 payload 검증 | 신규 (Task 9) |
| `supabase/migrations/0048_drop_schools_crawl_columns.sql` | `schools.crawl_*` 6컬럼 + 인덱스 2 | 신규 (Task 10) |
| `app/onboarding/actions.ts` | 프로필 upsert | 수정 (Task 7, 11) |
| `app/api/auth/dev-login/route.ts` | 프로필 upsert | 수정 (Task 11) |
| `app/(auth)/login/LoginButtons.tsx` | dev-login 요청 본문 | 수정 (Task 11) |
| `supabase/migrations/0049_drop_profiles_dead_columns.sql` | `profiles` 3컬럼 | 신규 (Task 12) |
| `supabase/migrations/0050_drop_dead_columns_and_narrow_checks.sql` | `school_events.source_language`, `validation_status` CHECK | 신규 (Task 13) |
| `supabase/migrations/0051_tighten_types_and_invariants.sql` | NOT NULL 3개 + `event_kinds` text[] | 신규 (Task 14) |
| `lib/server-cache.ts` | `getSchoolSummary` 소유권 검증 | 수정 (Task 15) |
| `docs/supabase/schema.md` | 스키마 개요 (2026-05-20 stale) | **재작성** (Task 16) |
| `supabase/migrations/0052_notice_source_translations.sql` | 소스 번역 행 분리 | 신규 (**선택 Task A**) |

---

## 배포 순서

```
0   사업 A 완료                                   (선행 — 이력 정합 + db push 자동화 + 우회 제거)
1   Task 1   타입 자동 생성 전환
2   Task 2   드리프트 CI (경고 모드)
3   Task 3   인덱스 6종                (0045)
4   Task 4   저위험 위생               (0046)
5   Task 5   깨진 시드 스크립트 삭제
6   Task 6   데모·쇼케이스 실측 + 이관 대상 확정
7   Task 7   데모 시드 코드 제거
8   Task 8   자녀 이관 + 데모·쇼케이스 삭제 (0047)  🔴
9   Task 9   크롤러 이중 쓰기 제거
10  Task 10  schools.crawl_* 삭제      (0048)   🔴
11  Task 11  profiles 쓰기 경로 정리
12  Task 12  profiles 죽은 컬럼 삭제    (0049)   🔴
13  Task 13  죽은 컬럼·상태 제거        (0050)   🔴
14  Task 14  타입·불변식 교정          (0051)   🔴
15  Task 15  getSchoolSummary 소유권 검증
16  Task 16  드리프트 차단 전환 + 계획 문서 닫기
—   선택 A   경쟁 상태 해소            (0052)   ⏸ 승인 대기
—   선택 B   canonical 정의 명문화              ⏸ 승인 대기
```

### 순서의 이유

- **Task 1 이 맨 앞인 이유**: Task 10·12·13·14 가 전부 컬럼을 지운다. 타입을 손으로 고치면 또 어긋난다.
- **Task 5 가 Task 9·10 보다 앞인 이유**: `scripts/seed-arabic-demo-account.cjs:275-288` 이 TS/JS 에 남은 마지막 `schools.crawl_*` 쓰기다. 이걸 먼저 없애야 Task 10 이 「쓰는 곳 0건」이 된다.
- **Task 7 이 Task 8 보다 앞인 이유**: 시드 코드가 살아 있는데 데이터를 지우면 다음 홈 렌더에서 `ensureDemoSchoolSeed()` 가 다시 뿌린다.
- **Task 7 이 Task 13 보다 앞인 이유**: `lib/demo-school.ts:1157` 이 `school_events.source_language` 를 select 하는 **유일한 TS 경로**다. 파일이 사라져야 Task 13 의 컬럼 삭제가 안전하다.
- **Task 9 / 10 을 나누는 이유**: 코드만 되돌리면 즉시 원복되는 구간을 만든다. Task 9 배포 후 **실제 크롤 1회**를 돌려 `school_crawl_state` 만으로 도는지 본 뒤 Task 10 으로 간다.
- **Task 6 이 Task 8 보다 앞인 이유**: 삭제 앵커 UUID 와 **자녀 이관 대상**을 실행 시점에 다시 확정해야 한다. 아래 §「착수 전 반드시 읽을 것」 참조.

---

## 결정 기록

| # | 질문 | 결정 | 반영 |
|---|---|---|---|
| 1 | 번역 이력·감사 payload 를 마저 제거할 것인가 (기존 Phase 6) | ❌ **하지 않는다** (2026-08-27). "과거 번역 정보 필요할 수도 있으니까 이 부분은 남겼으면 좋겠다" → `notice_ai_translations` 의 남은 10 컬럼을 하나도 지우지 않는다. 중복 저장도 「삭제」가 아니라 「canonical 정의」로만 다룬다 | Global Constraints, Task 13, 선택 Task B |
| 2 | 데모 데이터를 어떻게 할 것인가 | ✅ **운영 DB 에서 제거한다** (2026-08-27). "데모는 끝났어" | Task 5·7·8 |
| 3 | 왜 지금인가 | 데이터가 38건뿐인 지금이 가장 싸고 안전한 시점. 성능이 아니라 「나중에 못 고치게 되기 전에」가 근거 | 계획 전체 |
| **4** | **데모 학교에 붙은 실제 사용자 자녀 2건을 어떻게 할 것인가** | ✅ **「진짜 학교로 옮기고 데모 삭제」** (2026-08-27, 사용자 결정). 자녀 2건의 `school_id` 를 진짜 부천부흥중학교(`J10`/`7581020`, id `8da4b348…`)로 갱신한 뒤 데모 학교를 삭제한다. **자녀 행 자체는 지우지 않는다.** 계정도 온보딩도 보존된다 | **Task 6·8** |
| **5** | **`Naranhi Showcase School` 을 어떻게 할 것인가** | ✅ **함께 삭제한다** (2026-08-27). 자녀 0건이라 막는 것이 없다. 저장소 어디에서도 참조되지 않는 시연용 잔재다 | **Task 6·8** |

---

## 착수 전 반드시 읽을 것 — 운영 DB 실측 (2026-08-27)

계획 작성 중 운영 DB(읽기 전용)를 실측했고, 조정자가 같은 값을 독립적으로 재확인했다. **스펙이 예상하지 못한 사실 넷**이 나왔다.

| # | 실측 | 스펙의 서술 | 영향 |
|---|---|---|---|
| **1** | 데모 학교(`neis_office_code='DEMO'`, `neis_school_code='NARANHI001'`, id `3b33ac1d-0cb9-4199-9568-51431b876e63`)에 **`children` 2행이 붙어 있다.** 서로 다른 사용자 2명 소유(`d27d07a3…` / `884331fc…`), 둘 다 1학년 1반, 생성일 2026-06-10 | §18 검증 7번 「0 이어야 진행」 | `children_school_id_fkey` 가 `ON DELETE RESTRICT`(`0016:26-30`) 라 그냥은 못 지운다. **결정 4 에 따라 이관 후 삭제한다** (Task 8) |
| **2** | 그 데모 학교의 **이름이 `부천부흥중학교`** 로, 진짜 학교와 **글자까지 완전히 같다** (주소 `경기도 부천시`). 진짜 부천부흥중학교는 `J10`/`7581020`, id `8da4b348…` | §11.1 「학교 이름 = `'Naranhi School'`」 | 🔴 **이름으로는 절대 구분할 수 없다.** 앵커는 오직 `(neis_office_code, neis_school_code)` 조합 또는 그것으로 확정한 UUID 여야 한다 (§「이름 매칭 금지」) |
| **3** | 저장소 어디에서도 참조되지 않는 **`Naranhi Showcase School`**(`SHOWCASE`/`NARANHI_SHOWCASE`, id `9bfee999…`)이 있다. 자녀 0, `school_crawl_state` **없음**, 그러나 `notices` 2 · `notice_cards` 2 · `notice_ai_translations` 10 · `school_events` 6 | 언급 없음 | 결정 5 에 따라 Task 6·8 이 **둘째 앵커**로 다룬다 |
| **4** | 8개 학교 중 **`school_crawl_state` 행이 없는 학교가 정확히 1개**(위 SHOWCASE) | §8.3 「상태 행이 없는 학교는 이제 생기지 않는다 … 폴백은 이미 죽어 있다」 | §8.3 은 **한 학교에 대해 거짓**이다. 다만 그 학교를 Task 8 이 지우므로 Task 8 → 9 → 10 순서를 지키면 해소된다 |

### 이관 대상 학교의 상태 — 이관이 안전한 이유

| 항목 | 값 | 의미 |
|---|---|---|
| 진짜 부천부흥중학교 | `J10`/`7581020`, id `8da4b348-e3a2-4d24-884d-f7f55d04c0be` | 앵커는 NEIS 코드 조합으로 확정한다 |
| **`school_crawl_state` 행** | **있다** — `crawl_status='success'`, 게시판 URL `pcbuheung-m.goebc.kr/…bbsId=4717`, 최종 확인 2026-06-14 | ✅ 이관 즉시 크롤이 돈다. **§8.3 의 「상태 행 없는 학교 1개」는 이 학교가 아니라 SHOWCASE 다** |
| 기존 `notices` / `school_events` | **8** / **9** | 이관된 두 계정이 즉시 실제 공지를 받는다 |
| **기존 자녀 수** | **2** (`e2c06359…`, `027607c3…`, 2026-06-12 등록) | ⚠️ **조정자가 「0건」이라고 한 것은 사실과 다르다.** 이관 후 **2 → 4** 가 된다 |
| `children` 의 UNIQUE 제약 | **없다** (`0001` PK 외에 `0016` FK 와 `0034` 배열 CHECK 뿐) | ✅ 같은 학교·학년·반이 겹쳐도 충돌하지 않는다 |
| 이관 대상 사용자의 `notice_hides` | **각 0건** | ✅ 학교가 바뀌어도 어긋날 파생 데이터가 없다 |

> ⚠️ **`notice_hides` 에는 `id` 컬럼이 없다.** PK 가 `(user_id, notice_id)` 복합키다(`0004:1-6`). PostgREST 에 `select=id` 로 물으면 **HTTP 400** 이 난다. 조사 스크립트는 `select=notice_id` 를 쓴다.

### 이름 매칭 금지

실측 #2 가 확정했다 — **데모 학교와 진짜 학교의 이름이 완전히 같다.** 따라서 이 계획 어디에서도 학교 **이름**으로 대상을 고르지 않는다.

| 위치 | 식별 방법 | 이름 사용 |
|---|---|---|
| Task 6 `scripts/audit_demo_data.py` | `(neis_office_code, neis_school_code)` | **출력에만** 쓴다. 필터에 안 쓴다 |
| Task 8 `0047` 앵커 확정 | `(neis_office_code, neis_school_code)` → UUID | 없음 |
| Task 8 `0047` 하위 삭제 | 확정된 UUID 로 FK 추적 | 없음 |
| Task 8 `meals` 삭제 | `(office_code, school_code)` — `schools` 와 FK 가 없어 코드로만 가능 | 없음 |
| Task 7 | `isDemoSchoolSelection()`(이름 매칭 포함) 을 **삭제**한다 | 제거 대상 |

`(neis_office_code, neis_school_code)` 를 앵커로 쓸 수 있는 근거는 그 조합이 `schools_neis_office_code_neis_school_code_key`(`0001:27`) 유니크 제약을 타서 **학교 1개를 확정**하기 때문이다. Task 14 가 이 두 컬럼에 NOT NULL 을 주어 앵커를 더 단단하게 만든다.

### 그 외 사전 카운트 — 전부 스펙의 낙관적 가정과 맞았다

| 사전 카운트 | 실측 | 판정 |
|---|---|---|
| `notice_cards` where `type='schedule'` | **0** / 29 | §13.1-3 데드코드 확정 |
| `notice_ai_translations` where `validation_status='human_review_required'` | **0** / 155 (전부 `passed`) | Task 13 의 CHECK 축소 안전 |
| `schools` where NEIS 코드 null | **0** / 8 | Task 14 `set not null` 안전 |
| `children` where `school_id is null` | **0** / 9 | Task 14 `set not null` 안전 |
| `school_events` 중복 `(notice_id, event_date)` | **0** (end_date 보유 5행 포함) | §13.2-5 유니크 확장 **불필요** — Task 14 에서 제외 |
| `school_events.source_language` 분포 | `ko` **68/68** | §13.1-1 정보량 0 확정 |
| `profiles.avatar_url` / `display_name` non-null | **0/10** / **0/10** | Task 12 무손실 |
| `profiles.email` non-null | **10/10** | `auth.users.email` 이 canonical — Task 11 이 먼저 쓰기를 끊는다 |
| `profiles` 중 `locale ≠ native_language` | **7/10** | §9.2 확정 — `native_language` 를 **지우면 안 된다** |
| `school_events.event_kinds` 분포 | `["event"]` 43 · `["deadline","event"]` **13** · `["deadline"]` 12 | 🔴 **스펙 §13.2-4 의 「두 가지뿐」은 틀렸다.** Task 14 는 2분기 CASE 가 아니라 `jsonb_array_elements_text` 로 일반 변환한다 |
| `meals.calories` 중 숫자가 아닌 값 | **102/102** (전부 `"905.1 Kcal"` 꼴) | 🔴 §13.2-1 의 캐스트 경로 **불가.** Task 14 에서 **제외**하고 후속으로 넘긴다 (§19 위험표의 「0 이 아니면 별건 분리」 규정 적용) |

---

## Task 1: `types/database.ts` 자동 생성 전환

`types/database.ts`(449줄)는 `supabase gen types` 산출물이 아니라 손으로 쓴 파일이고, 이미 4곳이 어긋났다 (`app_jobs` 테이블 통째 누락, `school_crawl_state.board_watermarks` 누락, 지워질 `schools.crawl_*` 잔존, `validation_status` 유니언 불일치).

**Files:**
- Create: `types/database.generated.ts`
- Rewrite: `types/database.ts`
- Modify: `package.json` (scripts)
- Modify: `lib/notices.ts`, `app/(app)/page.tsx` (타입 좁히기 경계)

**Interfaces:**
- Consumes: 사업 A 가 정합시킨 원격 스키마
- Produces: `npm run gen:types`. `@/types/database` 의 export 집합은 **바뀌지 않는다** (`Database`, `Json`, 별칭 5개). import 경로 변경 0건.

- [ ] **Step 1: `gen:types` 스크립트를 넣는다**

`package.json` 의 `scripts` 에 한 줄 추가:

```json
    "gen:types": "supabase gen types typescript --linked --schema public > types/database.generated.ts"
```

> `supabase` CLI 를 devDependency 로 넣지 않는다. 로컬은 이미 로그인·링크된 CLI 를 쓰고, CI 는 사업 A 와 같은 `supabase/setup-cli@v1` 을 쓴다 — 버전 번호를 새로 지어내지 않기 위해서다.

- [ ] **Step 2: 링크 상태를 확인한다 (실패를 먼저 본다)**

```bash
supabase projects list
npm run gen:types
head -c 400 types/database.generated.ts
```

Expected: `aoihmzewthgyoxtejfwo` 가 `●` 로 링크되어 있고, `export type Json =` 로 시작하는 파일이 생성된다. 링크가 안 되어 있으면 `supabase link --project-ref aoihmzewthgyoxtejfwo` 후 재시도.

- [ ] **Step 3: 생성물이 드리프트 4건을 실제로 담았는지 확인한다**

```bash
python - <<'PY'
import re, sys
src = open('types/database.generated.ts', encoding='utf-8').read()
checks = {
    'app_jobs 테이블': 'app_jobs:' in src,
    'board_watermarks 컬럼': 'board_watermarks' in src,
    'schools.crawl_status (아직 존재해야 정상)': 'crawl_status' in src,
    'notice_card_translations': 'notice_card_translations' in src,
    'subject_translations': 'subject_translations' in src,
}
for k, v in checks.items():
    print(('OK  ' if v else 'FAIL') , k)
sys.exit(0 if all(checks.values()) else 1)
PY
```

Expected: 5줄 전부 `OK`. `app_jobs` 나 `board_watermarks` 가 `FAIL` 이면 원격 스키마가 예상과 다르다 — **중단하고 보고할 것.**

- [ ] **Step 4: `types/database.ts` 를 재수출 + 별칭만 남긴 파일로 교체한다**

`types/database.ts` 의 **전체 내용**을 아래로 바꾼다:

```typescript
// 테이블·컬럼 정의의 정본은 types/database.generated.ts 이며, 그 파일은
// `npm run gen:types` 로만 갱신한다 — 손으로 고치지 않는다.
//
// 이 파일에는 gen types 가 만들어 주지 못하는 것만 남긴다. 아래 5개 유니언은
// DB 에 enum 이 없고 text + CHECK 로 표현된 값 도메인이라 gen types 가 string 으로
// 뱉는다. 전 저장소가 '@/types/database' 를 import 하므로 경로는 그대로 둔다.
export type { Json, Database } from './database.generated'

export type SupportedLocale = 'ko' | 'en' | 'zh' | 'vi' | 'ru' | 'ar' | 'fr' | 'id' | 'th'
export type NoticeStatus = 'pending' | 'processing' | 'done' | 'error'
export type CardType = 'supplies' | 'action' | 'schedule'
export type SchoolCrawlBoardKind = 'family_notice' | 'announcement_fallback' | 'unknown'
/** 0005:14-15 의 CHECK 는 세 값이지만 코드가 쓰는 것은 둘뿐이고, 운영 155행이 전부 'passed' 다.
 *  Task 13 이 DB CHECK 를 이 둘로 좁힌다. */
export type NoticeAiValidationStatus = 'passed' | 'failed'
```

- [ ] **Step 5: 타입이 좁혀지지 않는 경계를 찾는다 (실패를 본다)**

```bash
npm run typecheck
```

Expected: **실패한다.** generated 타입에서 `notices.status` · `notice_cards.type` 이 `string` 이라 아래 세 곳이 걸린다.

- `lib/notices.ts:74` — `NoticeDetailDto.status: NoticeStatus` ← `notice.status`
- `lib/notices.ts:96` — `NoticeCardDto.type: CardType` ← `r.type`
- `app/(app)/page.tsx:22, 36` — `status: NoticeStatus`

**출력에 나온 파일·줄을 기록해 둘 것.** Step 6 에서 하나씩 좁힌다.

- [ ] **Step 6: 매핑 경계에서만 좁힌다**

DB 는 `string` 이고 앱은 유니언을 쓴다. **읽어서 DTO 로 옮기는 지점 한 곳에서만** 좁힌다 (컴포넌트 안까지 캐스트를 퍼뜨리지 않는다).

`lib/notices.ts` 의 카드 매핑 (`cardRows` → `cards`):

```typescript
  const cards: NoticeCardDto[] = (cardRows ?? []).map(r => ({
    id: r.id,
    // DB 는 text + CHECK 라 generated 타입이 string 이다. 값 도메인은 0001 의
    // notice_cards_type_check 가 보장하므로 DTO 경계에서 한 번만 좁힌다.
    type: r.type as CardType,
```

`notices` 행을 DTO 로 옮기는 자리에서도 같은 방식으로 `status: notice.status as NoticeStatus` 로 좁힌다. `app/(app)/page.tsx` 도 `row.status as NoticeStatus` 로 동일하게 처리한다.

- [ ] **Step 7: 통과를 확인한다**

```bash
npm run typecheck && npm run build
```

Expected: 둘 다 성공.

- [ ] **Step 8: 커밋**

```bash
git add package.json types/database.ts types/database.generated.ts lib/notices.ts "app/(app)/page.tsx"
git commit -m "chore(types): database 타입을 supabase gen types 산출물로 전환

types/database.ts 는 gen types 산출물이 아니라 손으로 쓴 449줄이었고 이미 네 곳이
어긋나 있었다 — app_jobs 테이블 통째 누락, school_crawl_state.board_watermarks 누락,
정본이 아닌 schools.crawl_* 잔존, validation_status 유니언 불일치.

정의는 database.generated.ts 로 옮기고, gen types 가 만들어 주지 못하는
값 도메인 유니언 5개만 database.ts 에 남겨 재수출한다.
전 저장소가 @/types/database 를 import 하므로 import 경로 변경은 0건이다.

status·type 은 DB 가 text 라 generated 가 string 을 준다. DTO 매핑 경계
세 곳에서만 좁힌다."
```

---

## Task 2: 타입 드리프트 CI 검사 (경고 모드)

**Files:**
- Modify: `.github/workflows/ci.yml` (`validate-web` 잡)

**Interfaces:**
- Consumes: Task 1 의 `gen:types`, 사업 A 가 등록한 `SUPABASE_ACCESS_TOKEN` / `SUPABASE_PROJECT_REF`
- Produces: PR·push 에서 드리프트를 **경고**로 알린다. Task 16 이 차단 모드를 별도 통로에 붙인다. **새 시크릿 발급 없음.**

- [ ] **Step 1: `validate-web` 잡에 스텝 둘을 추가한다**

`.github/workflows/ci.yml` 의 `validate-web` 잡, `Build` 스텝 **뒤에** 붙인다:

```yaml
      - name: Setup Supabase CLI
        uses: supabase/setup-cli@v1
        with:
          version: latest

      # 경고 전용이다. 이 잡은 아직 적용되지 않은 마이그레이션이 있는 PR 에서
      # 반드시 실패하므로 차단하면 개발 흐름이 멈춘다. 적용 직후 시점의
      # 차단 검사는 db-migrate 워크플로가 맡는다(Task 16).
      - name: 타입 드리프트 검사 (경고)
        continue-on-error: true
        env:
          SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}
        run: |
          supabase link --project-ref "${{ vars.SUPABASE_PROJECT_REF }}"
          npm run gen:types
          if ! git diff --exit-code -- types/database.generated.ts; then
            echo "::warning file=types/database.generated.ts::스키마와 타입이 다릅니다. 'npm run gen:types' 를 돌리고 커밋하세요."
            exit 1
          fi
          echo "타입 드리프트 없음"
```

- [ ] **Step 2: 워크플로 문법과 배치를 검사한다**

```bash
python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))
steps = d['jobs']['validate-web']['steps']
names = [s.get('name') or s.get('uses') for s in steps]
print(names)
drift = [s for s in steps if s.get('name') == '타입 드리프트 검사 (경고)'][0]
assert drift['continue-on-error'] is True
assert names.index('Build') < names.index('타입 드리프트 검사 (경고)')
print('OK')
"
```

Expected: 스텝 목록 출력 + `OK`

- [ ] **Step 3: 로컬에서 드리프트가 실제로 잡히는지 확인한다**

```bash
printf '\n// drift probe\n' >> types/database.generated.ts
git diff --exit-code -- types/database.generated.ts; echo "종료코드: $? (1 이면 검출 = 정상)"
git checkout -- types/database.generated.ts
git diff --exit-code -- types/database.generated.ts; echo "종료코드: $? (0 이면 복구 = 정상)"
```

Expected: 첫 종료코드 1, 둘째 0

- [ ] **Step 4: 커밋**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: types/database.generated.ts 드리프트 검사 추가 (경고 모드)

gen:types 를 다시 돌려 커밋된 생성물과 비교한다. 다르면 경고를 남긴다.

지금은 차단하지 않는다 — PR 시점에는 아직 적용되지 않은 마이그레이션 때문에
항상 다르기 때문이다. 적용 직후 시점의 차단 검사는 db-migrate 워크플로가 맡는다.

자격증명은 사업 A 가 등록한 SUPABASE_ACCESS_TOKEN / SUPABASE_PROJECT_REF 를
재사용한다. 추가로 발급할 시크릿이 없다."
```

---

## Task 3: 인덱스 추가

38행짜리 테이블에서는 아무 차이도 안 난다. **지금 넣는 이유는 나중에 넣기가 어렵기 때문이다** — 운영 중 `create index` 는 `concurrently` 가 필요하고 그건 트랜잭션 밖에서 돌아야 해서 마이그레이션 파일에 넣기 까다롭다.

**Files:**
- Create: `supabase/migrations/0045_indexes_for_hot_paths.sql`

**Interfaces:**
- Consumes: 없음
- Produces: 인덱스 7개(6종). 전부 additive. Task 14 는 `children` 인덱스를 **다시 건드리지 않는다** (이 Task 가 이미 비부분으로 바꾼다).

- [ ] **Step 1: 지금 인덱스가 없다는 것을 확인한다 (실패를 먼저 본다)**

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python - <<'PY'
import json, os, urllib.request
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
r = urllib.request.Request(u + '/rest/v1/notice_cards?select=id&limit=1')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
r.add_header('Prefer', 'count=exact')
x = urllib.request.urlopen(r, timeout=60)
print('notice_cards 행 수:', x.headers.get('Content-Range'))
print('→ notice_id 인덱스는 pg_indexes 로 확인해야 한다. 적용 후 Step 4 에서 검증.')
PY
```

Expected: `0-0/29` 근처. (PostgREST 로는 `pg_indexes` 를 못 읽으므로 인덱스 존재 확인은 Step 4 의 대시보드/`db diff` 로 한다.)

- [ ] **Step 2: 마이그레이션을 쓴다**

`supabase/migrations/0045_indexes_for_hot_paths.sql`:

```sql
-- 지금 필요해서가 아니라, 나중에 필요할 때 이미 있어야 하기 때문이다.
-- 운영 규모(notices 38 / notice_cards 29 / children 9)에서는 계획이 바뀌지 않는다.
-- 전부 additive 이며 되돌리기는 drop index 한 줄이다.

-- 1) notice_cards 는 notice_id 로만 조회되는데 PK 말고 인덱스가 없었다.
--    RLS 정책 두 개가 매 행마다 notices.id = notice_cards.notice_id 로 조인하고,
--    0001:61 의 on delete cascade 도 인덱스 없는 FK 라 부모 삭제 시 전체 스캔이다.
create index if not exists notice_cards_notice_id_idx
  on public.notice_cards (notice_id);

-- 2) children(user_id) 단독 조회 — lib/server-cache.ts:97, 119
--    기존 children_user_school_id_idx 는 (user_id, school_id) WHERE school_id IS NOT NULL
--    부분 인덱스(0003:13-15)라, 조건 없는 WHERE user_id = ? 는 부분 조건을 증명하지
--    못해 못 탄다. 부분 조건을 떼어 선두 컬럼 단독 조회도 태운다.
--    (별도의 children(user_id) 단일 인덱스는 만들지 않는다 — 아래 복합 인덱스의
--     선두 컬럼이라 중복이다.)
drop index if exists public.children_user_school_id_idx;
create index if not exists children_user_school_id_idx
  on public.children (user_id, school_id);

-- 3) children(school_id) 단독 — content_extraction_service.py 의 학교별 자녀 조회와
--    RLS 'school events select own school'(0017:86-95). 복합 인덱스의 선두 컬럼이
--    아니라 못 탄다.
create index if not exists children_school_id_idx
  on public.children (school_id);

-- 4) 홈 목록 — app/(app)/page.tsx 의
--    .eq('school_id').eq('status','done').order('created_at' desc).limit(50)
--    notices_school_id_idx 는 school_id 단일이라 정렬·필터가 인덱스 밖이다.
create index if not exists notices_school_status_created_idx
  on public.notices (school_id, status, created_at desc);

-- 5) 추출 큐 스캔 — status IN ('pending','error','processing')
--    0007 의 부분 인덱스 둘은 각각 ('pending','error') 와 ('processing') 이라
--    세 값을 한 번에 묻는 쿼리는 어느 쪽에도 맞지 않아 시퀀셜 스캔이 된다.
create index if not exists notices_status_created_idx
  on public.notices (status, created_at);

-- 6) 완료된 잡을 job_key 로 되짚는 경로 — job_queue_service.py 의
--    completed_recently / latest_job / stale started_at 스캔.
--    app_jobs_active_job_key_idx 는 WHERE status IN ('queued','processing') 부분
--    인덱스(0027:22-24)라 완료된 잡이 그 밖에 있다.
create index if not exists app_jobs_job_key_created_idx
  on public.app_jobs (job_key, created_at desc);

create index if not exists app_jobs_started_at_idx
  on public.app_jobs (started_at);
```

- [ ] **Step 3: 번호 검사와 적용 예정 목록을 확인한다**

```bash
python scripts/check_migration_numbers.py
supabase db push --dry-run
```

Expected: `번호 중복 없음` + dry-run 목록에 `0045_indexes_for_hot_paths.sql` **하나만** 나온다. 다른 파일이 함께 나오면 **중단하고 보고할 것** — 사업 A 의 이력 정합이 안 끝났다는 뜻이다.

- [ ] **Step 4: 커밋 (적용은 머지 시 db-migrate 워크플로가 한다)**

```bash
git add supabase/migrations/0045_indexes_for_hot_paths.sql
git commit -m "perf(db): 실제로 도는 쿼리에 인덱스 6종 추가

38행에서는 계획이 바뀌지 않는다. 지금 넣는 이유는 나중에 넣기가 어렵기 때문이다 —
운영 중 create index 는 concurrently 가 필요하고 그건 트랜잭션 밖에서 돌아야 해서
마이그레이션 파일에 넣기 까다롭다.

notice_cards(notice_id) 가 제일 급하다. RLS 정책 둘이 매 행마다 이 조인을 돌고
on delete cascade 도 인덱스 없는 FK 다.

children_user_school_id_idx 는 부분 인덱스라 WHERE user_id=? 단독 조회를 못 탔다.
부분 조건을 떼어 재생성한다. 별도의 단일 인덱스는 만들지 않는다 — 선두 컬럼이라
중복이다."
```

- [ ] **Step 5: 머지 후 인덱스가 실제로 쓰이는지 확인한다**

머지되어 워크플로가 `0045` 를 적용한 뒤, Supabase 대시보드 SQL Editor 에서:

```sql
explain (analyze, buffers)
select id, type, "order", content
from public.notice_cards
where notice_id = (select id from public.notices limit 1);
```

Expected: `Index Scan using notice_cards_notice_id_idx` (또는 `Bitmap Index Scan`). `Seq Scan` 이 나오면 29행이라 플래너가 무시한 것일 수 있다 — `set enable_seqscan = off;` 로 인덱스가 존재하는지만 확인한다.

---

## Task 4: 저위험 위생 — 트리거 2 · 중복 정책 1 · 유령 버킷 1

**Files:**
- Create: `supabase/migrations/0046_low_risk_hygiene.sql`

**Interfaces:**
- Consumes: `public.set_updated_at()` (`0001:105-111`, 이미 6개 테이블이 쓰는 함수)
- Produces: `notice_cards` 의 SELECT 정책이 2 → 1. `notice-originals` 버킷 소멸. **코드 변경 0건.**

- [ ] **Step 1: 마이그레이션을 쓴다**

`supabase/migrations/0046_low_risk_hygiene.sql`:

```sql
-- (1) updated_at 컬럼은 있는데 트리거가 없어서 UPDATE 해도 값이 안 바뀌던 두 테이블.
--     notice_card_translations 는 코드도 수동으로 안 채우므로(notice_service 의 upsert
--     payload 에 updated_at 없음) 삽입 시각에 영원히 고정되어 있었다.
--     app_jobs 는 코드가 수동으로 채우지만 누락 경로가 있으면 조용히 stale 이 된다.
--     트리거가 덮어쓰므로 기존 수동 세팅은 그대로 둬도 무해하다.
drop trigger if exists notice_card_translations_set_updated_at on public.notice_card_translations;
create trigger notice_card_translations_set_updated_at
before update on public.notice_card_translations
for each row execute function public.set_updated_at();

drop trigger if exists app_jobs_set_updated_at on public.app_jobs;
create trigger app_jobs_set_updated_at
before update on public.app_jobs
for each row execute function public.set_updated_at();

-- (2) notice_cards 의 SELECT 정책이 논리적으로 동일한 것 둘이다.
--     0008:10-21 의 추가 조건 notices.school_id is not null 은 0006:81 이
--     school_id 를 NOT NULL 로 만든 이후 항상 참이다. PERMISSIVE 라 결과는 같지만
--     거의 같은 EXISTS 서브쿼리가 SELECT 마다 두 번 평가된다.
--     0009 가 idempotent 가드로 재생성까지 하는 0006/0009 쪽을 정본으로 남긴다.
drop policy if exists "notice cards select own school notice" on public.notice_cards;

-- (3) 유령 스토리지 버킷 notice-originals.
--     0001:243-254 가 만들고, 0006:92-94 가 정책 3개를 전부 지웠고,
--     유일한 참조 테이블 document_files 도 0006:65 가 drop 했다. 코드 참조 0건.
--     0006:91 주석이 스스로 "bucket 자체는 대시보드에서 수동으로 삭제할 것" 이라고
--     적어 두고 석 달간 안 지워졌다.
do $$
declare
  leftover integer;
begin
  select count(*) into leftover
  from storage.objects
  where bucket_id = 'notice-originals';

  if leftover > 0 then
    raise exception 'notice-originals 버킷에 오브젝트가 %개 남아 있어 삭제를 중단합니다', leftover;
  end if;

  delete from storage.buckets where id = 'notice-originals';
end $$;
```

- [ ] **Step 2: 번호 검사와 dry-run**

```bash
python scripts/check_migration_numbers.py
supabase db push --dry-run
```

Expected: `번호 중복 없음`. dry-run 에 `0046_low_risk_hygiene.sql` 만 (`0045` 가 이미 머지·적용됐다면).

- [ ] **Step 3: 커밋**

```bash
git add supabase/migrations/0046_low_risk_hygiene.sql
git commit -m "fix(db): updated_at 트리거 2개 · 중복 RLS 정책 · 유령 버킷 정리

notice_card_translations 와 app_jobs 는 updated_at 컬럼이 있는데 트리거가 없어
UPDATE 해도 값이 안 바뀌었다. 다른 6개 테이블과 같은 set_updated_at 트리거를 붙인다.

notice_cards 의 SELECT 정책 둘은 논리적으로 동일하다 — 0008 쪽의 추가 조건
notices.school_id is not null 은 0006:81 이 NOT NULL 로 만든 이후 항상 참이다.
같은 EXISTS 서브쿼리가 SELECT 마다 두 번 돌고 있었다.

notice-originals 버킷은 정책도 참조 테이블도 이미 사라졌는데 버킷만 남아 있었다.
0006:91 이 스스로 '수동으로 삭제할 것' 이라고 적어 둔 것을 이제 지운다.
오브젝트가 남아 있으면 raise exception 으로 중단한다."
```

- [ ] **Step 4: 머지 후 결과를 확인한다**

대시보드 SQL Editor 에서:

```sql
select count(*) as notice_cards_policies from pg_policies
  where schemaname = 'public' and tablename = 'notice_cards';
select count(*) as ghost_bucket from storage.buckets where id = 'notice-originals';
select tgname from pg_trigger
  where tgrelid in ('public.app_jobs'::regclass, 'public.notice_card_translations'::regclass)
    and not tgisinternal;
```

Expected: `notice_cards_policies` = **1** (2 에서 감소), `ghost_bucket` = **0**, 트리거 2행.

---

## Task 5: 깨진 데모 시드 스크립트 삭제

`scripts/seed-arabic-demo-account.cjs` 는 마지막 커밋이 `4b331ae` / 2026-06-04 이고, 그 뒤 `0012`~`0034` 가 적용되며 **15곳 이상에서 깨졌다.** 실행하면 `main()` 의 두 번째 스텝 `upsertProfile` 에서 즉사한다 (`profiles.role` 은 `0012:16` 이 지웠다).

**Files:**
- Delete: `scripts/seed-arabic-demo-account.cjs`

**Interfaces:**
- Consumes: 없음
- Produces: `schools.crawl_*` 를 쓰는 **TS/JS 마지막 경로가 사라진다.** Task 10 이 「쓰는 곳 0건」을 주장할 수 있게 된다.

- [ ] **Step 1: 정말 깨져 있는지 확인한다**

```bash
grep -n "role:\|school_name\|neis_office_code\|neis_school_code\|source_text\|ingredient_identity_map\|raw_pipeline\|requires_admin_review\|admin_review_reason\|from('schedules')\|crawl_status" scripts/seed-arabic-demo-account.cjs
```

Expected: 지워진 스키마 요소를 참조하는 줄이 10줄 이상 나온다 (`schedules` delete/insert, `profiles.role`, `children.school_name`, `notice_ai_translations` 의 제거된 컬럼들, `schools.crawl_*`).

- [ ] **Step 2: 다른 스크립트는 안 깨졌는지 확인한다**

```bash
git ls-files scripts/
grep -rn "from('schedules')\|table(\"schedules\")\|school_name\|requires_admin_review" $(git ls-files 'scripts/*.py' 'scripts/*.cjs' | grep -v seed-arabic)
echo "종료코드: $? (1 이면 없음 = 정상)"
```

Expected: git 추적 스크립트는 5개뿐이고, `seed-arabic-demo-account.cjs` 를 뺀 나머지 4개에서는 출력이 없다. (`scripts/` 의 나머지 파일은 untracked 로컬 스크래치라 이 사업의 관리 대상이 아니다.)

- [ ] **Step 3: 삭제한다**

```bash
git rm scripts/seed-arabic-demo-account.cjs
```

고치지 않고 지우는 이유: 15곳 이상을 고쳐야 하고, 고쳐도 `lib/demo-school.ts`(1537줄)와 기능이 겹치며, **데모 종료 결정과 정면으로 충돌**한다.

- [ ] **Step 4: 잔존 참조가 없는지 확인한다**

```bash
grep -rn "seed-arabic-demo-account" --include=*.json --include=*.yml --include=*.md --include=*.ts . | grep -v node_modules
echo "종료코드: $? (1 이면 없음 = 정상)"
```

Expected: 출력 없음, 종료코드 1. (`package.json` 이나 워크플로가 이 스크립트를 부르지 않는다.)

- [ ] **Step 5: 커밋**

```bash
git commit -m "chore(scripts): 깨진 아랍어 데모 시드 스크립트 삭제

마지막 커밋이 2026-06-04 이고 그 뒤 0012~0034 가 적용되며 15곳 이상에서 깨졌다.
지금 돌리면 두 번째 스텝 upsertProfile 에서 즉사한다 — profiles.role 은 0012 가
지웠다. 그 밖에 drop 된 schedules 테이블, children 의 학교 중복 필드,
notice_ai_translations 의 제거된 컬럼 7개를 그대로 참조한다.

고치지 않고 지운다. 고쳐도 lib/demo-school.ts 와 기능이 겹치고,
데모 종료 결정과 충돌한다.

부수 효과로 schools.crawl_* 를 쓰는 TS/JS 마지막 경로가 사라진다."
```

---

## Task 6: 데모·쇼케이스 실측 + 이관 대상 확정

**이 Task 는 운영 데이터를 바꾸지 않는다.** 삭제 앵커와 **자녀 이관 대상**을 실행 시점에 다시 확정하는 것이 산출물이다.

방향은 이미 정해져 있다 (결정 4·5): **데모 학교의 자녀 2건을 진짜 부천부흥중학교로 옮기고, 데모·쇼케이스 두 학교를 삭제한다.** 이 Task 가 하는 일은 계획 작성 시점(2026-08-27)의 실측이 **실행 시점에도 여전히 맞는지** 확인하는 것이다. 그 사이 자녀가 늘었다면 그건 새 사실이므로 중단하고 보고한다.

**Files:**
- Create: `scripts/audit_demo_data.py`

**Interfaces:**
- Consumes: service_role 읽기 권한
- Produces: 데모·쇼케이스 두 앵커의 UUID, 이관 대상 학교의 UUID 와 크롤 준비 상태, FK 의존 건수. Task 8 의 마이그레이션이 쓸 값들을 확정한다.

- [ ] **Step 1: 조사 스크립트를 쓴다**

`scripts/audit_demo_data.py`:

```python
"""데모·쇼케이스 학교의 데이터 발자국과 자녀 이관 대상을 조사한다.

읽기 전용이다. 아무것도 지우거나 바꾸지 않는다.

식별에 학교 '이름' 을 쓰지 않는다. 데모 학교의 이름이 진짜 학교와 글자까지
똑같은 '부천부흥중학교' 라서 이름으로는 구분이 불가능하기 때문이다.
앵커는 (neis_office_code, neis_school_code) 조합뿐이다 — 그 조합은
schools_neis_office_code_neis_school_code_key(0001:27) 유니크 제약을 타므로
학교 1개를 확정하고, 확정된 UUID 만으로 FK 를 따라간다.
이름은 사람이 눈으로 확인하도록 출력에만 쓴다.

기대와 다르면 종료코드 1 을 낸다. 기대치는 EXPECTED 에 적혀 있고,
2026-08-27 실측 + 사용자 결정에 근거한다.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# 삭제 대상 (label, office_code, school_code, 기대 자녀 수)
ANCHORS = [
    ("데모", "DEMO", "NARANHI001", 2),
    ("쇼케이스", "SHOWCASE", "NARANHI_SHOWCASE", 0),
]

# 데모 학교 자녀의 이관 대상 — 진짜 부천부흥중학교
TRANSFER_TO = ("J10", "7581020")


def get(path):
    req = urllib.request.Request(URL + "/rest/v1/" + path)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "[]")
    except urllib.error.HTTPError as e:
        print(f"  요청 실패 {e.code}: {path}")
        return None


def school_id_for(office, code):
    rows = get(f"schools?neis_office_code=eq.{office}&neis_school_code=eq.{code}&select=id,name,address")
    if rows is None or len(rows) != 1:
        return None, rows
    return rows[0]["id"], rows[0]


failed = False
demo_children = []

for label, office, code, expected_children in ANCHORS:
    print(f"\n=== {label} 학교 ({office}/{code}) ===")
    sid, row = school_id_for(office, code)
    if sid is None:
        if row == []:
            # 삭제 후 재실행하면 여기로 온다. 정상이다.
            print("  학교 없음 — 이미 삭제됐거나 애초에 없다")
            continue
        print(f"  학교가 정확히 1건이 아니다: {row!r}")
        print("  → 삭제 마이그레이션의 앵커 확정이 실패한다")
        failed = True
        continue

    print(f"  id={sid}")
    print(f"  name={row['name']!r}  address={row['address']!r}   (이름은 확인용. 필터에 쓰지 않는다)")

    notice_ids = [n["id"] for n in get(f"notices?school_id=eq.{sid}&select=id") or []]
    counts = {
        "notices": len(notice_ids),
        "school_events": len(get(f"school_events?school_id=eq.{sid}&select=id") or []),
        "school_crawl_state": len(get(f"school_crawl_state?school_id=eq.{sid}&select=school_id") or []),
        "meals": len(get(f"meals?office_code=eq.{office}&school_code=eq.{code}&select=id") or []),
    }
    if notice_ids:
        inl = "(" + ",".join(notice_ids) + ")"
        card_ids = [c["id"] for c in get(f"notice_cards?notice_id=in.{inl}&select=id") or []]
        counts["notice_cards"] = len(card_ids)
        counts["notice_ai_translations"] = len(get(f"notice_ai_translations?notice_id=in.{inl}&select=id") or [])
        # notice_hides 에는 id 컬럼이 없다. PK 가 (user_id, notice_id) 복합키다(0004:1-6).
        # select=id 로 물으면 HTTP 400 이 난다.
        counts["notice_hides"] = len(get(f"notice_hides?notice_id=in.{inl}&select=notice_id") or [])
        if card_ids:
            cinl = "(" + ",".join(card_ids) + ")"
            counts["notice_card_translations"] = len(
                get(f"notice_card_translations?notice_card_id=in.{cinl}&select=id") or []
            )

    children = get(f"children?school_id=eq.{sid}&select=id,user_id,name,grade,class_no,created_at") or []
    counts["children"] = len(children)

    for key, value in counts.items():
        print(f"    {key:26s} {value}")

    if len(children) != expected_children:
        print(f"    !! 자녀가 {len(children)}건이다. 기대치는 {expected_children}건 — 중단하고 보고할 것")
        failed = True
    for c in children:
        print(
            f"      child={c['id'][:8]}  user={c['user_id'][:8]}  name={c['name']!r}  "
            f"{c['grade']}-{c['class_no']}  생성 {c['created_at'][:10]}"
        )
    if label == "데모":
        demo_children = children

# ── 이관 대상 학교 ────────────────────────────────────────────
office, code = TRANSFER_TO
print(f"\n=== 이관 대상 학교 ({office}/{code}) ===")
real_id, real_row = school_id_for(office, code)
if real_id is None:
    print(f"  학교가 정확히 1건이 아니다: {real_row!r} — 이관할 수 없다")
    failed = True
else:
    print(f"  id={real_id}")
    print(f"  name={real_row['name']!r}   (데모 학교와 이름이 같다. 그래서 UUID 로만 다룬다)")

    state = get(f"school_crawl_state?school_id=eq.{real_id}&select=crawl_status,crawl_board_url,crawl_last_checked_at") or []
    if not state:
        print("  !! school_crawl_state 행이 없다 — 이관해도 크롤이 돌지 않는다. 상태 행을 먼저 만들 것")
        failed = True
    else:
        print(f"    crawl_status      {state[0]['crawl_status']}")
        print(f"    crawl_board_url   {state[0]['crawl_board_url']}")
        print(f"    최종 확인          {state[0]['crawl_last_checked_at']}")

    print(f"    notices           {len(get(f'notices?school_id=eq.{real_id}&select=id') or [])}")
    print(f"    school_events     {len(get(f'school_events?school_id=eq.{real_id}&select=id') or [])}")
    before = len(get(f"children?school_id=eq.{real_id}&select=id") or [])
    print(f"    children (이관 전)  {before}")
    print(f"    children (이관 후)  {before + len(demo_children)}  <- 대조용")

# ── 이관될 사용자의 파생 데이터 ────────────────────────────────
if demo_children:
    print("\n=== 이관될 사용자의 파생 데이터 ===")
    for uid in sorted({c["user_id"] for c in demo_children}):
        hides = get(f"notice_hides?user_id=eq.{uid}&select=notice_id") or []
        print(f"  user {uid[:8]}  notice_hides {len(hides)}")
        if hides:
            print("    (숨긴 공지는 데모 학교 공지이므로 학교 삭제 시 cascade 로 함께 사라진다)")

if failed:
    print("\n판정: 기대와 다르다. 중단하고 보고할 것.")
    sys.exit(1)

print("\n판정: 진행 가능. Task 8 의 이관·삭제를 실행할 수 있다.")
```

- [ ] **Step 2: 실행해 실측이 여전히 맞는지 확인한다**

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python scripts/audit_demo_data.py; echo "종료코드: $?"
```

Expected (2026-08-27 실측 기준):

```
=== 데모 학교 (DEMO/NARANHI001) ===
  id=3b33ac1d-0cb9-4199-9568-51431b876e63
  name='부천부흥중학교'  address='경기도 부천시'   (이름은 확인용. 필터에 쓰지 않는다)
    notices                    0
    school_events              0
    school_crawl_state         1
    meals                      8
    children                   2
      child=aab67a6b  user=d27d07a3  name='ㅇ'  1-1  생성 2026-06-10
      child=19b27dd9  user=884331fc  name='ㅣ'  1-1  생성 2026-06-10

=== 쇼케이스 학교 (SHOWCASE/NARANHI_SHOWCASE) ===
  id=9bfee999-c9fe-4eed-8cb5-a218453c9bb8
  name='Naranhi Showcase School'  address='Showcase only'   (이름은 확인용. 필터에 쓰지 않는다)
    notices                    2
    notice_cards               2
    notice_ai_translations     10
    notice_hides               0
    school_events              6
    school_crawl_state         0
    meals                      0
    children                   0

=== 이관 대상 학교 (J10/7581020) ===
  id=8da4b348-e3a2-4d24-884d-f7f55d04c0be
  name='부천부흥중학교'   (데모 학교와 이름이 같다. 그래서 UUID 로만 다룬다)
    crawl_status      success
    crawl_board_url   https://pcbuheung-m.goebc.kr/pcbuheung-m/na/ntt/selectNttList.do?mi=8464&bbsId=4717
    notices           8
    school_events     9
    children (이관 전)  2
    children (이관 후)  4  <- 대조용

=== 이관될 사용자의 파생 데이터 ===
  user 884331fc  notice_hides 0
  user d27d07a3  notice_hides 0

판정: 진행 가능.
```

종료코드 **0**.

**자녀 수가 2건이 아니면 종료코드 1 이 나온다 — 중단하고 보고할 것.** 계획 작성(2026-08-27) 이후 누가 데모 학교로 온보딩했다는 뜻이고, 그건 사용자 결정이 다루지 않은 새 사실이다.

- [ ] **Step 3: 이관이 무해한지 세 가지를 확인한다**

Step 2 출력에서 아래 셋을 **눈으로** 확인한다. 하나라도 어긋나면 Task 8 을 시작하지 않는다.

| # | 확인 | 왜 | 어긋나면 |
|---|---|---|---|
| 1 | 이관 대상 학교에 `school_crawl_state` 행이 **있다** (`crawl_status=success`) | 상태 행이 없으면 옮겨도 크롤이 안 돈다. **§8.3 의 「상태 행 없는 학교 1개」는 쇼케이스이지 이 학교가 아니다** | `ensureSchoolCrawlerState` 상당의 insert 를 `0047` 앞에 넣는다 |
| 2 | 이관될 두 사용자의 `notice_hides` 가 **0건** | 숨긴 공지가 있으면 그건 데모 학교 공지이고, 학교 삭제 시 `notices` cascade 로 함께 사라진다. 0건이면 그 처리조차 필요 없다 | `0047` 의 `notice_hides` 삭제가 그 행을 함께 지운다 (이미 포함됨) |
| 3 | 이관 대상 학교에 `notices` 8 · `school_events` 9 가 **있다** | 옮긴 두 계정이 즉시 실제 공지를 보게 된다. 0 이면 옮겨도 빈 화면이다 | 크롤을 1회 돌린 뒤 이관한다 |

`children` 에는 UNIQUE 제약이 없으므로(`0001` PK 외에 `0016` FK 와 `0034` 배열 CHECK 뿐) 같은 학년·반이 겹쳐도 이관이 충돌하지 않는다.

- [ ] **Step 4: 커밋 (스크립트만)**

```bash
git add scripts/audit_demo_data.py
git commit -m "chore(scripts): 데모·쇼케이스 학교 발자국 + 자녀 이관 대상 조사 스크립트

식별에 학교 이름을 쓰지 않는다. 데모 학교의 이름이 진짜 학교와 글자까지 똑같은
'부천부흥중학교' 라 이름으로는 구분이 불가능하다. 앵커는
(neis_office_code, neis_school_code) 조합뿐이고, 그 조합이 유니크 제약을 타
학교 1개를 확정한다. 이름은 사람이 눈으로 확인하도록 출력에만 쓴다.

읽기 전용이다. 기대와 다르면 종료코드 1 을 낸다 — 특히 데모 학교의 자녀가
2건이 아니면 중단한다. 계획 수립 이후 누가 데모 학교로 온보딩했다는 뜻이고
그건 사용자 결정이 다루지 않은 새 사실이다.

이관 대상 학교의 school_crawl_state 존재 여부도 함께 확인한다.
상태 행이 없으면 옮겨도 크롤이 돌지 않는다.

notice_hides 는 select=notice_id 로 조회한다. 이 테이블에는 id 컬럼이 없고
PK 가 (user_id, notice_id) 복합키라 select=id 는 HTTP 400 이 난다."
```

---

## Task 7: 데모 시드 코드 제거 (D5-a)

**코드 먼저, 데이터 나중.** 코드가 살아 있는 동안 데이터를 지우면 다음 홈 렌더에서 `ensureDemoSchoolSeed()` 가 다시 뿌린다.

**Files:**
- Delete: `lib/demo-school.ts` (1537줄)
- Delete: `app/(app)/settings/DemoSchoolPicker.tsx`
- Modify: `app/onboarding/actions.ts`, `app/(app)/settings/actions.ts`, `app/(app)/settings/page.tsx`, `app/(app)/page.tsx`, `app/(app)/meals/page.tsx`, `app/api/schools/search/route.ts`

**Interfaces:**
- Consumes: 사업 A 가 `lib/test-entry-bypass.ts` 를 지운 상태
- Produces: `demo-school` 심볼이 저장소에서 사라진다. `school_events.source_language` 를 읽는 마지막 TS 경로(`lib/demo-school.ts:1157`)도 함께 사라져 Task 13 이 가능해진다.

- [ ] **Step 1: 참조 지점을 전부 찾는다**

```bash
grep -rn "demo-school\|ensureDemoSchoolSeed\|isDemoSchoolSelection\|maybeInjectDemoSchoolResult\|getSeededDemoMealsForRange\|DemoSchoolPicker\|selectDemoSchool" \
  --include=*.ts --include=*.tsx . | grep -v node_modules | grep -v .claude/worktrees
```

Expected: `lib/demo-school.ts` 자신 외에 `app/onboarding/actions.ts`, `app/(app)/settings/actions.ts`, `app/(app)/settings/page.tsx`, `app/(app)/settings/DemoSchoolPicker.tsx`, `app/(app)/page.tsx`, `app/(app)/meals/page.tsx`, `app/api/schools/search/route.ts`. **목록을 기록해 둘 것.**

> 사업 A 가 이미 `selectDemoSchool` / `DemoSchoolPicker` 를 지웠다면 그 항목은 목록에 없다. 있으면 이 Task 가 지운다.

- [ ] **Step 2: 학교 검색에서 데모 주입을 뺀다**

`app/api/schools/search/route.ts` — import 와 두 호출을 지운다:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { searchSchools } from '@/lib/neis'
```

```typescript
  try {
    const results = await searchSchools(query)
    return NextResponse.json({ results })
  } catch (e) {
    console.error('[api/schools/search] failed:', e instanceof Error ? e.message : e)
    return NextResponse.json({ results: [], error: '학교 검색에 실패했어요.' }, { status: 500 })
  }
```

- [ ] **Step 3: 온보딩·설정에서 데모 분기를 뺀다**

`app/onboarding/actions.ts`: `import { ensureDemoSchoolSeed, isDemoSchoolSelection } from '@/lib/demo-school'` 줄, `const isDemoSchool = isDemoSchoolSelection({...})` 블록, 그리고 `if (isDemoSchool) { await ensureDemoSchoolSeed(...) }` 블록을 **통째로 삭제**한다. 대체 로직을 넣지 않는다.

`app/(app)/settings/actions.ts`: 같은 import 와 `isDemoSchool` 블록을 지운다. `if (isDemoSchool) { … shouldTriggerCrawl = false }` 를 지우면 **데모 학교에도 크롤이 걸리게 되는데, 그 학교는 Task 8 이 지우므로 의도된 동작이다.**

`app/(app)/settings/page.tsx`: `DemoSchoolPicker` import 와 렌더 블록을 지운다.

- [ ] **Step 4: 홈·급식에서 데모 분기를 뺀다**

`app/(app)/page.tsx`: `import { ensureDemoSchoolSeed, isDemoSchoolSelection } from '@/lib/demo-school'` 와 `if (child.school_id && isDemoSchoolSelection({...})) { … }` 블록을 지운다.

`app/(app)/meals/page.tsx`: `lib/demo-school` import 블록(`ensureDemoSchoolSeed`, `getSeededDemoMealsForRange`, `isDemoSchoolSelection`)과 `const isDemoSchool = …` / `if (isDemoSchool) { … }` 분기를 통째로 지운다. **데모 분기가 사라지면 일반 NEIS 경로(`getCachedOrFetchMealsForRange`)로 떨어진다** — 그게 정상 동작이다.

- [ ] **Step 5: 파일들을 지운다**

```bash
git rm lib/demo-school.ts "app/(app)/settings/DemoSchoolPicker.tsx"
```

- [ ] **Step 6: 잔존 참조가 없는지 확인한다**

```bash
grep -rn "demo-school\|ensureDemoSchoolSeed\|isDemoSchoolSelection\|maybeInjectDemoSchoolResult\|getSeededDemoMealsForRange\|DemoSchoolPicker\|selectDemoSchool\|DEMO_SCHOOL" \
  --include=*.ts --include=*.tsx . | grep -v node_modules | grep -v .claude/worktrees
echo "종료코드: $? (1 이면 없음 = 정상)"
```

Expected: 출력 없음, 종료코드 1

- [ ] **Step 7: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 둘 다 성공. 실패하면 Step 3~4 에서 지운 블록의 잔재(쓰이지 않는 변수, 닫히지 않은 `try`)다.

- [ ] **Step 8: 커밋**

```bash
git add -A app lib
git commit -m "refactor(demo): 데모 학교 시드 코드 제거

데모 종료 결정에 따라 lib/demo-school.ts(1537줄)와 DemoSchoolPicker 를 삭제하고
온보딩·설정·홈·급식·학교검색의 데모 분기를 전부 걷어낸다.

데이터보다 코드를 먼저 지운다 — 코드가 살아 있는 동안 데이터를 지우면
다음 렌더에서 ensureDemoSchoolSeed 가 다시 뿌린다.

급식의 데모 분기가 사라지면 일반 NEIS 경로로 떨어진다. 설정에서 데모 학교의
크롤 억제(shouldTriggerCrawl = false)도 사라지는데, 그 학교는 다음 단계에서
삭제되므로 의도된 동작이다.

부수 효과: school_events.source_language 를 읽는 마지막 TS 경로가 사라진다."
```

- [ ] **Step 9: 새 데모 데이터가 더 이상 생기지 않는지 확인한다**

배포 후 홈·급식·설정을 한 번씩 렌더한 뒤:

```bash
python scripts/audit_demo_data.py; echo "종료코드: $?"
```

Expected: Task 6 Step 2 와 **같은 숫자** + 종료코드 0. 늘어난 항목이 있으면 시드 경로가 남아 있다는 뜻이다 — 중단하고 Step 1 로 돌아간다.

특히 데모 학교의 `children` 이 여전히 **2** 여야 한다. 3 이상이면 Task 8 의 가드가 마이그레이션을 중단시킨다.

---

## Task 8: 자녀 이관 + 데모·쇼케이스 삭제 (D5-b) 🔴

**사용자 결정 (2026-08-27): 「진짜 학교로 옮기고 데모 삭제」.** 자녀 2건의 `school_id` 를 진짜 부천부흥중학교(`J10`/`7581020`)로 갱신한 뒤 데모·쇼케이스 두 학교를 삭제한다. **자녀 행 자체는 지우지 않는다** — 계정도 온보딩 상태도 보존된다.

이관은 `school_id` **한 컬럼만** 바꾼다. `user_id` · `name` · `grade` · `class_no` · `dietary_restrictions` 는 건드리지 않는다.

**Files:**
- Create: `supabase/migrations/0047_remove_demo_school_data.sql`

**Interfaces:**
- Consumes: Task 6 이 확정한 앵커 UUID 와 이관 대상, Task 7 이 제거한 시드 코드
- Produces: `schools` 8 → 6. 이관 대상 학교의 `children` 2 → 4. 데모·쇼케이스 파생 데이터 소멸.

- [ ] **Step 1: 마이그레이션을 쓴다**

`supabase/migrations/0047_remove_demo_school_data.sql`:

```sql
-- 데모 학교의 자녀를 진짜 학교로 이관한 뒤, 데모·쇼케이스 학교와 그 파생 데이터를
-- 지운다. 사용자 결정(2026-08-27): "진짜 학교로 옮기고 데모 삭제".
--
-- 식별에 학교 '이름' 을 쓰지 않는다. 데모 학교의 이름은 'Naranhi School' 이 아니라
-- 진짜 학교와 글자까지 똑같은 '부천부흥중학교' 다 — 이름으로는 구분이 불가능하다.
-- (neis_office_code, neis_school_code) 조합만이 안전한 식별자다.
-- 그 조합은 schools_neis_office_code_neis_school_code_key(0001:27) 유니크 제약을 탄다.
--
-- FK 는 대부분 cascade 라 notices 삭제만으로 하위가 따라오지만, 건수를 눈으로
-- 확인하기 위해 순서를 명시한다.

do $$
declare
  demo_id      uuid;
  show_id      uuid;
  real_id      uuid;
  moved        integer;
  before_real  integer;
  after_real   integer;
  n            integer;
begin
  -- ── 앵커 확정 ──────────────────────────────────────────────
  select id into demo_id from public.schools
  where neis_office_code = 'DEMO' and neis_school_code = 'NARANHI001';

  select id into show_id from public.schools
  where neis_office_code = 'SHOWCASE' and neis_school_code = 'NARANHI_SHOWCASE';

  -- 이관 대상: 진짜 부천부흥중학교. 이름이 데모와 같으므로 코드로만 찾는다.
  select id into real_id from public.schools
  where neis_office_code = 'J10' and neis_school_code = '7581020';

  -- ── 데모 학교 ──────────────────────────────────────────────
  if demo_id is null then
    raise notice '데모 학교 없음 — 건너뜀';
  else
    select count(*) into n from public.children where school_id = demo_id;

    if n > 0 then
      -- 계획 수립 시점(2026-08-27) 실측은 2건이었다. 그보다 늘었다면
      -- 그 사이 누가 데모 학교로 온보딩했다는 뜻이고, 사용자 결정이 다루지
      -- 않은 새 사실이다. 조용히 옮기지 않고 중단한다.
      if n <> 2 then
        raise exception
          '데모 학교의 자녀가 %건입니다. 결정 시점의 2건과 다르므로 중단합니다 — 재확인 후 진행하세요', n;
      end if;

      if real_id is null then
        raise exception
          '이관 대상 학교(J10/7581020)를 찾을 수 없는데 데모 학교에 자녀가 %건 있습니다', n;
      end if;

      -- 옮긴 뒤에도 크롤이 돌아야 한다. 상태 행이 없으면 만든다
      -- (lib/school-crawl-state.ts 의 ensureSchoolCrawlerState 와 같은 기본값).
      insert into public.school_crawl_state (school_id, crawl_board_kind, crawl_status)
      values (real_id, 'unknown', 'pending')
      on conflict (school_id) do nothing;

      select count(*) into before_real from public.children where school_id = real_id;

      -- school_id 한 컬럼만 바꾼다. user_id·name·grade·class_no·dietary_restrictions
      -- 는 그대로 둔다. children 에는 UNIQUE 제약이 없어(0001 PK 외 0016 FK 와
      -- 0034 배열 CHECK 뿐) 같은 학년·반이 겹쳐도 충돌하지 않는다.
      update public.children set school_id = real_id where school_id = demo_id;
      get diagnostics moved = row_count;

      select count(*) into after_real from public.children where school_id = real_id;

      if after_real <> before_real + moved then
        raise exception '이관 행 수가 맞지 않습니다: 이전 % + 이관 % <> 이후 %',
          before_real, moved, after_real;
      end if;

      raise notice '자녀 이관 완료: %건 (대상 학교 % → %)', moved, before_real, after_real;
    end if;

    delete from public.notice_card_translations
    where notice_card_id in (
      select nc.id from public.notice_cards nc
      join public.notices n2 on n2.id = nc.notice_id
      where n2.school_id = demo_id
    );

    delete from public.notice_cards
    where notice_id in (select id from public.notices where school_id = demo_id);

    delete from public.notice_ai_translations
    where notice_id in (select id from public.notices where school_id = demo_id);

    delete from public.notice_hides
    where notice_id in (select id from public.notices where school_id = demo_id);

    delete from public.school_events where school_id = demo_id;
    delete from public.notices      where school_id = demo_id;

    -- meals 만 문자열에 의존한다. schools 와 FK 가 없고(0001:80-93)
    -- NEIS 코드 단위 전역 공유 캐시로 설계되어 있기 때문이다.
    delete from public.meals
    where office_code = 'DEMO' and school_code = 'NARANHI001';

    delete from public.school_crawl_state where school_id = demo_id;
    delete from public.schools            where id = demo_id;
    raise notice '데모 학교 삭제 완료: %', demo_id;
  end if;

  -- ── 쇼케이스 학교 ──────────────────────────────────────────
  -- 저장소 어디에서도 참조되지 않는 시연용 잔재다(코드 검색 0건).
  -- 자녀가 0건이라 ON DELETE RESTRICT 에 막히지 않고, 나머지는 전부 cascade 다:
  --   schools ─cascade→ school_events(0017:3-4) · school_crawl_state(0013:2) · notices
  --   notices ─cascade→ notice_cards(0001:61) · notice_ai_translations(0005:3) · notice_hides(0004:3)
  --   notice_cards ─cascade→ notice_card_translations(0026:3)
  -- 즉 `delete from schools` 한 줄이면 공지 2·카드 2·번역 10·일정 6 이 전부 따라온다.
  -- 그래도 순서를 명시해 지우는 이유는 건수를 눈으로 확인하기 위해서다 —
  -- cascade 는 조용해서 무엇이 얼마나 사라졌는지 알려주지 않는다.
  if show_id is null then
    raise notice '쇼케이스 학교 없음 — 건너뜀';
  else
    select count(*) into n from public.children where school_id = show_id;
    if n > 0 then
      raise exception '쇼케이스 학교에 자녀가 %건 있습니다 — 중단합니다', n;
    end if;

    delete from public.notice_card_translations
    where notice_card_id in (
      select nc.id from public.notice_cards nc
      join public.notices n2 on n2.id = nc.notice_id
      where n2.school_id = show_id
    );

    delete from public.notice_cards
    where notice_id in (select id from public.notices where school_id = show_id);

    delete from public.notice_ai_translations
    where notice_id in (select id from public.notices where school_id = show_id);

    delete from public.notice_hides
    where notice_id in (select id from public.notices where school_id = show_id);

    delete from public.school_events      where school_id = show_id;
    delete from public.notices            where school_id = show_id;
    delete from public.school_crawl_state where school_id = show_id;
    delete from public.schools            where id = show_id;
    raise notice '쇼케이스 학교 삭제 완료: %', show_id;
  end if;
end $$;
```

- [ ] **Step 2: 번호 검사와 dry-run**

```bash
python scripts/check_migration_numbers.py
supabase db push --dry-run
```

Expected: `번호 중복 없음` + dry-run 에 `0047_remove_demo_school_data.sql`

- [ ] **Step 3: 커밋**

```bash
git add supabase/migrations/0047_remove_demo_school_data.sql
git commit -m "feat(db): 데모 학교 자녀 이관 + 데모·쇼케이스 학교 삭제

데모는 끝났다는 결정에 따라 운영 테이블에서 걷어낸다.

식별에 학교 이름을 쓰지 않는다. 데모 학교의 이름이 'Naranhi School' 이 아니라
진짜 학교와 글자까지 똑같은 '부천부흥중학교' 라 이름으로는 구분이 불가능하다.
(neis_office_code, neis_school_code) 조합으로 학교 1개를 확정하고
그 UUID 만 앵커로 FK 를 따라간다.

데모 학교에 붙어 있던 실제 계정 2개의 자녀는 삭제하지 않고 진짜
부천부흥중학교(J10/7581020)로 이관한다 — 사용자 결정 2026-08-27
'진짜 학교로 옮기고 데모 삭제'. school_id 한 컬럼만 바꾸고
user_id·name·grade·class_no·dietary_restrictions 는 건드리지 않는다.

가드 셋을 둔다. 자녀가 2건이 아니면 중단한다(그 사이 누가 데모 학교로
온보딩했다는 뜻이다). 이관 대상 학교가 없어도 중단한다. 이관 전후 행 수가
안 맞아도 중단한다. 그리고 옮긴 뒤 크롤이 돌도록 대상 학교의
school_crawl_state 행을 보장한다.

저장소 어디에서도 참조되지 않는 Naranhi Showcase School(공지 2, 카드 2,
번역 10, 일정 6, 자녀 0)도 함께 지운다. 전부 cascade 라 schools 한 줄이면
따라오지만, 건수를 눈으로 보려고 순서를 명시한다.

meals 만 문자열 조건에 의존한다 — schools 와 FK 가 없고 NEIS 코드 단위
전역 공유 캐시로 설계되어 있다."
```

- [ ] **Step 4: 머지 후 이관 결과를 대조한다**

```bash
python - <<'PY'
import json, os, urllib.request, collections
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
def get(p):
    r = urllib.request.Request(u + '/rest/v1/' + p)
    r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode() or '[]')
sch = {s['id']: s for s in get('schools?select=id,name,neis_office_code,neis_school_code')}
kids = get('children?select=id,user_id,name,school_id,grade,class_no,created_at')
print('schools:', len(sch), '(이관·삭제 전 8)')
print('children:', len(kids), '(변하지 않아야 한다)')
for c in sorted(kids, key=lambda x: x['school_id']):
    s = sch.get(c['school_id'], {})
    print(f"  child={c['id'][:8]} user={c['user_id'][:8]} name={c['name']!r} "
          f"-> {s.get('name')} ({s.get('neis_office_code')}/{s.get('neis_school_code')})")
print('학교별 자녀:', dict(collections.Counter(c['school_id'][:8] for c in kids)))
PY
```

Expected:
- `schools: 6` (8 에서 데모·쇼케이스 둘이 빠짐)
- `children: 9` — **변하지 않는다.** 자녀는 지운 게 아니라 옮긴 것이다
- 이관된 두 자녀(`aab67a6b`, `19b27dd9`)가 **`부천부흥중학교 (J10/7581020)`** 아래에 있다
- `8da4b348…` 의 자녀 수 **2 → 4**
- `DEMO` / `SHOWCASE` 코드를 가진 학교가 목록에 없다

`children` 수가 9 보다 줄었으면 **이관이 아니라 삭제가 일어난 것이다** — 즉시 보고할 것.

- [ ] **Step 5: 앵커가 사라졌는지 확인한다**

```bash
python scripts/audit_demo_data.py; echo "종료코드: $?"
```

Expected: 두 앵커 모두 `학교 없음 — 이미 삭제됐거나 애초에 없다`, 이관 대상 학교의 `children (이관 전) 4`, 종료코드 **0**

- [ ] **Step 6: 회귀 확인**

로그인 → 홈 → 캘린더 → 급식 → 설정 → 학교 검색(`나란히`, `demo`, `부천부흥` 으로 검색).

- 데모 학교가 **어디에도 나오지 않아야** 한다
- `부천부흥` 검색 결과에 **진짜 학교 하나만** 나와야 한다 (예전엔 이름이 같은 둘이 나올 수 있었다)
- **이관된 두 계정으로 로그인해** 홈을 열면 진짜 부천부흥중학교의 공지 8건과 캘린더 일정 9건이 보여야 한다. 빈 화면이면 이관은 됐지만 크롤 상태 행이 없는 것이다 — `school_crawl_state` 를 확인한다

---

## Task 9: 크롤러 이중 쓰기 제거 (D6-a)

`_save_school_discovery_result()` 가 같은 값을 `schools` 와 `school_crawl_state` 두 곳에 쓴다. 두 문장이 트랜잭션으로 묶여 있지도 않아 앞이 성공하고 뒤가 실패하면 두 테이블이 갈린다.

> ⚠️ **`schools` UPDATE 를 통째로 제거하면 안 된다.** `homepage_url` 은 `schools` 에만 있고 `school_crawl_state` 에는 없다(`0013` 에 미포함). 크롤러가 크롤 대상 URL 을 얻는 유일한 경로가 `_context_from_school_row()` 의 `row.get("homepage_url")` 이다. **crawl_* 6키만 빼고 `homepage_url` 백필은 남긴다.**

**Files:**
- Modify: `backend/app/services/school_crawler_service.py` (`_fetch_school_row`, `_save_school_discovery_result`)
- Create: `backend/tests/test_school_crawler_state_write.py`

**Interfaces:**
- Consumes: Task 5·8 (마지막 `schools.crawl_*` 쓰기 경로 제거, 상태 행 없는 학교 제거)
- Produces: `_school_backfill_payload(result) -> dict[str, Any]`. `schools.crawl_*` 를 쓰는 코드가 저장소에서 0건이 된다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_school_crawler_state_write.py`:

```python
import unittest
from types import SimpleNamespace

from app.services import school_crawler_service


class SchoolBackfillPayloadTest(unittest.TestCase):
    """schools 에 남기는 백필은 homepage_url 하나뿐이어야 한다.

    크롤 상태의 정본은 school_crawl_state 다(0013). schools 의 crawl_* 6컬럼은
    다음 단계에서 삭제되므로, 그 전에 쓰기가 끊겨 있어야 한다.
    homepage_url 만은 schools 에만 있고 크롤 대상 URL 의 유일한 소스라 남긴다.
    """

    def test_only_homepage_url_is_written_back(self):
        payload = school_crawler_service._school_backfill_payload(
            SimpleNamespace(homepage_url="https://school.example.kr")
        )
        self.assertEqual(payload, {"homepage_url": "https://school.example.kr"})

    def test_no_crawl_columns_in_payload(self):
        payload = school_crawler_service._school_backfill_payload(
            SimpleNamespace(homepage_url="https://school.example.kr")
        )
        for key in (
            "crawl_status",
            "crawl_error_message",
            "crawl_result",
            "crawl_board_url",
            "crawl_board_kind",
            "crawl_last_checked_at",
        ):
            self.assertNotIn(key, payload)

    def test_empty_payload_when_homepage_missing(self):
        """빈 dict 로 update 를 치면 PostgREST 가 400 을 낸다. 호출 자체를 건너뛴다."""
        self.assertEqual(
            school_crawler_service._school_backfill_payload(SimpleNamespace(homepage_url=None)),
            {},
        )

    def test_school_row_select_excludes_crawl_columns(self):
        """select('*') 는 죽은 컬럼까지 긁어와 우연한 폴백을 만든다. 명시 목록으로 좁힌다."""
        cols = school_crawler_service._SCHOOL_ROW_COLUMNS
        self.assertNotIn("crawl_", cols)
        for expected in ("id", "name", "homepage_url", "neis_office_code", "neis_school_code"):
            self.assertIn(expected, cols)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_school_crawler_state_write -v
```

Expected: FAIL — `AttributeError: module 'app.services.school_crawler_service' has no attribute '_school_backfill_payload'` (4건 전부)

- [ ] **Step 3: 최소 구현 — payload 를 순수 함수로 뽑고 crawl_* 를 뺀다**

`backend/app/services/school_crawler_service.py` 의 `_save_school_discovery_result` **바로 위**에 추가:

```python
_SCHOOL_ROW_COLUMNS = "id,name,address,homepage_url,neis_office_code,neis_school_code"


def _school_backfill_payload(result: SchoolBoardDiscoveryResult) -> dict[str, Any]:
    """schools 에 되돌려 쓰는 값. 크롤 상태의 정본은 school_crawl_state 다(0013).

    homepage_url 만 남긴다 — 이 컬럼은 schools 에만 있고(0013 에 미포함),
    _context_from_school_row 가 크롤 대상 URL 을 얻는 유일한 경로다.
    """
    payload: dict[str, Any] = {}
    if result.homepage_url:
        payload["homepage_url"] = result.homepage_url
    return payload
```

그리고 `_save_school_discovery_result` 의 `try` 블록 안 `school_payload` 구성부(624~639행)를 아래로 바꾼다:

```python
    try:
        supabase = get_supabase_client()
        school_payload = _school_backfill_payload(result)
        # 빈 dict 로 update 를 치면 PostgREST 가 400 을 낸다.
        if school_payload:
            supabase.table("schools").update(school_payload).eq(
                "id",
                result.school_id,
            ).execute()
        supabase.table("school_crawl_state").upsert(
            state_payload,
            on_conflict="school_id",
        ).execute()
```

- [ ] **Step 4: `select("*")` 를 명시 목록으로 좁힌다**

`_fetch_school_row()` 의 331행:

```python
    result = (
        supabase.table("schools")
        .select(_SCHOOL_ROW_COLUMNS)
        .eq("id", school_id)
        .limit(1)
        .execute()
    )
```

`select("*")` 는 죽은 컬럼까지 긁어와 **우연한 폴백**을 만든다 — 상태 행이 없는 학교에서 `schools` 의 낡은 crawl_* 값이 살아남는다. 실측 결과 그런 학교가 정확히 1개(쇼케이스) 있었고 Task 8 이 지웠다. 컬럼 목록을 좁히면 컬럼 삭제 후에도 이 코드가 그대로 돈다.

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_school_crawler_state_write -v
PYTHONPATH=backend python -m unittest discover backend/tests
```

Expected: 새 테스트 4건 PASS, 전체 스위트도 전부 통과

- [ ] **Step 6: `schools.crawl_*` 쓰기가 저장소에서 0건인지 확인한다**

```bash
grep -rn "crawl_status\|crawl_board_url\|crawl_board_kind\|crawl_error_message\|crawl_result\|crawl_last_checked_at" \
  --include=*.ts --include=*.tsx --include=*.py --include=*.cjs . \
  | grep -v node_modules | grep -v .claude/worktrees | grep -v "supabase/migrations" \
  | grep -iv "school_crawl_state\|schoolCrawlState\|SchoolCrawlerState"
```

Expected: `types/database.generated.ts` 의 `schools` 선언(Task 10 이후 사라짐)과 `lib/school-crawl-state.ts` 의 `school_crawl_state` 매핑 외에는 없다. `.table("schools")` 나 `.from('schools')` 와 함께 나오는 줄이 **하나도 없어야** 한다.

- [ ] **Step 7: 커밋**

```bash
git add backend/app/services/school_crawler_service.py backend/tests/test_school_crawler_state_write.py
git commit -m "refactor(crawler): schools 로의 크롤 상태 이중 쓰기 제거

0013 이 school_crawl_state 를 만들고 백필까지 했는데, _save_school_discovery_result
가 같은 값을 schools 에도 계속 쓰고 있었다. 두 문장이 트랜잭션으로 묶여 있지도 않아
앞이 성공하고 뒤가 실패하면 두 테이블이 갈린다.

schools UPDATE 를 통째로 없애지는 않는다 — homepage_url 은 schools 에만 있고
크롤 대상 URL 의 유일한 소스다. crawl_* 6키만 빼고, payload 가 비면 update 호출
자체를 건너뛴다(빈 dict update 는 400).

_fetch_school_row 의 select('*') 도 명시 컬럼 목록으로 좁힌다. select('*') 는
죽은 컬럼까지 긁어와 상태 행이 없는 학교에서 우연한 폴백을 만든다.

컬럼 삭제는 다음 배포다. 이 커밋만으로는 DB 가 그대로라 즉시 원복할 수 있다."
```

- [ ] **Step 8: 실제 크롤 1회로 확인한다 (Task 10 의 전제)**

배포 후 학교 하나에 크롤을 트리거하고:

```bash
python - <<'PY'
import json, os, urllib.request
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
def get(p):
    r = urllib.request.Request(u + '/rest/v1/' + p)
    r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode() or '[]')
for s in get('schools?select=id,name,crawl_status,crawl_last_checked_at,homepage_url'):
    st = get(f"school_crawl_state?school_id=eq.{s['id']}&select=crawl_status,crawl_last_checked_at")
    print(f"{s['name'][:12]:14s} schools={s['crawl_last_checked_at']}  state={st[0]['crawl_last_checked_at'] if st else None}")
PY
```

Expected: 크롤을 돌린 학교의 **`state` 쪽 시각만 갱신**되고 `schools` 쪽은 그대로다. 둘 다 갱신되면 이중 쓰기가 안 끊긴 것이다 — **중단하고 Step 3 으로 돌아간다.**

`homepage_url` 이 없는 학교로도 한 번 돌려 `.update({})` 오류가 안 나는지 본다.

---

## Task 10: `schools.crawl_*` 삭제 (D6-b) 🔴

**Files:**
- Create: `supabase/migrations/0048_drop_schools_crawl_columns.sql`
- Regenerate: `types/database.generated.ts`

**Interfaces:**
- Consumes: Task 9 Step 8 의 크롤 성공 확인
- Produces: `schools` 에서 crawl_* 6컬럼 + 죽은 인덱스 2개 + CHECK 제약 1개 소멸. `schema-migration-plan.md` Phase 4 완료.

- [ ] **Step 1: 마이그레이션을 쓴다**

`supabase/migrations/0048_drop_schools_crawl_columns.sql`:

```sql
-- schema-migration-plan.md Phase 4 의 마지막 배포.
-- 0013 이 school_crawl_state 를 만들고 8개 학교를 전부 백필했으나 원본 컬럼을
-- 지우지 않아 두 테이블이 공존했고, 0033 이 board_watermarks 를 새 테이블에만
-- 추가하면서 스키마가 이미 갈라졌다.
--
-- 읽기는 진작 이전됐다(lib/school-crawl-state.ts, scheduled_crawler_service.py).
-- 쓰기는 직전 배포가 끊었다.
--
-- homepage_url 은 지우지 않는다. schools 에만 있고 크롤 대상 URL 의 유일한 소스다.

-- 값을 잃기 전에, 정본 테이블에 상태 행이 없는 학교가 없는지 확인한다.
do $$
declare
  orphan integer;
begin
  select count(*) into orphan
  from public.schools s
  left join public.school_crawl_state st on st.school_id = s.id
  where st.school_id is null;

  if orphan > 0 then
    raise exception 'school_crawl_state 행이 없는 학교가 %개 있습니다 — 삭제를 중단합니다', orphan;
  end if;
end $$;

drop index if exists public.schools_crawl_status_idx;
drop index if exists public.schools_crawl_last_checked_at_idx;

-- schools_crawl_board_kind_check(0002:19-21) 는 컬럼 drop 시 자동으로 사라진다.
alter table public.schools
  drop column if exists crawl_status,
  drop column if exists crawl_error_message,
  drop column if exists crawl_result,
  drop column if exists crawl_board_url,
  drop column if exists crawl_board_kind,
  drop column if exists crawl_last_checked_at;
```

- [ ] **Step 2: 가드가 통과할지 미리 확인한다**

```bash
python - <<'PY'
import json, os, urllib.request
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
def get(p):
    r = urllib.request.Request(u + '/rest/v1/' + p)
    r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode() or '[]')
sids = {s['id'] for s in get('schools?select=id')}
have = {s['school_id'] for s in get('school_crawl_state?select=school_id')}
print('schools:', len(sids), '| crawl_state:', len(have), '| 상태 행 없는 학교:', sorted(s[:8] for s in sids - have))
PY
```

Expected: `상태 행 없는 학교: []`. 비어 있지 않으면 **중단하고 보고할 것** — 쇼케이스 학교가 Task 8 에서 안 지워졌거나 새로 생긴 것이다.

- [ ] **Step 3: 번호 검사와 dry-run**

```bash
python scripts/check_migration_numbers.py
supabase db push --dry-run
```

Expected: `번호 중복 없음` + `0048_drop_schools_crawl_columns.sql`

- [ ] **Step 4: 커밋**

```bash
git add supabase/migrations/0048_drop_schools_crawl_columns.sql
git commit -m "feat(db): schools 의 크롤 상태 컬럼 6개와 죽은 인덱스 2개 삭제

schema-migration-plan.md Phase 4 의 마지막 배포다. 0013 이 school_crawl_state 를
만들고 백필까지 했지만 원본 컬럼을 지우지 않아 두 테이블이 석 달을 공존했고,
0033 이 board_watermarks 를 새 테이블에만 추가하면서 스키마가 이미 갈라졌다.

읽기는 진작 이전됐고 쓰기는 직전 배포가 끊었다.
schools_crawl_board_kind_check 는 컬럼과 함께 자동으로 사라진다.

homepage_url 은 지우지 않는다 — schools 에만 있고 크롤 대상 URL 의 유일한 소스다.

값을 잃기 전에 school_crawl_state 행이 없는 학교가 없는지 확인하는 가드를 둔다.
되돌리려면 school_crawl_state 에서 역백필하는 복구 마이그레이션이 필요하다."
```

- [ ] **Step 5: 머지 후 타입을 재생성한다**

```bash
npm run gen:types
git diff --stat types/database.generated.ts
npm run typecheck && npm run build
```

Expected: `schools` 에서 crawl_* 6줄 × 3블록(Row/Insert/Update)이 사라진 diff. 타입체크·빌드 성공.

```bash
git add types/database.generated.ts
git commit -m "chore(types): schools.crawl_* 삭제 반영 (gen:types 재실행)"
```

- [ ] **Step 6: 사후 검증**

```sql
select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'schools'
order by ordinal_position;
```

Expected: crawl_* 6개 없음, **`homepage_url` 있음**.

그리고 **온보딩에서 새 학교를 하나 등록해 최초 크롤이 정상인지** 확인한다.

---

## Task 11: `profiles` 쓰기 경로 정리 (D7-a)

`profiles.email` / `display_name` 을 읽는 유일한 목적이 **「자기가 방금 쓴 값을 다시 읽어 다시 쓰기」** 다. `avatar_url` 은 읽기·쓰기 0건이다. UI 에서 프로필 이름을 렌더하는 경로도 0건이다 (사용자 이름은 `children.name` 으로 표시된다).

> ⚠️ **`native_language` 는 지우지 않는다.** 실측 결과 10개 프로필 중 **7개가 `locale ≠ native_language`** 다. `locale` 만 갱신 경로가 있고(`app/api/locale/route.ts`), 백엔드는 **둘의 합집합**을 번역 대상 locale 로 쓴다(`_school_translation_locales`).

**Files:**
- Modify: `app/onboarding/actions.ts`, `app/api/auth/dev-login/route.ts`, `app/(auth)/login/LoginButtons.tsx`

**Interfaces:**
- Consumes: 없음
- Produces: `profiles` 의 `email`/`display_name`/`avatar_url` 을 읽거나 쓰는 코드가 0건이 된다. dev-login 요청 본문에서 `profileEmail`/`displayName` 이 사라진다.

- [ ] **Step 1: 사전 확인 — 지금 어디서 쓰는가**

```bash
grep -rn "display_name\|avatar_url\|profileEmail" --include=*.ts --include=*.tsx . \
  | grep -v node_modules | grep -v .claude/worktrees | grep -v types/database
grep -rn "from('profiles')\|table(\"profiles\")" --include=*.ts --include=*.tsx --include=*.py . \
  | grep -v node_modules | grep -v .claude/worktrees
```

Expected: `app/onboarding/actions.ts`, `app/api/auth/dev-login/route.ts`, `app/(auth)/login/LoginButtons.tsx` 세 파일. 백엔드의 `profiles` 접근은 `content_extraction_service.py` 의 `_school_translation_locales` 한 곳뿐이고 **`locale,native_language` 만** 읽는다.

- [ ] **Step 2: 온보딩의 프로필 upsert 를 줄인다**

`app/onboarding/actions.ts` — `existingProfile` 조회(60~64행)와 dev-login 이메일 보존 분기(66~69행)를 **삭제**하고, upsert 를 아래로 바꾼다:

```typescript
  // 사용자 식별의 정본은 auth.users 다. profiles 에는 언어 설정만 둔다.
  // locale = 지금 보고 싶은 언어(설정에서 바뀐다), native_language = 온보딩 때 고른
  // 모국어(갱신 경로 없음, 온보딩 1회 고정). 백엔드는 둘의 합집합을 번역 대상으로 쓴다.
  const { error: profileError } = await supabase.from('profiles').upsert(
    {
      id: user.id,
      locale: input.locale,
      native_language: input.locale,
    },
    { onConflict: 'id' }
  )
```

- [ ] **Step 3: dev-login 라우트를 줄인다**

`app/api/auth/dev-login/route.ts`:

- 20~21행의 `profileEmail` / `displayName` 파싱 두 줄을 삭제한다.
- 61~65행의 select 를 `'locale,native_language'` 로 좁힌다.
- `nextProfile` 에서 `email` / `display_name` 두 줄을 삭제한다:

```typescript
    const nextProfile = {
      id: user.id,
      locale: isValidLocale(profile?.locale) ? profile.locale : 'ko',
      native_language: isValidLocale(profile?.native_language) ? profile.native_language : 'ko',
    }
```

- [ ] **Step 4: 로그인 버튼의 요청 본문을 줄인다**

`app/(auth)/login/LoginButtons.tsx` 의 `handleDevLogin` 요청 본문에서 두 줄을 삭제한다:

```typescript
      body: JSON.stringify({
        next: safeNext,
        resetOnboarding: true,
      }),
```

`devEmail` / `devName` 이 다른 곳에서 안 쓰이면 그 상태 정의도 함께 지운다. (`resetOnboarding` 은 남긴다 — `children` 삭제 기능이라 이 사업과 무관하다.)

- [ ] **Step 5: 잔존 참조와 빌드를 확인한다**

```bash
grep -rn "display_name\|avatar_url\|profileEmail" --include=*.ts --include=*.tsx . \
  | grep -v node_modules | grep -v .claude/worktrees | grep -v types/database
echo "종료코드: $? (1 이면 없음 = 정상)"
npm run typecheck && npm run build
```

Expected: 첫 명령 출력 없음(종료코드 1), 타입체크·빌드 성공. `email` 은 `user.email`(auth) 참조가 남아 있을 수 있으므로 `profiles` 와 함께 나오는 줄만 없으면 된다.

- [ ] **Step 6: 커밋**

```bash
git add app/onboarding/actions.ts app/api/auth/dev-login/route.ts "app/(auth)/login/LoginButtons.tsx"
git commit -m "refactor(profiles): email·display_name 쓰기 경로 제거

두 컬럼을 읽는 유일한 목적이 '자기가 방금 쓴 값을 다시 읽어 다시 쓰기' 였다.
사용자 식별의 정본은 auth.users 이고, UI 에서 프로필 이름을 렌더하는 경로는
0건이다 — 사용자 이름은 children.name 으로 표시된다.
운영 실측으로도 display_name 은 10개 프로필 전부 null 이다.

dev-login 요청 본문의 profileEmail/displayName 도 함께 뺀다. 저장할 곳이 없다.

native_language 는 남긴다. 10개 프로필 중 7개가 locale 과 값이 다르고,
백엔드가 둘의 합집합을 번역 대상 locale 로 쓴다.
locale = 지금 보고 싶은 언어, native_language = 온보딩 때 고른 모국어다.

컬럼 삭제는 다음 배포다."
```

- [ ] **Step 7: 온보딩을 실제로 완주한다**

배포 후 새 계정으로 로그인 → 온보딩 완주 → 홈. `profiles` 행이 생기고 `locale`·`native_language` 가 기록되는지 확인한다.

---

## Task 12: `profiles` 죽은 컬럼 삭제 (D7-b) 🔴

**Files:**
- Create: `supabase/migrations/0049_drop_profiles_dead_columns.sql`
- Regenerate: `types/database.generated.ts`

**Interfaces:**
- Consumes: Task 11 의 온보딩 정상 확인
- Produces: `profiles` 가 `id / locale / native_language / created_at / updated_at` 5컬럼이 된다. `schema-migration-plan.md` Phase 3 완료.

- [ ] **Step 1: 삭제 전 값이 정말 없는지 센다**

```bash
python - <<'PY'
import json, os, urllib.request
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
def n(p):
    r = urllib.request.Request(u + '/rest/v1/' + p)
    r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
    return len(json.loads(urllib.request.urlopen(r, timeout=60).read().decode() or '[]'))
total = n('profiles?select=id')
print('profiles:', total)
print('display_name non-null:', n('profiles?display_name=not.is.null&select=id'))
print('avatar_url   non-null:', n('profiles?avatar_url=not.is.null&select=id'))
print('email        non-null:', n('profiles?email=not.is.null&select=id'), '(auth.users.email 이 canonical)')
PY
```

Expected: `display_name non-null: 0`, `avatar_url non-null: 0`, `email non-null: 10`.

`email` 은 값이 있지만 **`auth.users.email` 에서 조회 가능**하므로 기능 손실은 없다. `display_name`/`avatar_url` 이 0 이 아니면 그 값이 어디서 왔는지 확인하고 **보고할 것.**

- [ ] **Step 2: 마이그레이션을 쓴다**

`supabase/migrations/0049_drop_profiles_dead_columns.sql`:

```sql
-- schema-migration-plan.md Phase 3. 계획 수립 후 한 번도 실행되지 않았다 —
-- profiles 를 건드린 마이그레이션은 0001(생성)과 0012(role drop) 둘뿐이었다.
--
-- avatar_url  : 저장소 전체에서 읽기·쓰기 0건. 운영 10행 전부 null.
-- display_name: UI 렌더 경로 0건. 운영 10행 전부 null.
--               사용자 이름은 children.name 으로 표시된다.
-- email       : canonical 은 auth.users.email 이다. 유일한 소비자가
--               '자기가 쓴 걸 다시 읽어 다시 쓰는' 루프였고, 직전 배포가 끊었다.
--
-- locale / native_language 는 남긴다. 10행 중 7행이 서로 다른 값이고
-- 백엔드가 둘의 합집합을 번역 대상 locale 로 쓴다.
--
-- RLS 정책 3개(0001:130-141)는 전부 auth.uid() = id 만 보므로 영향이 없다.

alter table public.profiles
  drop column if exists email,
  drop column if exists display_name,
  drop column if exists avatar_url;

comment on column public.profiles.locale is
  '지금 보고 싶은 언어. 설정에서 갱신된다(app/api/locale/route.ts).';
comment on column public.profiles.native_language is
  '온보딩 때 고른 모국어. 갱신 경로가 없는 1회 고정 값이다. 번역 대상 locale 은 이 둘의 합집합이다.';
```

- [ ] **Step 3: 번호 검사와 dry-run**

```bash
python scripts/check_migration_numbers.py
supabase db push --dry-run
```

Expected: `번호 중복 없음` + `0049_drop_profiles_dead_columns.sql`

- [ ] **Step 4: 커밋**

```bash
git add supabase/migrations/0049_drop_profiles_dead_columns.sql
git commit -m "feat(db): profiles 의 email·display_name·avatar_url 삭제

schema-migration-plan.md Phase 3 이다. 계획 수립 후 한 번도 실행되지 않았다 —
profiles 를 건드린 마이그레이션은 0001(생성)과 0012(role drop) 둘뿐이었다.

avatar_url 과 display_name 은 읽기·쓰기 0건이고 운영 10행이 전부 null 이다.
email 의 canonical 은 auth.users.email 이고, 유일한 소비자였던
'자기가 쓴 걸 다시 읽어 다시 쓰는' 루프는 직전 배포가 끊었다.

locale 과 native_language 는 남기고 의도를 컬럼 주석으로 명문화한다.
10행 중 7행이 서로 다른 값이고 백엔드가 둘의 합집합을 번역 대상으로 쓴다.

RLS 정책 3개는 전부 auth.uid() = id 만 보므로 영향이 없다."
```

- [ ] **Step 5: 머지 후 타입 재생성과 회귀**

```bash
npm run gen:types
npm run typecheck && npm run build
git add types/database.generated.ts
git commit -m "chore(types): profiles 죽은 컬럼 삭제 반영 (gen:types 재실행)"
```

그리고 **로그인 → 온보딩 → 홈 → 공지 상세**를 실제로 밟아 전 화면이 정상인지 확인한다.

---

## Task 13: 죽은 컬럼·상태 제거 (D8) 🔴

**Files:**
- Create: `supabase/migrations/0050_drop_dead_columns_and_narrow_checks.sql`
- Modify: `backend/app/services/notice_service.py`, `lib/schedule-backfill.ts`

**Interfaces:**
- Consumes: Task 7 (`lib/demo-school.ts` 삭제 — `school_events.source_language` 를 읽는 마지막 TS 경로)
- Produces: `school_events` 에서 `source_language` 소멸. `notice_ai_translations.validation_status` 의 값 도메인이 코드·타입과 일치(`passed`/`failed`).

- [ ] **Step 1: 사전 카운트 — 두 가지를 잰다**

```bash
python - <<'PY'
import json, os, urllib.request, collections
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
def get(p):
    r = urllib.request.Request(u + '/rest/v1/' + p)
    r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode() or '[]')
print('school_events.source_language 분포:',
      dict(collections.Counter(str(e['source_language']) for e in get('school_events?select=source_language&limit=1000'))))
print('validation_status 분포:',
      dict(collections.Counter(str(t['validation_status']) for t in get('notice_ai_translations?select=validation_status&limit=1000'))))
print('notice_cards type=schedule:', len(get('notice_cards?type=eq.schedule&select=id')))
PY
```

Expected (2026-08-27 실측): `source_language` 는 `{'ko': 68}`, `validation_status` 는 `{'passed': 155}`, `type=schedule` 은 `0`.

`validation_status` 에 `human_review_required` 가 하나라도 있으면 **중단하고 사용자에게 묻는다** (`failed` 로 이행할지). `type=schedule` 이 0 이 아니면 §13.1-3 의 데드코드 판단이 틀린 것이므로 **`lib/schedule-backfill.ts` 의 schedule 카드 읽기 경로는 건드리지 않는다.**

- [ ] **Step 2: 코드에서 `source_language` 쓰기를 뺀다**

`backend/app/services/notice_service.py` — `school_events` upsert rows 에서 한 줄 삭제:

```python
                "location": location,
                "description": description,
            }
```

(`"source_language": "ko",` 줄을 지운다.)

`lib/schedule-backfill.ts` — 같은 이유로 한 줄 삭제:

```typescript
        location: optionalString(notice.event_location) ?? scheduleCardLocation,
        description,
      })
```

(`source_language: 'ko',` 줄을 지운다.)

- [ ] **Step 3: 백엔드 테스트가 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend python -m unittest discover backend/tests
npm run typecheck
```

Expected: 전부 통과. `source_language` 를 기대하는 단정이 있으면 그 테스트에서도 지운다.

- [ ] **Step 4: 마이그레이션을 쓴다**

`supabase/migrations/0050_drop_dead_columns_and_narrow_checks.sql`:

```sql
-- (1) school_events.source_language
--     모든 쓰기가 'ko' 하드코딩이었고(백엔드 upsert, 프론트 백필, 0017:50 의 백필 SQL)
--     읽는 곳은 데모 시드뿐이었다. 그 파일은 이미 삭제됐다.
--     운영 68행이 전부 'ko' — 정보량이 0 인 컬럼이다.
do $$
declare
  distinct_langs integer;
begin
  select count(distinct source_language) into distinct_langs from public.school_events;
  if distinct_langs > 1 then
    raise exception 'school_events.source_language 값이 %종류입니다 — 정보가 있으므로 중단합니다', distinct_langs;
  end if;
end $$;

alter table public.school_events drop column if exists source_language;

-- (2) notice_ai_translations.validation_status 의 값 도메인 축소.
--     컬럼은 남긴다 — 번역 이력은 보존한다는 사용자 결정(2026-08-27).
--     0005:14-15 는 세 값을 허용하고 기본값이 'human_review_required' 인데,
--     코드는 'passed'/'failed' 둘만 쓰고(notice_service, orchestrator, prompts)
--     TS 유니언도 둘뿐이며 운영 155행이 전부 'passed' 다.
--     기본값도 어긋나 있었다 — 코드가 명시하지 않으면 아무도 안 쓰는 값이 들어갔다.
do $$
declare
  stale integer;
begin
  select count(*) into stale
  from public.notice_ai_translations
  where validation_status not in ('passed', 'failed');

  if stale > 0 then
    raise exception 'validation_status 가 passed/failed 가 아닌 행이 %개 있습니다 — 중단합니다', stale;
  end if;
end $$;

alter table public.notice_ai_translations
  drop constraint if exists notice_ai_translations_validation_status_check;

-- 명시하지 않은 삽입은 실패로 본다(fail closed).
alter table public.notice_ai_translations
  alter column validation_status set default 'failed';

alter table public.notice_ai_translations
  add constraint notice_ai_translations_validation_status_check
  check (validation_status in ('passed', 'failed'));
```

- [ ] **Step 5: 번호 검사와 dry-run**

```bash
python scripts/check_migration_numbers.py
supabase db push --dry-run
```

Expected: `번호 중복 없음` + `0050_drop_dead_columns_and_narrow_checks.sql`

- [ ] **Step 6: 커밋**

```bash
git add supabase/migrations/0050_drop_dead_columns_and_narrow_checks.sql \
        backend/app/services/notice_service.py lib/schedule-backfill.ts
git commit -m "feat(db): school_events.source_language 삭제, validation_status 값 도메인 축소

source_language 는 모든 쓰기가 'ko' 하드코딩이었고 읽는 곳은 방금 삭제한
데모 시드뿐이었다. 운영 68행이 전부 'ko' 라 정보량이 0 이다.
값이 두 종류 이상이면 중단하는 가드를 둔다.

validation_status 는 컬럼을 남긴다 — 번역 이력 보존 결정. 값 도메인만 조인다.
0005 는 세 값을 허용하고 기본값이 human_review_required 였는데, 코드는
passed/failed 둘만 쓰고 TS 유니언도 둘뿐이며 운영 155행이 전부 passed 다.
기본값은 fail closed 로 'failed' 로 바꾼다.

notice_cards 의 type='schedule' 은 운영 0행으로 데드코드가 확인됐지만,
읽는 쪽(lib/schedule-backfill.ts)은 이번에 건드리지 않는다 — 컬럼 삭제가 아니라
분기 삭제라 성격이 다르고 이 사업의 범위 밖이다."
```

- [ ] **Step 7: 머지 후 타입 재생성과 회귀**

```bash
npm run gen:types
npm run typecheck && npm run build
git add types/database.generated.ts
git commit -m "chore(types): school_events.source_language 삭제 반영 (gen:types 재실행)"
```

**캘린더 화면**과 **공지 번역 1건**을 실제로 돌려 정상인지 확인한다.

---

## Task 14: 타입·불변식 교정 (D9) 🔴

**Files:**
- Create: `supabase/migrations/0051_tighten_types_and_invariants.sql`

**Interfaces:**
- Consumes: Task 8 (데모 학교 제거로 `schools` 가 6행), Task 3 (`children_user_school_id_idx` 를 이미 비부분으로 교체)
- Produces: `schools.neis_*` · `children.school_id` NOT NULL. `school_events.event_kinds` 가 `text[] + CHECK`.

**이 Task 에서 하지 않는 것 (실측 근거):**

| 스펙 항목 | 실측 | 판단 |
|---|---|---|
| §13.2-1 `meals.calories` → `numeric` | **102/102 행이 `"905.1 Kcal"` 꼴** — 캐스트 불가 | **제외.** 새 컬럼 `calories_kcal` 를 만들면 NEIS 수집기와 급식 화면까지 손봐야 해서 성격이 다르다. §19 위험표의 「0 이 아니면 그 항목만 별건 분리」 규정을 적용해 후속으로 넘긴다 |
| §13.2-5 `school_events` UNIQUE 에 `end_date` 추가 | 중복 `(notice_id, event_date)` **0건** (end_date 보유 5행 포함) | **제외.** 지금 막히는 케이스가 없다. 생기면 그때 확장한다 |
| §13.2-6 `meals` ↔ `schools` FK | `meals` 에 `schools` 에 없는 코드 조합 2종(`J10/7679329`, `N10/8291005`) 존재 | **제외.** 스펙 §2 가 이미 비목표로 못박았다. NEIS 코드 단위 전역 공유 캐시 모델이 실제로 그렇게 쓰이고 있다는 증거다 |

- [ ] **Step 1: 사전 카운트 — 세 개가 전부 0 이어야 한다**

```bash
python - <<'PY'
import json, os, urllib.request, collections
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
def get(p):
    r = urllib.request.Request(u + '/rest/v1/' + p)
    r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode() or '[]')
print('schools NEIS 코드 결측:',
      len(get('schools?neis_office_code=is.null&select=id')) + len(get('schools?neis_school_code=is.null&select=id')))
print('children school_id 결측:', len(get('children?school_id=is.null&select=id')))
ev = get('school_events?select=notice_id,event_date,event_kinds&limit=1000')
print('event_kinds 분포:', dict(collections.Counter(json.dumps(e['event_kinds']) for e in ev)))
dup = [kk for kk, v in collections.Counter((e['notice_id'], e['event_date']) for e in ev).items() if v > 1]
print('(notice_id, event_date) 중복:', len(dup))
PY
```

Expected: 앞의 두 값이 **0**, `event_kinds` 분포에 `["event"]` / `["deadline"]` / `["deadline","event"]` 세 종류, 중복 0.

**앞 두 값 중 하나라도 0 이 아니면 그 항목만 빼고 진행한다** (마이그레이션에서 해당 `set not null` 을 삭제).

- [ ] **Step 2: 마이그레이션을 쓴다**

`supabase/migrations/0051_tighten_types_and_invariants.sql`:

```sql
-- 코드가 이미 지키고 있는 불변식을 스키마에 적는다.

-- (1) schools 의 UNIQUE 가 사실상 작동하지 않았다.
--     0001:23-27 이 (neis_office_code, neis_school_code) 에 unique 를 걸었지만
--     둘 다 nullable 이고 Postgres 기본이 NULLS DISTINCT 라, 코드가 비어 있는
--     학교는 무한히 중복될 수 있었다.
do $$
declare
  n integer;
begin
  select count(*) into n from public.schools
  where neis_office_code is null or neis_school_code is null;
  if n > 0 then
    raise exception 'NEIS 코드가 비어 있는 학교가 %개 있습니다 — 중단합니다', n;
  end if;
end $$;

alter table public.schools
  alter column neis_office_code set not null,
  alter column neis_school_code set not null;

-- (2) children.school_id 는 0001:33 이후 계속 nullable 이었지만,
--     0016:1-21 이 'school_id 없는 자녀 0건' 을 강제한 뒤
--     0016:26-30 이 FK 를 ON DELETE RESTRICT 로 바꿨다. 불변식과 스키마가 어긋난다.
do $$
declare
  n integer;
begin
  select count(*) into n from public.children where school_id is null;
  if n > 0 then
    raise exception 'school_id 가 비어 있는 자녀가 %개 있습니다 — 중단합니다', n;
  end if;
end $$;

alter table public.children
  alter column school_id set not null;

-- children_user_school_id_idx 는 0045 가 이미 부분 조건을 떼고 재생성했다.
-- 여기서 다시 건드리지 않는다.

-- (3) school_events.event_kinds 를 jsonb 에서 text[] + CHECK 로 바꾼다.
--     0028(2026-06-09)은 jsonb 에 값 도메인 CHECK 없이 만들었고,
--     닷새 뒤 0034(2026-06-14)는 같은 성격의 children.dietary_restrictions 를
--     text[] + <@ CHECK 로 만들었다. 같은 저장소의 정반대 해법이고 0034 가 옳다.
--
--     값은 두 가지가 아니다 — 운영에 ["event"] 43, ["deadline"] 12,
--     ["deadline","event"] 13 이 있다. 원소 단위로 일반 변환한다.
alter table public.school_events
  add column if not exists event_kinds_text text[];

update public.school_events
set event_kinds_text = coalesce(
  (
    select array_agg(elem order by ord)
    from jsonb_array_elements_text(event_kinds) with ordinality as t(elem, ord)
  ),
  array['event']::text[]
)
where event_kinds_text is null;

do $$
declare
  n integer;
begin
  select count(*) into n from public.school_events
  where event_kinds_text is null
     or not (event_kinds_text <@ array['event', 'deadline']::text[]);
  if n > 0 then
    raise exception 'event_kinds 변환 결과가 도메인 밖인 행이 %개 있습니다 — 중단합니다', n;
  end if;
end $$;

alter table public.school_events drop column event_kinds;
alter table public.school_events rename column event_kinds_text to event_kinds;

alter table public.school_events
  alter column event_kinds set not null,
  alter column event_kinds set default array['event']::text[];

alter table public.school_events
  add constraint school_events_event_kinds_check
  check (event_kinds <@ array['event', 'deadline']::text[]);
```

- [ ] **Step 3: 번호 검사와 dry-run**

```bash
python scripts/check_migration_numbers.py
supabase db push --dry-run
```

Expected: `번호 중복 없음` + `0051_tighten_types_and_invariants.sql`

- [ ] **Step 4: 커밋**

```bash
git add supabase/migrations/0051_tighten_types_and_invariants.sql
git commit -m "feat(db): NOT NULL 불변식 확정 + event_kinds 를 text[] + CHECK 로

schools 의 UNIQUE 가 사실상 작동하지 않았다. (neis_office_code, neis_school_code)
둘 다 nullable 인데 Postgres 기본이 NULLS DISTINCT 라 코드 없는 학교는 무한히
중복될 수 있었다. 운영 결측 0건을 확인하고 NOT NULL 을 준다.

children.school_id 는 0016 이 '결측 0건' 을 강제하고 FK 를 ON DELETE RESTRICT 로
바꿨는데도 컬럼은 nullable 로 남아 있었다. 불변식을 스키마에 적는다.

event_kinds 는 0028 이 jsonb 에 값 도메인 CHECK 없이 만들었고, 닷새 뒤 0034 가
같은 성격의 dietary_restrictions 를 text[] + <@ CHECK 로 만들었다. 0034 가 옳다.
값은 두 가지가 아니라 세 가지다(['deadline','event'] 조합이 13행) — 2분기 CASE 가
아니라 jsonb_array_elements_text 로 원소 단위 변환한다.

meals.calories 캐스트는 제외한다. 운영 102행이 전부 '905.1 Kcal' 꼴이라 캐스트가
불가능하고, 새 컬럼을 만들면 NEIS 수집기와 급식 화면까지 손봐야 해서 성격이 다르다.
school_events UNIQUE 확장도 제외한다 — 지금 막히는 케이스가 0건이다."
```

- [ ] **Step 5: 머지 후 타입 재생성과 회귀**

```bash
npm run gen:types
git diff types/database.generated.ts | head -40
npm run typecheck && npm run build
```

Expected: `event_kinds` 가 `Json` → `string[]` 로 바뀐 diff. `lib/schedule-backfill.ts` 의 `satisfies Json` 이 걸리면 `entry.eventKinds` 그대로 두고 `satisfies Json` 을 제거한다 (PostgREST 가 JSON 배열을 text[] 로 받는다).

```bash
git add types/database.generated.ts lib/schedule-backfill.ts
git commit -m "chore(types): event_kinds text[] 전환 반영 (gen:types 재실행)"
```

**캘린더 화면**을 열어 이벤트/마감 구분이 그대로인지 확인한다.

---

## Task 15: `getSchoolSummary` 소유권 검증 (D10)

`lib/server-cache.ts` 의 service_role 사용 5곳 중 **소유권 검증이 아예 없는 곳은 `getSchoolSummary` 하나**다. `schoolId` 만 알면 아무 학교의 크롤 상태를 읽을 수 있다.

> 나머지 4곳은 `unstable_cache` 콜백 안이라 쿠키를 못 읽고, 따라서 세션이 붙은 anon 클라이언트를 만들 수 없다 — **아키텍처 제약**이다. 그래서 코드가 RLS 가 할 일을 손으로 재현한다(`userId` 를 캐시 키에 넣고 `.eq('user_id', userId)`). 이걸 고치려면 홈·캘린더·급식의 렌더 아키텍처를 다시 짜야 하고, 그건 DB 정리가 아니다. **이 사업 범위 밖이다.**

**Files:**
- Modify: `lib/server-cache.ts` (`getSchoolSummary`)
- Modify: `app/(app)/page.tsx` (호출부)

**Interfaces:**
- Consumes: 사업 A 가 `TEST_ENTRY_BYPASS` 조건부 우회 8곳을 없앤 상태
- Produces: `getSchoolSummary(userId, schoolId)`. 캐시 키가 `['school-summary', userId, schoolId]` 로 바뀐다.

- [ ] **Step 1: 호출부를 전부 찾는다**

```bash
grep -rn "getSchoolSummary" --include=*.ts --include=*.tsx . | grep -v node_modules | grep -v .claude/worktrees
```

Expected: 정의 1곳(`lib/server-cache.ts`) + 호출 1곳(`app/(app)/page.tsx`) + import 1줄.

- [ ] **Step 2: 저장소에 이미 있는 올바른 패턴을 확인한다**

```bash
sed -n '20,55p' "app/api/schools/[schoolId]/crawl/route.ts"
```

Expected: anon 클라이언트 → 인증 확인(401) → `children` 으로 소유권 검증 → 거부(403 `school_not_allowed`) → **그 후** service_role 승격. 이 순서를 그대로 옮긴다.

- [ ] **Step 3: `getSchoolSummary` 에 소유권 검증을 넣는다**

`lib/server-cache.ts`:

```typescript
/** 홈 상단의 '공지 수집 중' 배너용 크롤 상태.
 *
 *  unstable_cache 콜백은 요청 스코프 밖에서 돌아 쿠키를 못 읽는다. 그래서 세션이
 *  붙은 anon 클라이언트를 만들 수 없고, RLS 대신 코드가 소유권을 확인한다.
 *  userId 는 반드시 호출자가 세션에서 꺼낸 값이어야 한다 —
 *  이 값을 잘못 넘기면 크로스테넌트 유출이다. */
export async function getSchoolSummary(
  userId: string,
  schoolId: string,
): Promise<CachedSchoolSummary | null> {
  return unstable_cache(
    async () => {
      const serviceClient = createSupabaseServiceClient()

      const { data: owned } = await serviceClient
        .from('children')
        .select('id')
        .eq('user_id', userId)
        .eq('school_id', schoolId)
        .limit(1)

      if (!owned || owned.length === 0) return null

      const state = await getSchoolCrawlerState(serviceClient, schoolId)
      if (!state) return null
      return {
        id: schoolId,
        crawl_status: state.crawl_status,
        crawl_board_url: state.crawl_board_url,
        crawl_last_checked_at: state.crawl_last_checked_at,
      }
    },
    ['school-summary', userId, schoolId],
    { revalidate: HOME_DATA_TTL_SECONDS, tags: [schoolSummaryTag(schoolId)] },
  )()
}
```

캐시 키에 `userId` 를 넣는 것이 필수다 — 안 넣으면 A 가 채운 캐시를 B 가 읽는다. 무효화 태그는 `schoolSummaryTag(schoolId)` 그대로 둔다 (`app/(app)/settings/actions.ts` 가 이 태그로 무효화한다).

- [ ] **Step 4: 호출부를 고친다**

`app/(app)/page.tsx`:

```typescript
    const schoolPromise = child.school_id && user
      ? getSchoolSummary(user.id, child.school_id)
      : Promise.resolve(null)
```

- [ ] **Step 5: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 성공. 인자 누락이 있으면 여기서 잡힌다.

- [ ] **Step 6: 남의 학교가 안 보이는지 확인한다**

dev 서버에서 로그인한 뒤, `app/(app)/page.tsx` 의 호출을 **일시적으로** 자기 자녀가 없는 학교 id 로 바꿔 홈을 렌더한다.

Expected: 크롤 상태 배너가 **나오지 않는다**(`null`). 확인 후 코드를 되돌린다.

- [ ] **Step 7: 커밋**

```bash
git add lib/server-cache.ts "app/(app)/page.tsx"
git commit -m "fix(security): getSchoolSummary 에 소유권 검증 추가

lib/server-cache.ts 의 service_role 사용 5곳 중 소유권 검증이 아예 없는 유일한
곳이었다. schoolId 만 알면 아무 학교의 크롤 상태를 읽을 수 있었다.

app/api/schools/[schoolId]/crawl/route.ts 가 이미 쓰고 있는 패턴을 옮긴다 —
children 에서 (user_id, school_id) 로 소유권을 확인한 뒤에만 상태를 읽는다.
캐시 키에도 userId 를 넣는다. 안 넣으면 A 가 채운 캐시를 B 가 읽는다.

나머지 4곳은 고치지 않는다. unstable_cache 콜백이 요청 스코프 밖이라 쿠키를 못
읽는 아키텍처 제약이고, 이미 userId 를 캐시 키와 쿼리 양쪽에 걸어 스코프를 지킨다.
고치려면 홈·캘린더·급식의 렌더 아키텍처를 다시 짜야 해서 이 사업의 성격과 다르다."
```

---

## Task 16: 드리프트 차단 전환 + 계획 문서 닫기

**Files:**
- Modify: `.github/workflows/db-migrate.yml` (사업 A 가 만든 파일, `apply` 잡)
- Rewrite: `docs/supabase/schema.md`
- Modify: `schema-migration-plan.md`

**Interfaces:**
- Consumes: Task 1·2 의 `gen:types` 와 경고 검사
- Produces: 마이그레이션 적용 **직후** 시점에 타입 드리프트가 차단된다.

- [ ] **Step 1: 차단 검사를 `db-migrate.yml` 의 `apply` 잡에 붙인다**

`ci.yml` 쪽을 차단으로 바꾸지 **않는다.** `ci.yml` 과 `db-migrate.yml` 은 같은 push 로 **동시에** 트리거되므로, `ci.yml` 이 `db push` 완료 전에 타입을 비교하면 경합으로 깜빡인다. 적용 **직후**가 유일하게 결정적인 시점이다.

`.github/workflows/db-migrate.yml` 의 `apply` 잡, `마이그레이션 적용` 스텝 **뒤에** 추가:

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Install dependencies
        run: npm ci

      # 적용 직후가 타입을 DB 와 비교할 수 있는 유일한 결정적 시점이다.
      # ci.yml 은 같은 push 로 동시에 돌아 db push 완료를 보장하지 못하므로
      # 그쪽은 경고로 남겨 둔다.
      - name: 타입 드리프트 차단 검사
        env:
          SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}
        run: |
          npm run gen:types
          if ! git diff --exit-code -- types/database.generated.ts; then
            echo "::error file=types/database.generated.ts::스키마와 타입이 다릅니다. 'npm run gen:types' 를 돌리고 커밋하세요."
            exit 1
          fi
          echo "타입 드리프트 없음"
```

- [ ] **Step 2: 워크플로 문법을 검사한다**

```bash
python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/db-migrate.yml', encoding='utf-8'))
steps = d['jobs']['apply']['steps']
names = [s.get('name') or s.get('uses') for s in steps]
print(names)
assert '타입 드리프트 차단 검사' in names
assert names.index('마이그레이션 적용') < names.index('타입 드리프트 차단 검사')
drift = [s for s in steps if s.get('name') == '타입 드리프트 차단 검사'][0]
assert 'continue-on-error' not in drift
print('OK')
"
```

Expected: 스텝 목록 + `OK`

- [ ] **Step 3: 일부러 어긋내서 차단을 확인한다**

```bash
printf '\n// intentional drift\n' >> types/database.generated.ts
npm run gen:types
git diff --exit-code -- types/database.generated.ts; echo "종료코드: $? (1 이면 차단 = 정상)"
git checkout -- types/database.generated.ts
```

Expected: 종료코드 1

- [ ] **Step 4: `docs/supabase/schema.md` 를 다시 쓴다**

이 문서는 마지막 커밋이 2026-05-20 이고 `schedules` 를 살아 있는 테이블로 서술하며 `school_events`·`school_crawl_state`·`notice_card_translations`·`app_jobs`·`notice_ai_translations`·`subject_translations` 가 전부 빠져 있다.

**컬럼 목록은 쓰지 않는다** — `types/database.generated.ts` 가 정본이다. 남기는 것은 generated 가 담지 못하는 것뿐:

```markdown
# Supabase 스키마 개요

> **컬럼 정의의 정본은 [`types/database.generated.ts`](../../types/database.generated.ts) 다.**
> 이 문서는 그 파일이 담지 못하는 것 — 테이블의 역할, RLS 경계, 테이블 간 관계 — 만 적는다.
> 컬럼 목록을 여기에 옮겨 적지 말 것. 그래서 이 문서가 석 달간 stale 이었다.

## 테이블

| 테이블 | 역할 | 도입 |
|---|---|---|
| `profiles` | 사용자 언어 설정. 식별의 정본은 `auth.users` | `0001` / `0049` |
| `children` | 자녀 ↔ 학교 연결. `school_id` NOT NULL, FK 는 `ON DELETE RESTRICT` | `0001` / `0016` / `0051` |
| `schools` | 학교 마스터. NEIS 코드 조합이 유니크 키 | `0001` / `0051` |
| `school_crawl_state` | **크롤 상태의 정본.** `schools` 의 crawl_* 는 `0048` 이 삭제 | `0013` / `0033` |
| `notices` | 공지 원본 + 추출 결과(`extracted_content`) | `0001` ~ `0023` |
| `notice_cards` | 공지에서 뽑은 카드(한국어) | `0001` |
| `notice_card_translations` | 카드의 언어별 번역 (행 분리) | `0026` |
| `notice_ai_translations` | 공지 본문의 언어별 번역 | `0005` ~ `0031` |
| `notice_hides` | 사용자별 공지 숨김 | `0004` |
| `school_events` | 공지에서 파생된 학교 일정 (캘린더) | `0017` / `0028` ~ `0030` / `0051` |
| `meals` | 급식. **`schools` 와 FK 가 없다** — NEIS 코드 단위 전역 공유 캐시 | `0001` / `0032` |
| `subject_translations` | 과목·급식 라벨 번역 캐시 | `0032` |
| `app_jobs` | 작업 큐. `0036` 이 RLS 로 잠금 | `0027` / `0036` |

## 삭제된 테이블

| 테이블 | 삭제 | 후신 |
|---|---|---|
| `schedules` | `0018` | `school_events` (`0017`) |
| `document_files` | `0006` | 없음 (`notice-originals` 버킷도 `0046` 이 제거) |

## RLS 경계

거의 모든 정책이 같은 형태다 — **`children` 을 거쳐 `auth.uid()` 와 학교를 잇는다.**

    exists (select 1 from children where children.school_id = <대상>.school_id
                                    and children.user_id = auth.uid())

`notice_cards` · `notice_ai_translations` · `notice_card_translations` 는 `notices` 를 한 번 더 거친다. `app_jobs` 는 정책이 없다(`0036`) — service_role 전용이다.

## 스토리지

| 버킷 | 공개 | 비고 |
|---|---|---|
| `notice-attachments` | 비공개 (`0037`) | 서명 URL 라우트로만 접근 |
```

- [ ] **Step 5: `schema-migration-plan.md` 를 닫는다**

문서 상단에 완료 기록을 추가한다:

```markdown
> **상태: 완료 (2026-08-27).**
> Phase 1·2·5 는 `0012`·`0014`~`0016`·`0017`/`0018` 로 이미 끝나 있었다.
> **Phase 3** 은 `0049`, **Phase 4** 는 `0048` 로 완료했다 (사업 D).
> **Phase 6 은 사용자 결정으로 중단한다** — "과거 번역 정보 필요할 수도 있으니까
> 이 부분은 남겼으면 좋겠다"(2026-08-27). `notice_ai_translations` 의 남은
> 10 컬럼은 지우지 않는다. 값 도메인만 `0050` 이 조였다.
> 후속 계획: [docs/superpowers/plans/2026-08-27-D-db-cleanup.md](docs/superpowers/plans/2026-08-27-D-db-cleanup.md)
```

- [ ] **Step 6: 커밋**

```bash
git add .github/workflows/db-migrate.yml docs/supabase/schema.md schema-migration-plan.md
git commit -m "ci: 타입 드리프트 차단 검사를 db-migrate 적용 직후로 이동 + 스키마 문서 갱신

ci.yml 쪽은 경고로 남긴다. ci.yml 과 db-migrate.yml 은 같은 push 로 동시에 돌아
db push 완료를 보장하지 못한다 — 적용 직후가 유일하게 결정적인 시점이다.

docs/supabase/schema.md 는 2026-05-20 이후 stale 이었고 schedules 를 살아 있는
테이블로 서술하며 테이블 6개가 빠져 있었다. 컬럼 목록을 옮겨 적는 방식이
stale 의 원인이므로, 이제 컬럼은 generated 타입에 위임하고 역할·RLS 경계·관계만 적는다.

schema-migration-plan.md 는 Phase 3·4 완료와 Phase 6 중단 결정을 기록하고 닫는다."
```

---

## 선택 Task A: 경쟁 상태 해소 — 소스 번역 행 분리 ⏸

> **⛔ 착수 승인 대기.** 스펙 §19 Q1 이 미결이다.
> 이건 DB 정리가 아니라 **번역 파이프라인 변경**이고, `translate_sources_for_locale()` 은
> 사업 C(추출 수리)의 사정권 안이다. 포함하면 두 사업이 같은 파일을 동시에 고친다.
> **본 배포 순서에서 뺀다.** 설계는 아래에 완비해 두고, 승인이 나면 바로 실행한다.

### 왜 필요한가

`content_extraction_service.py` 의 `translate_sources_for_locale()` 은 `notices.extracted_content` 를 **통째로 읽어 통째로 쓴다.** 락은 프로세스 내 `asyncio.Lock` 이라 **프로세스 간에는 무력**하다. 이 함수는 서로 다른 4개 진입점(translation worker Job, crawler worker Job, scheduled content extractor Job, API 인라인)에서 호출되고, API 서비스는 `--max-instances` 미지정이라 Cloud Run 기본 100 인스턴스까지 오토스케일하며, translation worker 는 배치 10개를 `asyncio.gather` 로 동시에 돌린다.

> **스펙이 교정한 것**: `refactor.md` §3 이 지목한 「신뢰도 높음」 3건 중 ②(`notice_cards.content` lost update)는 **`0026` 이 이미 해소했다** — 언어별 콘텐츠를 `notice_card_translations` **행**으로 분리했다. **그 선례가 이 설계의 근거다.** ③(프론트/백엔드 번역 겹침)은 `app_jobs_active_job_key_idx` 유니크 부분 인덱스(`0027:22-24`)가 막고 있어 「중복 실행」이 아니라 **문서-코드 불일치** 문제다.

### 설계 (A안 — 언어별 행 분리)

**Files:**
- Create: `supabase/migrations/0052_notice_source_translations.sql`
- Modify: `backend/app/services/content_extraction_service.py` (`translate_sources_for_locale`)
- Modify: `lib/notices.ts` (첨부 카드 본문 읽기, `hasCompleteTranslatedSources`)
- Create: `backend/tests/test_notice_source_translations.py`

**Interfaces:**
- Consumes: Task 1 (타입 재생성), `0026` 의 행 분리 패턴
- Produces: `notice_source_translations(notice_id, source_index, target_language, translated_text)`. `extracted_content.sources[].translations` 는 **읽기 전용 파생 캐시**가 된다 (삭제하지 않는다 — 사용자 결정).

```sql
-- 0026 이 notice_cards 의 언어별 lost update 를 '행 분리' 로 해소한 그 패턴을
-- sources[].translations 에 똑같이 적용한다.
create table if not exists public.notice_source_translations (
  id uuid primary key default gen_random_uuid(),
  notice_id uuid not null references public.notices(id) on delete cascade,
  source_index integer not null,
  target_language text not null,
  translated_text text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (notice_id, source_index, target_language)
);

create index if not exists notice_source_translations_notice_id_idx
  on public.notice_source_translations (notice_id);

drop trigger if exists notice_source_translations_set_updated_at on public.notice_source_translations;
create trigger notice_source_translations_set_updated_at
before update on public.notice_source_translations
for each row execute function public.set_updated_at();

alter table public.notice_source_translations enable row level security;

drop policy if exists "notice source translations select own school" on public.notice_source_translations;
create policy "notice source translations select own school"
on public.notice_source_translations for select
using (
  exists (
    select 1
    from public.notices
    join public.children on children.school_id = notices.school_id
    where notices.id = notice_source_translations.notice_id
      and children.user_id = auth.uid()
  )
);

-- 백필: 기존 extracted_content.sources[].translations 를 행으로 편다.
-- 원본은 지우지 않는다 — 과거 번역 정보 보존 결정(2026-08-27).
insert into public.notice_source_translations (notice_id, source_index, target_language, translated_text)
select
  n.id,
  (s.ord - 1)::integer,
  t.key,
  t.value
from public.notices n
cross join lateral jsonb_array_elements(coalesce(n.extracted_content -> 'sources', '[]'::jsonb))
  with ordinality as s(elem, ord)
cross join lateral jsonb_each_text(coalesce(s.elem -> 'translations', '{}'::jsonb)) as t(key, value)
where t.value is not null and length(trim(t.value)) > 0
on conflict (notice_id, source_index, target_language) do nothing;
```

**코드 쪽 변경 요지** — `translate_sources_for_locale()` 이 `notices` 를 통째로 UPDATE 하는 대신 `notice_source_translations` 에 `on_conflict="notice_id,source_index,target_language"` upsert 한다. 「읽고-고치고-쓰기」가 사라지므로 `_SOURCE_TRANSLATION_LOCKS` 도 함께 제거한다. 읽기 쪽은 `lib/notices.ts` 가 `notice_source_translations` 를 우선 보고, 없으면 기존 `sources[].translations` 를 폴백으로 본다(백필 누락 대비).

**4단계 배포** — ① 테이블 생성 + 백필(0052) ② 백엔드 이중 쓰기(새 테이블 + 기존 jsonb 둘 다) ③ 읽기를 새 테이블로 전환 ④ jsonb 쓰기 중단(값은 **지우지 않는다**).

---

## 선택 Task B: 중복 저장의 canonical 정의 명문화 ⏸

> **⛔ 착수 승인 대기.** 선택 Task A 와 같은 Q1 에 묶여 있다.
> **전제: 어떤 저장소도 삭제하지 않는다** (사용자 결정). 과제는 「무엇을 지울까」가 아니라
> **「무엇이 정본이고 나머지는 무엇으로 부를까」** 를 정하는 것이다.

**Files:**
- Modify: `docs/supabase/schema.md` (「저장 위치와 정본」 절 추가)
- Modify: `lib/notices.ts` (`hasCompleteTranslatedSources` 의 판정 근거)
- Modify: `backend/app/services/notice_service.py`, `backend/app/services/content_extraction_service.py` (해당 쓰기 지점에 주석)

**Interfaces:**
- Consumes: 선택 Task A 를 실행했다면 #2 가 자연히 테이블로 이동해 두 작업이 합쳐진다
- Produces: 어긋났을 때 어느 쪽을 믿을지가 정해진다. `scripts/rebuild_school_events.py` 가 일회성 스크립트가 아니라 **정본에서 파생물을 재생성하는 공식 절차**가 된다.

| 도메인 | canonical | 나머지의 지위 | 근거 |
|---|---|---|---|
| 공지 원문 | `extracted_content.sources[].refined_text` | `notices.original_text` 는 **파생 캐시** — `_full_body_text()` 로 재계산 가능 | concat 의 방향이 sources → original_text |
| 본문 번역 | `notice_ai_translations.translated_text` | `sources[].translations` 의 「본문분」은 **파생 캐시**, 첨부분은 canonical | 본문 렌더가 실제로 전자를 쓴다 |
| 카드 번역 | `notice_card_translations.translated_content` | 유일본 | `0026` 이 이미 정리 |
| 요약 번역 | `extracted_content.summary.translations[locale]` | 유일본 | 소비자 하나 |
| 추출된 사실 | `notices.source_hard_facts` | `due_date`/`event_dates`/`event_location` 은 **파생 인덱스**, `school_events` 는 **파생 뷰** | `rebuild_school_events.py` 가 실제로 이 방향으로 재계산한다 |

**검토할 한 가지**: `hasCompleteTranslatedSources()` 가 「번역 완료」를 **파생 캐시**(`sources[].translations`)의 존재로 판정한다. canonical(`notice_ai_translations`)을 보도록 바꿀지 결정이 필요하다. 지금 바꾸면 선택 Task A 의 읽기 전환과 충돌하므로 **A 와 함께 처리한다.**

---

## 자체 검토

### 1. 스펙 커버리지

| 스펙 단위 | 담당 Task | 비고 |
|---|---|---|
| D1 타입 자동 생성 (§5.2) | Task 1 | |
| D1 CI 드리프트 (§5.3) | Task 2 (경고) + Task 16 (차단) | 차단 지점을 `ci.yml` → `db-migrate.yml` 로 옮김 (사유는 Task 16 Step 1) |
| D1 부수 — `docs/supabase/schema.md` (§5.4) | Task 16 Step 4 | 스펙의 기본안(재작성)을 따름 |
| D2 인덱스 6종 (§6) | Task 3 | |
| D3 트리거 2 (§7.1) | Task 4 | |
| D3 중복 정책 (§7.2) | Task 4 | |
| D3 유령 버킷 (§7.3) | Task 4 | |
| D4 깨진 스크립트 (§10) | Task 5 | |
| D5 안전한 식별 (§11.2) | Task 6 + Task 8 | UUID 앵커. **이름 매칭 0건** (§「이름 매칭 금지」 표로 전수 확인). 문자열은 `meals` 에서만 — `schools` 와 FK 가 없다 |
| D5-a 코드 제거 (§11.4) | Task 7 | `app/(app)/settings/page.tsx` **추가** (스펙 누락) |
| D5-b 데이터 삭제 (§11.3) | Task 8 | 쇼케이스 학교 **추가** (스펙 누락) |
| **자녀 이관** (스펙 §18-7 이 「0건 아니면 중단」만 적고 처리를 안 정함) | **Task 6 Step 3 + Task 8 Step 1** | 결정 4. `school_id` 한 컬럼만 갱신, 행 수 대조, 상태 행 보장 |
| D6-a 이중 쓰기 + select 좁히기 (§8.4) | Task 9 | |
| D6-b 컬럼·인덱스 삭제 (§8.4) | Task 10 | |
| D7-a 프로필 쓰기 (§9.4) | Task 11 | `LoginButtons.tsx` **추가** (스펙 누락) |
| D7-b 컬럼 삭제 (§9.3) | Task 12 | `avatar_url`·`display_name`·`email` 전부. `native_language` 는 유지 + 주석 |
| D8-1 `school_events.source_language` (§13.1) | Task 13 | |
| D8-2 `validation_status` CHECK 축소 (§13.1) | Task 13 | |
| D8-3 `type='schedule'` (§13.1) | Task 13 Step 1 | 실측 0건 → 데드코드 확정. **읽기 경로 삭제는 범위 밖으로 명시** |
| D9-2 `schools` NOT NULL (§13.2) | Task 14 | |
| D9-3 `children.school_id` NOT NULL (§13.2) | Task 14 | |
| D9-4 `event_kinds` text[] (§13.2) | Task 14 | 스펙의 「값 두 가지」 가정을 **일반 변환으로 교체** |
| D9-1 `meals.calories` (§13.2) | **제외** | 실측 102/102 캐스트 불가 — §19 「0 이 아니면 별건 분리」 적용 |
| D9-5 `school_events` UNIQUE (§13.2) | **제외** | 실측 충돌 0건 |
| D9-6 `meals` FK (§13.2) | **제외** | 스펙 §2 가 이미 비목표 |
| D10 `getSchoolSummary` (§12.3 ③) | Task 15 | 스펙 기본안(Q2 = ③)을 따름 |
| D11 경쟁 상태 (§14) | 선택 Task A | 본 배포 순서에서 제외, 설계 완비 |
| D12 canonical (§15) | 선택 Task B | 동일 |
| Phase 3·4 완료 기록 (§22-4) | Task 16 Step 5 | |

**본 배포 순서에서 의도적으로 뺀 것**: D9-1 · D9-5 · D9-6(실측/비목표 근거), D11 · D12(승인 대기). 그 외 빠진 것 없음.

### 2. 자리표시자 점검

"TBD" · "적절히" · "비슷하게" 없음. 모든 코드·SQL Step 에 실제 내용이 들어 있다. 사전 카운트의 Expected 값은 **2026-08-27 운영 DB 실측치**다.

### 3. 심볼 일관성

| 심볼 | 정의 | 사용 | 일치 |
|---|---|---|---|
| `_school_backfill_payload` | Task 9 Step 3 | Task 9 Step 1(테스트), Step 3(호출) | ✅ |
| `_SCHOOL_ROW_COLUMNS` | Task 9 Step 3 | Task 9 Step 1(테스트), Step 4(select) | ✅ |
| `getSchoolSummary(userId, schoolId)` | Task 15 Step 3 | Task 15 Step 4(호출부 동시 수정) | ✅ |
| `schoolSummaryTag(schoolId)` | 기존 `lib/server-cache.ts` | Task 15 가 **바꾸지 않는다** — `settings/actions.ts` 의 무효화가 계속 맞는다 | ✅ |
| `set_updated_at()` | `0001:105-111` (기존) | Task 4, 선택 A | ✅ |
| `children_user_school_id_idx` | Task 3 이 비부분으로 재생성 | Task 14 는 **건드리지 않는다** | ✅ 중복 작업 제거 |
| `Database` / `Json` / 별칭 5개 | Task 1 Step 4 | 전 저장소 (`@/types/database`) | ✅ export 집합 불변 |
| `NoticeAiValidationStatus = 'passed' \| 'failed'` | Task 1 Step 4 (TS) | Task 13 Step 4 (DB CHECK) | ✅ 양쪽 동일 |
| 마이그레이션 0045~0052 | Task 3·4·8·10·12·13·14 + 선택 A | 번호 중복 없음, 0035~0044 미사용 | ✅ |

### 4. 순서 의존성 검산

| 이 Task 는 | 이것 없이는 못 한다 | 이유 |
|---|---|---|
| Task 3 이후 전부 | 사업 A 의 이력 정합 | `db push` 첫 실행이 `0018:1` `drop table schedules` 를 재실행한다 |
| Task 8 | Task 6 의 실측 확인 | 앵커 UUID·이관 대상·자녀 2건이 실행 시점에도 맞아야 한다. `ON DELETE RESTRICT` 라 이관 없이는 삭제가 실패한다 |
| Task 8 | Task 7 | 시드 코드가 살아 있으면 다음 렌더가 다시 뿌린다 |
| Task 9 Step 6 | Task 5 | 시드 스크립트가 `schools.crawl_*` 마지막 쓰기다 |
| Task 10 Step 2 가드 | Task 8 | 상태 행 없는 학교(쇼케이스)를 지워야 가드가 통과한다 |
| Task 10 | Task 9 Step 8 의 크롤 성공 | 코드만 되돌리면 원복되는 구간을 확보 |
| Task 12 | Task 11 Step 7 의 온보딩 완주 | 동일 |
| Task 13 | Task 7 | `lib/demo-school.ts:1157` 이 `school_events.source_language` 를 읽는 마지막 TS 경로 |
| Task 14 | Task 8 | 데모 학교가 남아 있으면 NEIS 코드 NOT NULL 이 애매해진다 |
| Task 16 | Task 1·2 | `gen:types` 와 generated 파일이 있어야 한다 |

### 5. 롤백 경로

| Task | 되돌리기 |
|---|---|
| 1, 2, 5, 7, 9, 11, 15, 16 | `git revert` |
| 3 | `drop index` (7줄) + 부분 인덱스 재생성 1줄 |
| 4 | 트리거 2 `drop`, 정책 1 재생성(`0008:10-21` 원문), 버킷 1 `insert`(`0001:243-254` 원문) |
| **8** | 🔴 **부분 복구만 가능.** ① **자녀 이관은 되돌릴 수 있다** — `children` 행은 지우지 않고 `school_id` 만 바꾸므로, 데모 학교 행을 되살리면 원위치가 가능하다. 그러나 같은 마이그레이션이 학교 행까지 지우므로 **한 번 적용된 뒤에는 불가**하다 ② 데모·쇼케이스의 공지·번역·일정은 **복구 불가**다. 착수 전 `audit_demo_data.py` 출력을 반드시 남긴다 ③ 두 배포로 쪼개고 싶다면 이관(`update`)만 하는 `0047` 과 삭제만 하는 `0047b` 로 나눌 수 있다 — 그러면 이관 후 크롤·렌더를 확인한 뒤 삭제로 넘어갈 수 있다 |
| **10** | 🔴 복구 마이그레이션 필요. 값은 `school_crawl_state` 에서 역백필 가능 |
| **12** | 🔴 복구 마이그레이션 필요. `email` 은 `auth.users` 에서 복원 가능, `display_name`·`avatar_url` 은 원래 전부 null |
| **13** | 🔴 복구 마이그레이션 필요. `source_language` 는 전부 `'ko'` 였으므로 무손실 복원 가능 |
| **14** | 🔴 복구 마이그레이션 필요. NOT NULL 은 `drop not null` 로 즉시, `event_kinds` 는 text[] → jsonb 역변환 필요 |

---

## 스펙에서 발견한 누락·모순

계획을 쓰며 스펙과 어긋난 것을 여기 모아 둔다. **전부 이 계획이 스펙 대신 실측을 따랐다.**

| # | 스펙 | 실제 | 이 계획의 처리 |
|---|---|---|---|
| 1 | §18-7 「데모 학교 자녀 0 이어야 진행」 (0 을 기대) | **자녀 2건** — 서로 다른 계정 2개 | 사용자 결정 4(이관 후 삭제)를 받아 Task 8 에 이관 로직 추가. Task 6 이 실행 시점에 재확인 |
| 2 | §11.1 데모 학교 이름 `'Naranhi School'` | **`'부천부흥중학교'`** — 실제 학교와 동명 | 이름 매칭을 완전히 배제. UUID 앵커만 사용 |
| 3 | §11 대상은 데모 학교 1개 | **`Naranhi Showcase School` 이 하나 더 있다** (공지 2, 일정 6, 저장소 참조 0건) | Task 6·8 에 둘째 앵커 추가 |
| 4 | §8.3 「상태 행 없는 학교는 이제 생기지 않는다 … 폴백은 이미 죽어 있다」 | **8개 중 1개(쇼케이스)에 `school_crawl_state` 행이 없다** | Task 8 → 9 → 10 순서로 해소. Task 10 에 가드 추가 |
| 5 | §13.2-4 `event_kinds` 값은 `["event"]`/`["deadline"]` **두 가지뿐** | **세 가지** — `["deadline","event"]` 조합이 13행 | 2분기 CASE 를 `jsonb_array_elements_text` 일반 변환으로 교체 |
| 6 | §13.2-1 `meals.calories` 「0건이면 캐스트」 | **102/102 가 `"905.1 Kcal"`** — 캐스트 불가 | Task 14 에서 제외. §19 「별건 분리」 규정 적용 |
| 7 | §11.4 코드 제거 목록 | `app/(app)/settings/page.tsx`(`DemoSchoolPicker` 렌더) **누락** | Task 7 Step 3 에 추가 |
| 8 | §9.4 D7-a 파일 목록 | `app/(auth)/login/LoginButtons.tsx` 가 `profileEmail`/`displayName` 을 **보내고 있다** — 누락 | Task 11 Step 4 에 추가 |
| 9 | §5.3 CI 드리프트 「PR 경고 → main 차단」 | `ci.yml` 과 `db-migrate.yml` 이 같은 push 로 **동시에** 돌아 `main` 차단이 경합한다 | 차단 지점을 `db-migrate.yml` 의 `apply` 잡(적용 직후)으로 이동 |
| 10 | §6.1 `children(user_id)` 단일 인덱스 신설 + §13.2-3 부분 인덱스를 전체로 재생성 | 둘을 다 하면 **선두 컬럼 중복** | Task 3 에서 부분 인덱스만 전체로 교체. 단일 인덱스는 만들지 않음 |
| 11 | §13.1-3 「`type='schedule'` 실측 후 판단」 | **0건** — 데드코드 확정 | Task 13 Step 1 에서 확인만 하고 읽기 경로 삭제는 **범위 밖으로 명시** (컬럼 삭제가 아니라 분기 삭제라 성격이 다르다) |
| 12 | §13.2-5 `school_events` UNIQUE 확장 「실측 후 판단」 | 충돌 **0건** | Task 14 에서 제외 |
