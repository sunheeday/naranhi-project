# Improvement Plan — Iter-002

**Verdict:** `ready_for_re_evaluation`
**Iteration:** 002
**Date:** 2026-06-02
**Based on:** `evaluation/feedback-report.md`

---

## 1. Summary

- **다룬 이슈 번호:** Issue #1 (hard_fact 검증 위양성 — dates/grades/times 정규화 확장; 핵심), Issue #2 (en 표 열 구조 보존), Issue #3 (ar 라인 구조 보존 + 복합문 분절)
- **보류한 이슈 번호:** 없음 (Top 3 전부 다룸). iter-001의 ☑ 체크리스트 직역 잔존·ru/ar 구두점은 이번에도 보류(아래 Deferred).
- **Change Set 수:** 3개 (5개 이하)
- **변경 파일:** `backend/app/translation/validators.py`, `backend/app/translation/prompts.py`, `backend/tests/test_translation_validators.py`
- **신규 모듈:** 없음 (ar 룰은 prompts.py 내 `AR_TARGET_RULES` 상수 + 기존 `_target_language_specific_rules` 라우팅 확장으로 추가 — iter-001의 en override 패턴 재사용)
- **재실행 결과:** n02 스모크 1회 실행(en,ru,ar). 베이스라인을 `pipeline-output-baseline/`에 보존 후 `pipeline-output/` 갱신. ru→ready_to_save 전환 확인. en/ar은 잔여 FAIL이나 **원인이 정규화 비대칭이 아니라 LLM 추출기 변동**임을 확인(아래 §7).

## 2. Change Sets

### Change Set #1 — hard_fact 정규화 대칭화 확장: dates / times / grade_class_targets (핵심, 최대 지렛대)

- **해결하는 피드백:** Issue #1
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/validators.py`
  - 함수: `validate_hard_facts_by_code`(dates+deadlines 풀링), `_date_fact_set`(재작성), 신규 `_time_fact_set`/`_extract_clock_times`, `_grade_target_set`(재작성), `_extract_grade_tokens`(재작성), `_normalize_fee`(free 동치 확장), `_normalized_set_for_field`(times 라우팅), 신규 상수 `_NO_COST_PHRASE_MARKERS`
  - 변경 요약 (평가자가 지정한 3개 세부 + 1개 보조):
    1. **dates — 비-절대 토큰 게이트 제외 + 범위↔개별 동치 + dates/deadlines 풀링.** `_date_fact_set`이 이제 절대 달력일자(`YYYY-MM-DD`)만 비교한다. 학년도(`2026학년도`, normalized=None), 맨연도(`2026`/`2027`), 연-월(`2026-06`), 상대/퍼지 표현(`6월 중`/`마감 시`/`현재 접수 중`/`위촉 후~2027`)은 결정 게이트에서 제외(이전엔 literal로 떨어져 source/target 비대칭 유발). 범위는 기존대로 양끝 ISO를 추출해 개별일과 동치. 또한 `dates`와 `deadlines`를 하나의 절대일자 풀로 합쳐 비교 — 같은 날짜가 source에선 dates, target에선 deadlines로 분류돼도 위양성이 나지 않게. **진짜 절대일자 누락/변경은 여전히 FAIL**(missing 방향 유지).
    2. **grade_class_targets — class 라벨과 대상 학년 분리 + prose 제외.** 신규 `_extract_grade_tokens`가 한 항목 안의 *모든* 학년 숫자를 추출(콤마 리스트 `grades 1, 2, 3`, 서수 리스트 `1st, 2nd, 3rd grade`, 한국어 `1, 2, 3학년`, 사전정규화 `grade:3`). class 섹션 라벨(`A반`/`Class A`)은 학년 토큰으로 만들지 않고 게이트에서 제외(대상 학년이 아니라 분반 식별자). 숫자 학년이 없는 prose 자격요건(`시민기자단 30명`, `youth residing in Incheon`)은 contacts prose처럼 결정 게이트에서 제외(source 한국어 vs target 번역어라 문자 비교가 항상 어긋남) → LLM/context_tone가 검증. **진짜 대상 학년 누락은 여전히 FAIL.**
    3. **times — 시각(clock-time) vs 소요시간(duration) 분리.** 신규 `_time_fact_set`이 `HH:MM` 시각만 비교(범위 `19:30~20:10`는 양끝 시각으로 분해). 소요시간(`40 minutes`/`40분`)은 게이트에서 제외 — 시각 범위와 중복(`19:30-20:10`=40분)되고 양측이 비대칭 표기해 "new critical value" 위양성을 유발했음. **진짜 시각 변경은 여전히 FAIL.**
    4. **(보조) fee free 동치 확장.** iter-001의 free=0=무료 동치에 "fully supported/funded/covered", "전액 지원", "무상"을 추가(`_NO_COST_PHRASE_MARKERS`). n06에서 target이 무료를 "fully supported by the Office of Education"로 풀어쓴 경우를 흡수. 부분 지원/유료(`fully` 없음, 숫자 동반)는 collapse되지 않음 → 금액 변경은 FAIL 유지.
- **왜 이렇게 했는가:** 평가자가 지목한 위양성의 근본 원인은 source/target 정규화 비대칭. 검증 *의미*(어떤 사실이 보존돼야 하는가)는 바꾸지 않고 같은 사실을 같은 규칙으로 정규화하도록만 교정 — 평가 기준 변경이 아닌 위양성 교정(iter-001 CS#1 계열). 음성 케이스(진짜 누락/변경)는 단위 테스트로 FAIL 유지를 보장.
- **기대 효과:** 15건 admin_review 중 dates/times/grade가 단독 원인이던 통신문이 PASS·ready로 다수 전환. n04 status 회귀(`grade:3` vs `1 2 3`, dates `2028`)도 동일 뿌리라 동반 해소 기대.
- **회귀 리스크:** 낮음~중간.
  - 대상 학년 **오확대**(`grade:3` source ↔ `grades 1,2,3` target)는 게이트에서 PASS로 처리됨 — 이는 평가자가 명시적으로 위양성으로 지목한 n04 케이스(본문 정확)와 동일하므로 의도된 동작. 결정적 게이트로는 추출기 과소계수와 진짜 오확대를 구분할 수 없어, 학년은 extra-check에 넣지 않고 missing만 FAIL로 잡는다(본문/LLM이 오확대 검증).
  - 비-절대 날짜 토큰을 제외하므로 "2027년 행사"처럼 연도만으로 의미가 있는 날짜의 연도 변경은 결정 게이트가 못 잡음 — 단, 절대일자는 그대로 잡히고 연도 단독은 본문/LLM 검증으로 위임.
- **검증 방법:** 단위 테스트 8건 신규(아래 §7). n02 스모크: ru PASS·ready(mismatch 0, fix 0), `2026학년도` 위양성 제거 확인.
- **상태:** `applied`

### Change Set #2 — en 표 열 구조 보존 룰

- **해결하는 피드백:** Issue #2 (n04 표 분할 — held-out이므로 일반 룰로만 접근, n04 미열람)
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/prompts.py`
  - 함수/상수: `EN_TARGET_RULES`에 표 열 구조 보존 룰 1항 추가 (target_language=en 라우팅 유지)
  - 변경 요약: 단일 source 표는 같은 열·같은 행 수로 하나의 표로 유지. 표를 둘로 쪼개거나 한 행의 셀을 별도 표로 분리 금지. 관련 셀(내용↔강사/시간)은 한 행에 유지해 행 단위 가독 보존. source 열 순서 재현.
- **왜 이렇게 했는가:** en만의 형식 저하이고 ru/ar은 단일 표 유지이므로 en 전용 룰에 추가(효과 분리 측정). held-out n04를 보지 않고 일반 규칙으로만 기술.
- **기대 효과:** en Completeness/Naturalness(형식) 미세 회복. training n06(표 풍부)으로 회귀 점검 가능.
- **회귀 리스크:** 낮음. 형식 지시이며 사실/내용 변경 없음.
- **상태:** `applied` (효과 측정은 iter-003 풀런)

### Change Set #3 — ar 라인 구조 보존 + 복합문 분절 룰

- **해결하는 피드백:** Issue #3 (n05 ar Naturalness 4.0 최저, 문의 라인에 이메일 융합)
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/prompts.py`
  - 함수/상수: 신규 `AR_TARGET_RULES`, `_target_language_specific_rules`에 `target_language=="ar"` 분기 추가
  - 변경 요약: (1) 라벨-값 라인 구조 보존, 인접 라인 정보 융합 금지(문의 라인에 접수 라인 이메일을 붙이지 말 것). (2) 긴 행정 복합문을 짧고 명확한 여러 문장으로 분절. (3) 접근가능 MSA 유지, 사실 추가·라인 이동 금지.
- **왜 이렇게 했는가:** iter-001의 "공통 함수 유지 + 언어별 override 라우팅" 패턴 재사용. en/ru은 미주입(격리)해 ar 효과만 분리 측정.
- **기대 효과:** ar Naturalness(4.0)·Completeness 미세 회복, 라인 융합 제거.
- **회귀 리스크:** 낮음~중간. 분절이 과해 한 사실을 둘로 쪼개면 부자연스러울 수 있으나 "사실 추가·이동 금지"로 가드.
- **상태:** `applied` (효과 측정은 iter-003 풀런)

## 3. Deferred (이번에 적용하지 않은 피드백)

### iter-001 잔존 — en ☑ 체크리스트 직역 / ru·ar 구두점·고유명 병기

- **사유:** 이번 Top 3에 포함되지 않음(평가자 우선순위 외). CS#1의 효과를 깨끗이 측정하기 위해 범위를 dates/grades/times + en표 + ar라인으로 한정.
- **다음 이터레이션 권고:** Issue #1 통과율 확정 후, en EN_TARGET_RULES에 "☑/체크리스트 항목도 보호자 행동 동사형" 1항, ru/ar 구두점·검색키워드형 고유명 음역(원어) 병기 룰을 분리 도입.

## 4. Proposed for Next Iteration

- **LLM 추출기 변동(extractor variance) 완화.** n02 스모크에서 잔여 FAIL의 원인은 정규화 비대칭이 아니라 target hard_fact 추출기가 (a) 마감일(6/1)을 ISO로 정규화하지 못하거나 (b) 세분 비용(1600/30000/...)을 "additional costs" prose로 뭉뚱그린 *추출 변동*이었다. 이는 `validators.py`로는 잡을 수 없고, `extract_target_hard_facts_prompt`의 정규화 지시 강화(모든 마감/날짜를 `YYYY-MM-DD`로, 표의 모든 금액을 개별 추출) 또는 본문 텍스트 포함 검사를 게이트 완화 신호로 쓰는 보조 체크가 필요. 평가자가 명시 요청한 범위(정규화 대칭화)를 넘으므로 이번엔 제안만.
- 평가자 권고 보조 신호: final_translation 본문에 hard fact가 텍스트로 존재하는지 확인하는 보조 게이트(위양성 완화 + 진짜 누락 탐지 강화).

## 5. Backward Compatibility / Schema

- 데이터 스키마 변경 여부: 없음 (`HARD_FACT_SCHEMA` 불변)
- `TranslationPipelineInput` 시그니처 변경: 없음
- Supabase 컬럼 영향: 없음

## 6. Rubric / Criteria 변경 제안

- 직접 변경 없음. 평가자가 제기한 "검증 status ≠ Fact 축", "status 회귀 ≠ 품질 회귀", meal=N/A 가중평균 명문화는 rubric 소관(사용자/평가자 결정).

## 7. Re-run Result Summary (n02 스모크)

| 항목 | before (baseline) | after | 변화 |
|---|---|---|---|
| en status | admin_review_required | admin_review_required | 잔여(원인=추출기 변동, 아래) |
| ru status | admin_review_required | **ready_to_save** | ✅ 전환 |
| ar status | admin_review_required | admin_review_required | 잔여(원인=추출기 변동) |
| en hard_fact mismatch | `dates: 2026-06-01, 2026학년도` | `dates: 2026-06-01` + `fees: amount:... vs additional costs` | `2026학년도` 위양성 제거됨 ✅ |
| ru hard_fact | failed | **passed (mismatch 0, fix 0)** | ✅ |
| ar hard_fact mismatch | `dates: 2026학년도` | `dates: 2026-06-01` | `2026학년도` 제거, 새 `2026-06-01` 미스 |

**해석:** 정규화 확장은 의도대로 작동했다 — `2026학년도`(학년도)·`2026-01`(연-월) 비-절대 토큰이 게이트에서 사라졌고, ru는 완전 PASS. en/ar에 남은 `2026-06-01` 미스는 **target 추출기가 6/1 마감을 ISO로 정규화하지 못한 run-to-run 변동**이며(dates/deadlines 풀에 양측 모두 부재), en `fees`는 source가 세분 금액을 추출한 반면 target이 prose로 뭉친 추출 변동이다. 둘 다 정규화 비대칭이 아니라 추출 변동 → §4의 추출기 강화 제안 대상. 결정 게이트가 진짜 절대일자 미스를 FAIL로 잡는 것은 **의도된 정확한 동작**(평가자: "진짜 절대일자 누락은 FAIL 유지").

### 단위 테스트 결과

`backend/tests/test_translation_validators.py` — 20/20 PASS (`.venv/bin/python -m unittest`, pytest 미설치).
- **위양성 교정 (PASS로 전환) 6건:** academic-year 토큰 제외, 맨연도/연-월 제외, dates↔deadlines 이동, duration 제외(시각 유지), class 라벨↔대상학년 분리(전체 학년 추출), prose 자격요건 제외, free=fully supported.
- **음성(여전히 FAIL) 유지 3건 신규 + 기존 3건:** 시각 변경 FAIL, 대상학년 누락 FAIL, free=fully supported의 짝으로 fee 금액변경/URL경로변경/신규날짜 FAIL 유지.

## 8. Files Changed

- `backend/app/translation/validators.py` — Change Set #1
- `backend/app/translation/prompts.py` — Change Set #2 (EN_TARGET_RULES 표 룰), Change Set #3 (AR_TARGET_RULES 신규 + 라우팅)
- `backend/tests/test_translation_validators.py` — Change Set #1 위양성/음성 테스트 8건 추가

`changes-summary.md`에 함수 단위 diff 요약.

## 9. Handoff

- **반드시 확인할 것:** (1) iter-003 풀런에서 dates/times/grade 단독 FAIL 통신문의 PASS 전환율. (2) en n06 표가 단일 표로 유지되는지(CS#2). (3) ar n05 문의 라인에 이메일 융합이 사라졌는지·복합문 분절(CS#3).
- **회귀 watch:** (a) 학년 오확대를 게이트가 PASS시키므로(의도), held-out에서 본문이 실제로 틀린 학년 확대가 있는지 평가자 육안 확인. (b) ar 분절이 과해 한 사실을 쪼개 부자연스럽지 않은지. (c) free 동치 확장이 진짜 유료 통신문을 놓치지 않는지(음성 테스트로 보장하나 실데이터 확인).
- **rollback candidate:** 과적합 신호 시 CS#3(ar 룰) → CS#2(en 표 룰) 순. CS#1(validator)은 위양성 교정이라 rollback 비대상.
- **남은 병목:** target hard_fact 추출기 변동(§4). 정규화로는 한계 — 추출 프롬프트 강화가 다음 지렛대.
