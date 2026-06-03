# Changes Summary — Iter-002 (리뷰용)

3 Change Sets, 2 코드 파일 + 1 테스트 파일. 검증의 *의미*는 불변, source/target 정규화 비대칭만 dates/times/grade로 확장 교정(iter-001 CS#1 계열). prompts는 en/ar 전용 룰만 추가(ru 격리).

## backend/app/translation/validators.py (Change Set #1 — 핵심)

| 위치 | 변경 | 의도 |
|---|---|---|
| `validate_hard_facts_by_code` | `dates`+`deadlines`를 하나의 절대일자 풀로 합쳐 비교, 루프에서 `deadlines`는 풀에 접혀 skip | 같은 날짜가 dates↔deadlines로 분류돼도 위양성 방지 |
| `_date_fact_set` (재작성) | 절대 `YYYY-MM-DD`만 비교. 학년도/맨연도/연-월/상대·퍼지 토큰은 게이트 제외(이전 literal 폴백 삭제) | 비-절대 토큰 위양성 제거, 진짜 절대일자 누락은 FAIL 유지 |
| `_time_fact_set` / `_extract_clock_times` (신규) | `times`를 시각 `HH:MM`만 비교(범위는 양끝 분해), 소요시간(`40 minutes`/`분`)은 제외 | 시각↔소요시간 분리, duration 위양성 제거, 시각 변경은 FAIL 유지 |
| `_grade_target_set` (재작성) | 학년 토큰만 비교. class 라벨·prose 자격요건은 게이트 제외 | 표 헤더(반)↔대상학년 분리, 한국어 prose 위양성 제거, 학년 누락은 FAIL 유지 |
| `_extract_grade_tokens` (재작성) | 한 항목의 *모든* 학년 추출: 콤마 리스트/서수 리스트/`N학년`/`grade:N` | `grades 1,2,3`·`1st,2nd,3rd grade`를 전부 잡아 source/target 대칭 |
| `_normalized_set_for_field` | `times`→`_time_fact_set` 라우팅 추가 | 필드별 대칭 정규화 |
| `_normalize_fee` + `_NO_COST_PHRASE_MARKERS` (신규 상수) | free 동치에 "fully supported/funded/covered/전액 지원/무상" 추가 | 무료를 funding-model prose로 푼 경우 흡수, 금액 변경은 FAIL 유지 |

dates 범위↔개별 동치는 기존 `_extract_iso_dates`가 양끝을 추출 → 그대로 활용.

## backend/app/translation/prompts.py

**Change Set #2 (en 전용):**
- `EN_TARGET_RULES`에 "Table column structure" 1항 추가 — 단일 표를 하나의 표로(열·행 수 보존), 표 2분할/행 셀 분리 금지, 관련 셀은 한 행 유지, source 열 순서 재현. (en 라우팅 유지, ru/ar 미주입)

**Change Set #3 (ar 전용):**
- `AR_TARGET_RULES` (신규 상수) — 라벨-값 라인 구조 보존, 인접 라인 정보 융합 금지(문의↔접수 이메일), 긴 행정 복합문 분절, 접근가능 MSA·사실 추가/이동 금지.
- `_target_language_specific_rules` — `target_language=="ar"` 분기 추가. en/ru 동작 불변(ru는 여전히 빈 문자열 = 격리).

## backend/tests/test_translation_validators.py (Change Set #1 회귀 보호)

신규 8건:
- **위양성 교정(PASS):** `ignores_academic_year_token`, `ignores_bare_year_and_year_month`, `accepts_date_migrated_between_dates_and_deadlines`, `ignores_duration_keeps_clock_times`, `separates_class_labels_from_target_grades`, `ignores_prose_only_eligibility_targets`, `accepts_free_equals_fully_supported`
- **음성(여전히 FAIL):** `still_fails_for_changed_clock_time`, `still_fails_for_dropped_target_grade`

## 검증 결과

- **단위 테스트:** `test_translation_validators` 20/20 + `test_translation_orchestrator` 2/2 = 22/22 PASS (`.venv/bin/python -m unittest`, pytest 미설치). (저장소 전체 discover는 무관한 `test_hwp_extractor`가 PIL 미설치로 import 실패 — 본 변경과 무관.)
- **n02 스모크 (Vertex AI gemini-2.5-flash, 3언어, 462s, 429 없음):**

| lang | before | after | hard_fact | 비고 |
|---|---|---|---|---|
| en | admin_review_required | admin_review_required | failed | `2026학년도` 위양성 제거됨. 잔여 `2026-06-01`·세분 fees는 **추출기 변동**(정규화 비대칭 아님) |
| ru | admin_review_required | **ready_to_save** | **passed (0 mismatch, 0 fix)** | ✅ 정규화 확장 효과 확인 |
| ar | admin_review_required | admin_review_required | failed | `2026학년도` 제거됨. 잔여 `2026-06-01`은 target 추출기가 마감을 ISO 미정규화 |

- 베이스라인: `notices/training/n02-field-trip-consent/pipeline-output-baseline/{en,ru,ar}.json`에 개선 전 보존.
- **핵심 발견:** 정규화 확장은 의도대로 작동(ru 완전 PASS, 학년도/연-월 토큰 제거). en/ar 잔여 FAIL은 **LLM target 추출기 run-to-run 변동**(6/1 마감 ISO 미추출, 세분 금액의 prose화)으로, validators.py 범위 밖. iter-003 풀런에서 추출기 일관 시 PASS 전환 기대. 다음 지렛대는 `extract_target_hard_facts_prompt` 정규화 강화(improvement-plan §4).
- 전체 18-run 미실행(quota 절약, team-lead iter-003 담당).
