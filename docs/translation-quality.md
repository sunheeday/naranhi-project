# 번역 품질 개선 과정 & 최종 파이프라인

본 문서는 학교 가정통신문 번역 파이프라인(`backend/app/translation/`)의 **품질 개선 방법론**과
그 결과로 정착된 **최종 번역 파이프라인 구조**를 설명한다.

- 대상 언어: 영어(en) · 러시아어(ru) · 아랍어(ar)
- 북극성(North Star): **번역 언어를 모국어로 쓰는 한국 거주 이주민 학부모가 통신문을 정확히 이해할 수 있는가**
- 개선 이력 데이터: `.agents/translation-quality/iterations/_history.json`

---

## 1. 개선 방법론 — 2-에이전트 이터레이션 루프

품질을 "감"이 아니라 **측정 → 개선 → 회귀 검증**의 반복으로 끌어올렸다. 한 이터레이션은 다음 흐름을 따른다.

```
[1] 한국어 원문 N개 준비 (training / held-out 분할)
        │
[2] 번역 파이프라인 실행 (en, ru, ar) → pipeline-output/<lang>.json
        │
[3] 평가자 에이전트   → 8축 채점, feedback-report.md, scores.json, Verdict
        │
[4] 엔지니어 에이전트 → 프롬프트/검증기 개선 (코드 변경), improvement-plan.md
        │
[5] 같은 입력으로 재실행 → 회귀/개선 측정
        │
[6] Verdict로 종료 판정 (ship_ready면 종료)
```

### 두 에이전트의 역할 분리

| 에이전트 | 하는 일 | 제약 |
|---|---|---|
| **평가자(Evaluator)** | 8축 0–5점 채점, 회귀 탐지, Verdict 부여 | 코드 수정 금지, 평가 기준 변경 금지 |
| **엔지니어(Engineer)** | feedback 기반으로 프롬프트·검증기 개선 | held-out 디테일 열람 금지, 한 이터 5개 변경 초과 금지 |

### 일반화 측정 — held-out 분할

통신문을 **training**(엔지니어가 디테일을 보고 고침)과 **held-out**(엔지니어 비공개, 일반화 측정용)으로 나눈다.
training 점수만 오르고 held-out이 정체/하락하면 **과적합 신호**로 잡는다.
- 이번 프로젝트: training 4건(n01,n02,n05,n06) / held-out 2건(n03,n04)
- 전 이터에서 `generalization_gap`(held − train)이 **음수 유지** = held-out이 오히려 더 높음 → 과적합 없음.

### 8축 평가 루브릭 (가중 평균)

각 번역을 아래 8개 축에서 **0–5점**으로 채점한다. 모든 축은 북극성(이주민 학부모 이해도) 관점에서 본다 —
어떤 축이 만점이어도 "무엇을/언제까지/어떻게 해야 할지 모름"이면 종합 verdict는 fail.

| # | 축 | 무엇을 보는가 | 가중치 |
|---|---|---|---|
| 1 | **Fact Preservation** (사실 보존) | 날짜·시각·장소·금액·전화·계좌·URL·학년/반·인원·제출물·마감 등 기계 검증 가능 사실이 원문과 일치하는가 | 1.0 |
| 2 | **Action Clarity** (행동 명확성) | 학부모/학생이 *무엇을 / 언제까지 / 어떻게* 해야 하는지 한 번에 잡히는가 | 1.0 |
| 3 | **Tone & Register** (톤·격식) | 학교 공식 통신문의 공손·중립 톤을 타겟 언어에 맞게 매핑했는가 (단, 과한 고급 격식은 이해 장벽이라 감점) | 0.8 |
| 4 | **Completeness** (완전성) | 원문 정보 누락 없음 + 원문에 없는 정보 추가 없음 (1:1 대응) | 0.8 |
| 5 | **Naturalness / Readability** (자연스러움) | 이주민 학부모가 한 번에 이해하는가 (직역체/기계어투 점검, 이해도 > 매끄러움) | 0.7 |
| 6 | **Cultural & Linguistic** (문화·언어 적절성) | 호칭·존대·표기 관습, 한국 학교 개념(학예회·돌봄교실 등)을 처음 보는 보호자도 이해하게 풀었는가 | 0.8 |
| 7 | **Meal / Allergy Accuracy** (식재료·알레르기) | 승인 사전 매핑 사용, critical 알레르겐/종교 제약 표기 (식단 정보 없으면 0=N/A, 평균에서 제외) | 0.7 |
| 8 | **Safety & Risk** (안전·위험) | 오역이 안전/건강/출결/납부/참여에 영향 줄 가능성 (0/3/5만 사용) | **2.0** |

**점수 의미:** 5=완벽 · 4=좋음(사소한 흠) · 3=합격선 · 2=위험(오해 가능) · 1=실패(사실 왜곡/누락) · 0=해당 없음.

**가중 평균 공식:**
```
weighted_avg = ( fact×1.0 + action×1.0 + tone×0.8 + completeness×0.8
               + naturalness×0.7 + culture×0.8 + meal×0.7 + safety×2.0 ) / 8.8
```
Safety가 ×2로 가장 큰 가중치를 갖는다(안전 오역은 치명적). 축별 0–5점의 상세 판정 기준과 예시는
`.agents/translation-quality/templates/evaluation-rubric.md` 참조.

### 종료 기준 (Stopping Criteria)

끝없이 돌리지 않는다. 평가자가 매 이터 끝에 4개 Verdict 중 하나를 부여한다.

| Verdict | 의미 |
|---|---|
| `ship_ready` | 품질 충분 → 자동 종료 |
| `diminishing_returns` | 개선 폭 소진 → 사용자 확인 후 종료 |
| `blocking_regression` | 과적합/회귀 → 강제 정지 |
| `needs_iteration` | 개선 여지 있음 → 다음 이터 진행 |

**ship_ready 6조건:** 세 언어 모두 train_avg≥4.2 & held_out_avg≥4.0 · critical 0 · safety≥4 · fact/action/meal≥4 ·
Comprehension Pass 전건 통과 · 직전 2회 held-out 무하락.

---

## 2. 개선 이력 — iter-001 → iter-004

| 이터 | overall train | overall held-out | critical | Verdict | 핵심 변경 |
|---|---|---|---|---|---|
| **001** (baseline) | 3.98 | 4.08 | 0 | needs_iteration | — (최초 측정) |
| **002** | **4.62** | **4.68** | 0 | needs_iteration | 검증기 정규화 대칭화 + en 직역체 룰 + 문화 룰 |
| **003** | 4.62 | 4.68 | 0 | **ship_ready** | 정규화를 dates/grades/times로 확장 |
| **004** (Phase 2) | 4.62 | 4.68 | 0 | **ship_ready** | 러시아어 전용 룰(RU_TARGET_RULES) 추가 |

언어별 최종(iter-004): en 4.61/4.63 · ru 4.70/4.75 · ar 4.54/4.65 (train/held-out).

### 가장 큰 지렛대 — "검증기 위양성"이 진짜 문제였다

iter-001에서 18건 중 17건이 `admin_review_required`로 빠졌다. 원인을 파보니 **번역 본문은 정확한데
hard_fact 검증기가 source(원문)와 target(번역)의 사실을 서로 다른 규칙으로 정규화**해서 "사실 불일치"로
오판하고 있었다(위양성). 예:

- 전화번호: 원문 `032-320-0096` ↔ 번역 `+82 32 320 0096` 을 다른 값으로 판정
- 요금: 원문 `무료` ↔ 번역 `0 KRW` 를 다른 값으로 판정
- 날짜: 범위 `6/9~6/11` ↔ 개별일 `6/9, 6/10, 6/11` 을 다른 값으로 판정

→ `validators.py`에서 source/target에 **동일 규칙을 대칭 적용**하도록 고치자 점수가 4.6대로 점프하고,
`ready_to_save` 비율이 3/18 → 13/18로 올랐다. **번역 모델은 거의 건드리지 않았다.**

### 프롬프트 구조 정리 (Phase 1) + 러시아어 룰 (Phase 2)

언어별 규칙이 코드 곳곳에 흩어지지 않도록 `LanguageProfile` 레지스트리로 통합하고(출력 무변화 리팩터),
비어 있던 러시아어 슬롯을 `language-criteria/ru.md` 기반으로 채웠다. iter-004 재평가에서 ru 유지+미세개선,
en/ar 무회귀로 ship_ready가 유지됨을 확인.

---

## 3. 최종 번역 파이프라인 (`orchestrator.py`)

한 통신문 × 한 언어를 번역할 때 거치는 단계. **두 개의 품질 게이트**(hard_fact, context_tone)가 있고,
각 게이트는 자동수정(auto-fix)을 시도한 뒤 실패하면 `admin_review_required`로 사람 검토에 넘긴다.

```
한국어 원문
   │
 ① 원문 hard_fact 추출            extract_source_hard_facts   (temp 0.0)
   │   날짜·시각·금액·전화·URL·대상학년·제출물·마감 등 구조화
   │
 ② 식재료 매핑 (해당 시)           map_ingredients_if_needed
   │   승인 사전으로만 매핑, 미매핑 알레르겐은 human_review
   │
 ③ 한국어 → 영어 피벗             translate_ko_to_en_pivot    (temp 0.1)
   │   영어를 의미 허브로 사용 + 의미 해소 룰(맥락 의존 표현)
   │
 ④ 영어 → 타겟 언어               translate_en_to_target      (temp 0.1)
   │   ★ COMMON_SYSTEM_PROMPT + LANGUAGE_PROFILES[lang] 규칙 주입
   │
 ⑤ 번역문 hard_fact 재추출         extract_target_hard_facts   (temp 0.0)
   │
 ┌─ 게이트 A: hard_fact 검증 ──────────────────────────────────┐
 │ ⑥ 코드 검증 (결정적)            validate_hard_facts_by_code  │
 │     source vs target 사실 대칭 비교                         │
 │     FAIL → LLM 2차 검증 → auto-fix(fix_hard_facts) 반복     │
 │     그래도 FAIL → admin_review_required (중단)              │
 └────────────────────────────────────────────────────────────┘
   │ PASS
 ⑦ 타겟 → 한국어 역번역            back_translate_to_ko        (temp 0.0)
   │
 ┌─ 게이트 B: context/tone 검증 ───────────────────────────────┐
 │ ⑧ 의미·톤 검증                  validate_context_tone        │
 │     원문 + 역번역 대조, 의미 왜곡/톤 붕괴 점검              │
 │     FAIL_FIXABLE → auto-fix(fix_context_tone) 반복          │
 │     PASS 아니면 → admin_review_required (중단)              │
 └────────────────────────────────────────────────────────────┘
   │ PASS
 ⑨ 저장 메타데이터 생성            build_supabase_payload      (temp 0.0)
   │
 status = ready_to_save  ✅
```

### 결과 status 3종

| status | 의미 |
|---|---|
| `ready_to_save` | 두 게이트 모두 통과 → 바로 게시 가능 |
| `admin_review_required` | 게이트에서 막힘 → 사람 검토 필요 (사실 안전장치) |
| (`driver_error`) | API 호출 실패 등 인프라 오류 (재시도 대상) |

### 사실 검증의 핵심 설계 (`validators.py`)

게이트 A는 **결정적 코드 검증이 1차**, LLM은 2차 보조다. 코드 검증은 사실 종류별로 정규화 후 비교한다.

- 전화번호: `+82` 국제형 ↔ `0` 국내형 canonical 수렴
- 요금: 무료 = 0 = "전액 지원/fully supported" 동치 클래스
- URL: host 소문자·끝슬래시 흡수 (단 **경로 변경은 FAIL 유지**)
- 날짜: 범위 ↔ 개별 동치, 비-절대 토큰(`2026학년도`·`6월 중`·`마감 시`)은 게이트 제외
- 시각(clock) vs 소요시간(duration) 분리
- 대상학년 vs 반(class) 라벨 분리
- 기관명 prose 연락처는 결정 게이트에서 제외(토큰만 비교)

**안전장치:** 진짜 사실 변경/누락(요금 액수, URL 경로, 시각 변경, 대상학년 누락, 새 날짜 등장)은 여전히 FAIL.
회귀 방지용 단위 테스트 20건이 위양성 교정 + 음성(FAIL 유지) 케이스를 함께 보장한다.

---

## 4. 최종 프롬프트 구조 (`prompts.py`)

```
COMMON_SYSTEM_PROMPT          ← 언어 무관 공통 (미션 + 협상불가 규칙 9개)
        +
LANGUAGE_PROFILES[lang]       ← 언어별 프로파일 (한 곳에 통합)
   ├ en → EN_TARGET_RULES     직역체 금지, 표 열 구조 보존, 시각/전화 표기
   ├ ru → RU_TARGET_RULES     격식·존대, 수-명사 일치, 24시간제+러시아식 날짜, «» 인용부호
   └ ar → AR_TARGET_RULES     label–value 라인 구조 보존, 복합문 분절
```

- 공통 규칙은 모든 단계 프롬프트에 공유된다.
- 단계별 프롬프트는 "언어"가 아니라 "파이프라인 공정"으로 나뉜다(같은 함수가 `target_language`만 바꿔 재사용).
- **언어 전용 규칙은 `translate_en_to_target` 단계에 주입**되며, 추가/확장은 `LANGUAGE_PROFILES` 한 곳에서 끝난다.
- 이 규칙들은 평가 페르소나(`.agents/translation-quality/language-criteria/<lang>.md`)와 **정렬**되어 있다(단일 출처).
- 단, "요일을 항상 별도 구조 필드로 추출한다"까지는 아직 아니다. 현재 hard fact 스키마는 날짜를 `YYYY-MM-DD` 중심으로 보존하고, 요일은 번역 표현 품질 가이드로 다룬다.

---

## 5. 재현 방법

### Codex용 목업 이터레이션 부트스트랩

Claude 팀의 실제 개선 이력을 Codex에서도 독립 검증하고 싶다면, 먼저 목업 통신문 세트로 새 이터레이션을 만든다.

```bash
# 목업 6건(training 4 / held-out 2)으로 이터레이션 생성
python scripts/scaffold_translation_quality_iteration.py \
  --iter-dir .agents/translation-quality/iterations/2026-06-02_iter-codex-001

# 구조 검증
python scripts/validate_translation_iteration.py \
  --iter-dir .agents/translation-quality/iterations/2026-06-02_iter-codex-001
```

- seed 데이터: `.agents/translation-quality/mock-notices/seed-set-v1.json`
- Codex 역할 분담 가이드: `.agents/translation-quality/codex-team.md`
- seed-set-v1 포함 실패 모드:
  - en: 직역형 안전 수칙, action phrasing
  - ru: 존칭/24시간제/학년 표기/표 구조
  - ar: MSA, Western digits, 종교 민감 식재료, line structure

```bash
# 사전: backend/.env 에 Vertex 설정 (VERTEX_AI_PROJECT_ID, VERTEX_AI_LOCATION) + ADC 로그인
#   gcloud auth application-default login
#   gcloud auth application-default set-quota-project <PROJECT_ID>

# 한 이터레이션의 모든 통신문 × 3언어 실행
.venv/bin/python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/<DATE>_iter-<NNN>/

# 특정 통신문/언어만 (예: 실패분 재시도)
.venv/bin/python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/<DATE>_iter-<NNN>/ \
  --only n02-field-trip-consent --langs en,ru

# 검증기 단위 테스트 (backend 디렉터리 기준)
cd backend && ../.venv/bin/python -m unittest tests.test_translation_validators -q
```

> Vertex의 gemini-2.5-flash 분당 쿼터가 빡빡해 풀 18-run마다 일부가 `429 RESOURCE_EXHAUSTED`로
> 실패할 수 있다. `--only`로 실패분만 간격을 두고 재시도하면 대부분 복구된다.

---

## 6. 남은 과제 (선택)

- 잔여 `admin_review_required`의 근본 원인은 번역 품질이 아니라 **검증 단계의 LLM target fact 추출 run-to-run 변동**이다.
  다음 지렛대는 **target fact 추출기 정규화 강화**(추출 일관성 ↑ → 게이트 통과율 ↑).
- 러시아어처럼 다른 언어(중국어·베트남어 등)를 추가할 때는 `LANGUAGE_PROFILES`에 슬롯을 채우고
  `language-criteria/<lang>.md`를 먼저 작성한 뒤 이터레이션 루프로 검증한다.
