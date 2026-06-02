# Changes Summary — Iter-001 (리뷰용)

3 Change Sets, 2 코드 파일 + 1 테스트 파일. 검증의 *의미*는 불변, source/target 정규화 비대칭 버그만 교정.

## backend/app/translation/validators.py (Change Set #1 — 최대 지렛대)

| 위치 | 변경 | 의도 |
|---|---|---|
| `_FREE_OF_CHARGE_TOKENS` (신규 상수) | "free/무료/0/0 krw/Бесплатно/مجانية" 등 무료 표현 집합 | free=0=무료 동치 |
| `_normalized_set_for_field` | `urls`→`_url_fact_set`, `fees`→`_fee_fact_set` 라우팅 추가 | 필드별 대칭 정규화 |
| `_contact_fact_set` | machine-verifiable 토큰(전화/이메일/URL)만 비교, prose 폴백 제거 | 기관명 한국어↔번역어 위양성 제거 |
| `_extract_contact_tokens` | 전화 토큰을 `_canonical_phone_digits`로 정규화, URL도 토큰화 | +82 ↔ 0 국가형 수렴 |
| `_canonical_phone_digits` (신규) | `82` 국가코드 제거 + 국가 trunk `0` 복원 | source/target 전화 canonical |
| `_url_fact_set` / `_extract_urls` (신규) | scheme+host 소문자, trailing slash 제거, path 보존 | URL 케이싱/슬래시 차 흡수, 경로변경은 FAIL 유지 |
| `_fee_fact_set` / `_normalize_fee` (신규) | 무료→`free`, 유료→`amount:<digits>` | 통화기호/공백 위양성 제거, 금액변경은 FAIL 유지 |

날짜범위 병합(`A~B` vs `A,B`)은 기존 `_extract_iso_dates`가 이미 동치 처리 → 변경 불필요(기존 테스트 통과 확인).

## backend/app/translation/prompts.py

**Change Set #2 (en 전용):**
- `EN_TARGET_RULES` (신규 상수) — register lock(법무체 금지) + parent-facing action 자연화("Make sure your child ...") + 직역 안티패턴 금지("Confirm helmet wearing"/"Prohibit ..." 등) + 시간형식 통일 + 전화 국가형 유지 + 인사 처리.
- `_target_language_specific_rules` (신규 헬퍼) — `target_language=="en"`일 때만 주입(ru/ar 격리).
- `translate_en_to_target_prompt` — 위 헬퍼 결과를 룰 블록에 삽입.

**Change Set #3 (3언어 공통, 피벗):**
- `translate_ko_to_en_pivot_prompt` — "Meaning-resolution rules" 블록 추가: 표/리스트 항목을 맥락과 함께 의도된 의미로 번역(영양 신호등≠도로신호), 한국 학교 개념 풀어쓰기+원어 병기(신규 사실 발명 금지).

## backend/tests/test_translation_validators.py (Change Set #1 회귀 보호)

신규 7건:
- 위양성 교정: `phone_international_vs_national_form`, `org_name_only_contact`, `free_equals_zero_krw`, `free_equals_arabic_majjani`, `url_trailing_slash_and_host_case`
- 음성(여전히 FAIL): `changed_fee_amount`, `changed_url_path`

## 검증 결과

- **단위테스트:** `test_translation_validators` + `test_translation_orchestrator` = 13/13 PASS (`python -m unittest`, pytest 미설치).
- **n01 스모크 (Vertex AI gemini-2.5-flash, 3언어, 296s, 429 없음):**

| lang | before | after | hard_fact | context_tone |
|---|---|---|---|---|
| en | admin_review_required | ready_to_save | passed | passed |
| ru | admin_review_required | ready_to_save | passed | passed |
| ar | admin_review_required | ready_to_save | passed | passed |

- 전화 `032-320-0096` 3언어 모두 본문 보존, `+82` 미출현.
- en 본문 다수가 자연 영어로 전환. **잔존:** ☑ 체크리스트 2줄("Confirm helmet use." / "Instruct against riding ...") 직역투 → Change Set #2 `partially_applied`, iter-002 추가 강화 권고.
- 베이스라인: `notices/training/n01-bike-safety/pipeline-output-baseline/{en,ru,ar}.json`에 개선 전 보존.
- 전체 18-run 미실행(quota 절약, team-lead iter-002 담당).
