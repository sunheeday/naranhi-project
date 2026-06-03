# Improvement Plan — Iter-001

**Verdict:** `ready_for_re_evaluation`
**Iteration:** 001
**Date:** 2026-06-02
**Based on:** `evaluation/feedback-report.md`

---

## 1. Summary

- **다룬 이슈 번호:** Issue #1 (hard_fact 검증 위양성), Issue #2 (영어 직역체), Issue #3 (한국 학교 개념·표 항목 의미 미해소)
- **보류한 이슈 번호:** Issue #4 (ru/ar 구두점·고유명 미세 표기) — low, 측정 분리 위해 다음 이터로 이월
- **Change Set 수:** 3개 (5개 이하)
- **변경 파일:** `backend/app/translation/validators.py`, `backend/app/translation/prompts.py`, `backend/tests/test_translation_validators.py`
- **신규 모듈:** 없음 (en 룰은 prompts.py 내 라우팅 헬퍼로 추가 — agent-spec의 "override 라우팅" 권장 패턴)
- **재실행 결과:** n01 스모크 1회 실행, `pipeline-output/` 갱신 + `pipeline-output-baseline/`에 개선 전 보존 완료. 전체 18-run은 quota 절약을 위해 미실행(team-lead iter-002 담당).

## 2. Change Sets

### Change Set #1 — hard_fact 정규화 대칭화 (전화번호 canonical / free=0 동치 / URL canonical / 연락처 prose 제외)

- **해결하는 피드백:** Issue #1 (최대 지렛대)
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/validators.py`
  - 함수: `_extract_contact_tokens`(+신규 `_canonical_phone_digits`), `_contact_fact_set`, 신규 `_url_fact_set` / `_extract_urls`, 신규 `_fee_fact_set` / `_normalize_fee`, `_normalized_set_for_field` 라우팅, 신규 상수 `_FREE_OF_CHARGE_TOKENS`
  - 변경 요약:
    1. **전화번호 대칭화** — source 국가형(`032-...` → `0323200096`)과 target 국제형(`+82 32-...` → `82323200096`)을 한 canonical 키로 수렴. `82` 국가코드를 제거하고 국가 trunk `0`을 복원. 비한국 번호는 그대로 둠.
    2. **free = 0 = 무료 동치 클래스** — source `free`/`무료`와 target `0`/`0 KRW`/`Бесплатно`/`مجانية` 등을 단일 `free` 토큰으로 매핑. 유료 금액은 숫자 추출로 비교(`amount:<digits>`)해 통화기호·공백차 위양성 제거.
    3. **URL canonical 비교** — scheme+host 소문자화, trailing slash 제거, path는 대소문자 보존. host 케이싱/슬래시 차이는 흡수하되 경로/도메인 변경은 여전히 FAIL.
    4. **연락처 prose 제외** — 기관명만 있는 연락처(`인천광역시교육청 안전복지과` 등 번호·이메일 없음)는 source는 한국어, target은 번역어라 문자 비교가 항상 어긋난다. 이 결정적 게이트에서는 machine-verifiable 토큰(전화/이메일/URL)만 비교하고 prose는 LLM/context-tone 단계에 위임.
- **왜 이렇게 했는가:** 평가자가 지목한 위양성 4종(전화 +82, 무료→0, 날짜범위 병합, 연락처 묶음/분해)의 근본 원인은 source/target 정규화 비대칭. 날짜범위는 이미 `_extract_iso_dates`로 동치 처리됨(기존 테스트 통과 확인). 나머지 3종을 대칭화. 검증 *의미*(어떤 사실이 보존돼야 하는가)는 바꾸지 않고, 같은 사실을 같은 규칙으로 정규화하도록만 교정 → 평가 기준 변경이 아닌 위양성 교정.
- **기대 효과:** admin_review_required 폭증 해소 → 18건 중 다수 FAIL→PASS. ship 가능성/운영 신뢰도 게이트 정상화. (rubric Fact 점수 직접 상승은 아니나 파이프라인 통과율 급상승.)
- **회귀 리스크:** 낮음. (a) 실제로 다른 전화번호인데 우연히 같은 canonical로 수렴할 확률은 거의 없음(전체 자릿수 비교). (b) 유료 금액 변경·URL 경로 변경·새 날짜 추가는 여전히 FAIL로 잡힘(음성 테스트로 보장). 잠재 위험: 기관명만 있는 연락처가 통째로 누락돼도 결정적 게이트는 통과 → 단, 그 케이스는 context_tone(LLM) 단계가 잡는다.
- **검증 방법:** 단위테스트 7건 신규(위양성 4 + 음성 회귀 3) 전부 통과. n01 스모크: 3언어 모두 admin_review_required → ready_to_save, hard_fact passed.
- **상태:** `applied`

### Change Set #2 — 영어 전용 register / anti-literal 룰 (target==en 라우팅)

- **해결하는 피드백:** Issue #2
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/prompts.py`
  - 함수: `translate_en_to_target_prompt`(주입), 신규 헬퍼 `_target_language_specific_rules`, 신규 상수 `EN_TARGET_RULES`
  - 변경 요약: `target_language == "en"`일 때만 en.md 기반 룰 블록 주입 — register lock(법무체 금지), parent-facing action을 "Make sure your child ..." / "Please talk with your child about ..." 형태로 재구성, 직역 안티패턴 명시("Confirm helmet wearing"/"Prohibit ..."/"converse with them" 금지), 시간 형식 통일("AM 9" 금지), 한국 전화번호 국가형 유지, 의례 인사 처리. ru/ar에는 주입 안 됨(라우팅으로 격리).
- **왜 이렇게 했는가:** agent-spec 권장 "공통 함수 유지 + 언어별 override 라우팅" 패턴. ru/ar은 이미 톤 최고(4.x)라 건드리지 않고 en만 분리해 효과를 측정 가능하게 함.
- **기대 효과:** en Naturalness/Culture/Action 동시 상승, en train_avg 4.2 근처 목표.
- **회귀 리스크:** 낮음~중간. 룰이 강해 의역이 과해질 수 있으나 "사실 추가 금지"를 명시. 과적합 시 rollback candidate.
- **검증 방법:** 라우팅 단위 검증(en 룰 주입/ru 미주입 assert 통과). n01 en 스모크에서 본문 다수가 자연 영어로 전환됨. **부분 잔존**: ☑ 체크리스트 2줄("Confirm helmet use." / "Instruct against riding ...")은 여전히 직역투 — 모델이 ☑ 리스트를 verbatim 체크리스트로 취급. 추가 강화 필요(아래 Deferred 참조).
- **상태:** `partially_applied` (본문은 개선, ☑ 체크리스트 항목 일부 잔존)

### Change Set #3 — 한국 학교 개념·맥락 의존 표 항목 의미 해소 (3언어 공통, 피벗 단계)

- **해결하는 피드백:** Issue #3
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/prompts.py`
  - 함수: `translate_ko_to_en_pivot_prompt` (Meaning-resolution rules 블록 추가)
  - 변경 요약: (1) 짧은 표 셀/리스트/제목은 인접 행·열·섹션 맥락과 함께 읽어 *의도된 의미*로 번역 — "신호등을 지켜라"(영양 신호등)를 도로 신호로 오역하지 말 것을 명시. (2) 한국 학교/행정 고유 개념(수련회·알림장·돌봄교실·방과후·체험학습·학예회)은 기능을 풀어쓰고 필요시 원어 병기("overnight school camp (수련회)") — fact 추가가 아닌 의미 해소이며 날짜·비용 등 신규 사실 발명 금지.
- **왜 이렇게 했는가:** 피벗(영어 의미 백본)이 세 언어 모두에 전파되므로 여기서 의미를 고정하면 en/ru/ar Culture 축이 동시 개선. ar/ru의 도로신호 오역도 피벗에서 의미가 잡히면 함께 해소.
- **기대 효과:** Culture & Linguistic 축 3언어 동시 상승 (en 3.75, ar 4.0 등).
- **회귀 리스크:** 낮음~중간. "원어 병기 + 1구 보충" 허용이 과해지면 부수 설명 추가로 흐를 수 있음. "신규 사실 발명 금지"를 명시해 가드. 과적합 신호 시 rollback candidate.
- **검증 방법:** 피벗 프롬프트에 룰 주입 확인(assert 통과). n06(health-class)에서 효과 측정은 iter-002 풀런에서. n01 스모크에는 해당 표 항목 없음.
- **상태:** `applied`

## 3. Deferred (이번에 적용하지 않은 피드백)

### Deferred Issue #4 — ru/ar 한국식 중점(·)·카카오 채널명 한글 잔존

- **사유:** low 심각도. 이번 3개 Change Set의 효과를 깨끗이 측정하기 위해 ru/ar 프롬프트는 의도적으로 손대지 않음(ru/ar은 이미 톤 최고).
- **다음 이터레이션 권고:** iter-002에서 Change Set #2/#3 효과 확인 후, 구두점 정규화(en `,`/`/`, ar `،`)와 검색 키워드형 고유명 "음역(원어)" 병기 룰을 ru/ar 전용으로 추가.

### 추가 잔존 (Change Set #2 부분 적용)

- **☑ 체크리스트 항목 직역 잔존:** en 안전 체크리스트의 ☑ 항목("Confirm helmet use.")이 여전히 명사·명령 직역. 다음 이터에서 "☑/체크리스트 항목도 보호자 행동 동사형으로 재구성하라"를 EN_TARGET_RULES에 한 줄 더 명시하거나, 안전 체크리스트 전용 변환 예시를 추가 권고.

## 4. Proposed for Next Iteration

- en 효과 확인 후 ru → ar 순으로 언어별 분리 도입(구두점/고유명 병기).
- 검증 보조 신호: final_translation 본문에 hard fact가 텍스트로 포함됐는지 확인하는 보조 체크(평가자 권고)를 결정적 게이트에 추가하면 위양성 완화 + 진짜 누락 탐지 강화 가능. 이번엔 정규화 대칭화로 충분해 보류.

## 5. Backward Compatibility / Schema

- 데이터 스키마 변경 여부: 없음 (`HARD_FACT_SCHEMA` 불변)
- `TranslationPipelineInput` 시그니처 변경: 없음
- Supabase 컬럼 영향: 없음

## 6. Rubric / Criteria 변경 제안

- 직접 변경 없음. 평가자가 제기한 "검증 status와 Fact 축 점수 분리", "meal=N/A 가중평균 처리 명문화"는 rubric 소관이며 본 엔지니어 변경과 무관(사용자/평가자 결정 사항).

## 7. Re-run Result Summary (n01 스모크)

| 항목 | before | after | 변화 |
|---|---|---|---|
| en status | admin_review_required | ready_to_save | ✅ 통과 |
| ru status | admin_review_required | ready_to_save | ✅ 통과 |
| ar status | admin_review_required | ready_to_save | ✅ 통과 |
| en hard_fact | failed(위양성) | passed | ✅ |
| ru hard_fact | failed(위양성) | passed | ✅ |
| ar hard_fact | failed(위양성) | passed | ✅ |
| en final_translation 길이 | 2269 | 2195 | 유사 |
| ru final_translation 길이 | 2720 | 2559 | 유사 |
| ar final_translation 길이 | 2093 | 2071 | 유사 |
| 전화 `032-320-0096` 보존 | (게이트 차단) | 3언어 모두 보존, +82 없음 | ✅ |
| en action 자연화 | 직역 다수 | 본문 대부분 자연 영어, ☑ 2줄 잔존 | 부분 개선 |

전체 점수 산정은 iter-002에서 평가자가 수행.

## 8. Files Changed

- `backend/app/translation/validators.py` — Change Set #1
- `backend/app/translation/prompts.py` — Change Set #2, #3
- `backend/tests/test_translation_validators.py` — Change Set #1 회귀/위양성 테스트 7건 추가

`changes-summary.md`에 함수 단위 diff 요약.

## 9. Handoff

- **반드시 확인할 것:** (1) hard_fact 통과율이 18건 전반에서 올랐는지(특히 n02/n05/n06의 무료·전화·URL). (2) en Naturalness/Culture/Action 상승 여부. (3) Culture 축이 ru/ar에서도 피벗 의미 룰 덕에 올랐는지.
- **회귀 watch:** (a) en 룰 강화로 Fact/Completeness가 의역 때문에 깎이지 않았는지. (b) 피벗 의미 해소 룰이 부수 설명 추가(사실 추가)로 흐르지 않았는지. (c) 유료 통신문이 있으면 fee canonical이 진짜 금액 변경을 놓치지 않는지.
- **rollback candidate:** 과적합 신호 시 Change Set #2(en 룰) 우선, 다음 #3(피벗 의미 룰). #1(validator)은 위양성 교정이라 rollback 비대상.
