# Improvement Plan — Iter-codex-001

**Verdict:** `partial`
**Iteration:** `2026-06-02_iter-codex-001`
**Date:** `2026-06-02`
**Based on:** partial baseline outputs under `notices/*/pipeline-output/`

## 1. Summary

- **다룬 이슈:** `n01-bike-safety-checklist`의 en/ru/ar 직역체, `n02-field-trip-consent-fee`의 ru target fact extraction instability, human review 분기 제거, `n04-school-talent-show`의 ru/ar 제목 톤과 target fact extractor 규칙 보강, `n03-lunch-allergy-halal`의 unmapped critical ingredient 추정 번역 억제, dictionary-aware meal gate 및 per-notice ingredient dictionary 주입
- **보류한 이슈:** 없음
- **Change Set 수:** 5
- **변경 파일:** `backend/app/translation/prompts.py`, `backend/app/translation/orchestrator.py`, `backend/app/services/notice_service.py`, `backend/app/translation/validators.py`, `scripts/run_iteration.py`, `scripts/translation_quality_driver.py`
- **재실행 결과:** `n01-bike-safety-checklist` 3개 언어 재실행 완료, `n02-field-trip-consent-fee` ru 재실행 완료, `n04-school-talent-show` ru/ar 재실행 완료, `n03-lunch-allergy-halal` en/ru/ar dictionary-aware pass 확인

## 2. Change Sets

### Change Set #1 — Safety notice anti-literal prompt hardening

- **해결하는 피드백:** `n01-bike-safety-checklist`의 en/ru/ar 공통 직역체
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/prompts.py`
  - 함수/블록:
    - `translate_ko_to_en_pivot_prompt`
    - `translate_en_to_target_prompt`
    - `EN_TARGET_RULES`
    - `RU_TARGET_RULES`
    - `AR_TARGET_RULES`
  - 변경 요약:
    - Korean notice formula (`다시 안내드립니다`, `지도해 주시기 바랍니다`, `지속적으로 이야기해 주시기 바랍니다`, `안전사고 예방`)를 자연스러운 parent-facing phrasing으로 바꾸도록 예시 추가
    - `전동 킥보드` / safety notice title / caregiver-action frame 관련 anti-calque 규칙 추가
    - 아랍어에는 parent-guidance structure, one-line label-value, `سكوتر كهربائي`류의 범용 MSA 용어, explicit dismount wording 강화
    - target translation general rules에도 literal pivot repair 규칙 추가
- **왜 이렇게 했는가:**
  - `n01`은 `ready_to_save`였지만 품질상 직역 문제가 명확했고, 세 언어에 공통된 한국어 통신문 공식 패턴이 반복적으로 남아 있었다.
  - 단일 notice에서 en/ru/ar가 동시에 같은 실패 모드를 보여서 고레버리지 prompt fix라고 판단했다.
- **기대 효과:**
  - `Naturalness / Readability`
  - `Action Clarity`
  - `Tone & Register`
  - 아랍어의 `Cultural & Linguistic Appropriateness`
- **회귀 리스크:**
  - 안내문이 아닌 truly regulatory text에서도 parent-facing softening이 과도하게 적용될 수 있음
  - title naturalization이 source taxonomy를 지나치게 줄일 수 있음
- **검증 방법:**
  - `python3 -m py_compile backend/app/translation/prompts.py` 완료
  - `n01-bike-safety-checklist` 3개 언어 재실행 완료
  - before/after 확인:
    - en: `re-notifying` -> `we would like to remind you`, `electric kickboards` -> `e-scooters`, `Please continuously tell them` -> `Please keep reminding your child`
    - ru: `повторно информируем Вас` -> `хотели бы напомнить Вам`, `проинструктируйте` 계열 -> `проследите` / `регулярно напоминать`
    - ar: `لوح الركل الكهربائي` -> `السكوتر الكهربائي`, title `دليل` -> `إشعار`, contact line one-line 유지
- **상태:** `applied`

### Change Set #2 — Target fact extraction retry + no-human-review pipeline

- **해결하는 피드백:** `n02-field-trip-consent-fee` / ru에서 번역문은 정상인데 `target_hard_facts`가 비어 gate가 실패하던 케이스, 그리고 user request에 따른 human review 분기 제거
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/orchestrator.py`
  - 함수/블록:
    - `TranslationPipelineInput`
    - target hard-fact extraction 단계
    - `_validation_failed_result` 신규 경로
  - 파일: `backend/app/services/notice_service.py`
  - 변경 요약:
    - `extract_target_hard_facts_prompt` 결과가 비거나 critical field를 통째로 놓치면 자동 재시도하도록 추가
    - hard fact / context validation 실패 시 더 이상 `admin_review_required`로 반환하지 않고, `status=ready_to_save` + `metadata.validation_status=failed`로 계속 반환
    - fallback translation도 사람 검토 큐로 보내지 않고 동일 정책 적용
    - 저장 시 `requires_admin_review=false`로 고정하고, 실패 정보는 validation/metadata 쪽에만 남김
- **왜 이렇게 했는가:**
  - `n02 ru`는 번역 품질보다 extraction nondeterminism이 문제였고, 같은 번역문 재추출에서 정상 복구됨을 확인했다.
  - 사용자가 human review 프로세스를 제거해 달라고 명시적으로 요청했다.
- **기대 효과:**
  - `n02`/`n04` 계열 run-to-run extractor artifact 감소
  - 사람 검토 큐 없이도 파이프라인이 끝까지 결과를 저장
- **회귀 리스크:**
  - 검증 실패 번역도 저장되므로 downstream consumer가 `validation_status`를 반드시 봐야 함
  - false negative가 생기면 사람이 막아주던 안전장치가 사라짐
- **검증 방법:**
  - `python3 -m py_compile backend/app/translation/orchestrator.py backend/app/services/notice_service.py`
  - `PYTHONPATH=backend python3 -m unittest backend/tests/test_notice_service_school_only.py backend/tests/test_translation_validators.py`
  - `n02-field-trip-consent-fee` ru 재실행 결과:
    - before: `admin_review_required`, `target_hard_facts={}`
    - after: `ready_to_save`, `hard_fact=passed`, `target_hard_facts` populated
- **상태:** `applied`

### Change Set #3 — Target fact extractor hardening + notice-title cleanup

- **해결하는 피드백:** `extract_target_hard_facts_prompt`가 날짜/마감/제출물/학년 정보를 배열에 빠뜨릴 수 있는 구조적 약점, `n04-school-talent-show`의 ru/ar 제목이 `guide/manual` 쪽으로 기울던 문제
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/prompts.py`
  - 함수/블록:
    - `translate_en_to_target_prompt`
    - `extract_target_hard_facts_prompt`
    - `RU_TARGET_RULES`
    - `AR_TARGET_RULES`
  - 변경 요약:
    - target translation 단계에서 plain target-language school term으로 충분한 경우 한국어 원어 괄호를 다시 붙이지 않도록 일반 규칙 추가
    - extractor prompt에 table/list/label-value line 전체를 훑고, date/time/fee/contact/submission/grade가 보이면 corresponding array를 비워두지 말라는 self-check 규칙 추가
    - `by/until/до/بحلول`류 마감 표현은 `deadlines`에 반드시 넣도록 명시
    - 러시아어 제목 규칙을 `Информация ...` / `Уведомление ...` 계열로 강화하고 `Руководство ...` 금지
    - 아랍어 제목 규칙을 `إشعار ...` / `تنبيه ...` 계열로 강화하고 불필요한 `(알림장)` 병기 금지
- **왜 이렇게 했는가:**
  - `n02 ru`에서 확인한 extraction instability는 orchestrator retry만으로 막기보다 extractor prompt 자체도 더 구조적으로 만들어 두는 편이 안정적이다.
  - `n04`는 validation은 통과했지만 ru/ar 모두 title register와 한국어 괄호 용어가 parent-facing notice 품질을 깎고 있었다.
- **기대 효과:**
  - `Hard Fact Preservation`
  - `Naturalness / Readability`
  - `Tone & Register`
  - `Action Clarity`
- **회귀 리스크:**
  - 일부 문서에서 원어 병기가 실제로 필요한 경우까지 과하게 생략할 수 있음
  - extractor가 너무 공격적으로 facts를 채우면 중복 추출이 늘 수 있음
- **검증 방법:**
  - `python3 -m py_compile backend/app/translation/prompts.py`
  - `n04-school-talent-show` ru/ar 재실행 완료
  - before/after 확인:
    - ru: `Руководство ...` 제거, `(알림장)` 제거, `school notice` 계열 표현 유지
    - ar: title `دليل ...` -> `إشعار بخصوص ...`, `(알림장)` 제거
    - ru/ar 모두 `ready_to_save`, `hard_fact=passed`, `context_tone=passed`
- **상태:** `applied`

### Change Set #4 — Unmapped critical ingredient handling hardening

- **해결하는 피드백:** `n03-lunch-allergy-halal`에서 empty ingredient dictionary 상태일 때 `맛술`/`젤라틴`이 언어별로 제각각 추정 번역되거나 Markdown code formatting이 섞이던 문제
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/prompts.py`
  - 함수/블록:
    - `COMMON_SYSTEM_PROMPT`
    - `translate_ko_to_en_pivot_prompt`
    - `translate_en_to_target_prompt`
    - `fix_hard_facts_prompt`
    - `fix_context_tone_prompt`
  - 파일: `backend/app/translation/validators.py`
  - 변경 요약:
    - unmapped ingredient는 모든 단계에서 exact Korean token을 그대로 유지하고, 추정 번역/음역/설명 추가/code fence 사용을 금지
    - validator 추천 문구도 human review가 아니라 `preserve unmapped Korean ingredient tokens without guessing` 쪽으로 정렬
    - context/tone validation 및 metadata prompt 문구에서도 human-review 중심 표현을 줄이고 fail/unsafe 중심으로 정리 시작
- **왜 이렇게 했는가:**
  - `n03`는 현재 prompt를 아무리 좋아지게 해도 approved dictionary가 비어 있으면 validation은 실패해야 한다.
  - 하지만 user-facing 번역문은 그 와중에도 언어마다 임의 추정(`mirin`, backticks, mixed handling`) 없이 일관되게 안전해야 한다.
- **기대 효과:**
  - `Cultural & Linguistic Appropriateness`
  - `Hard Fact Preservation`
  - critical 식재료 관련 false confidence 감소
- **회귀 리스크:**
  - 최종 번역에 한국어 ingredient token이 남아 가독성이 떨어질 수 있음
  - dictionary 미비가 길어지면 product UX 차원에서 후속 표시 정책이 필요함
- **검증 방법:**
  - `python3 -m py_compile backend/app/translation/prompts.py backend/app/translation/validators.py`
  - `n03-lunch-allergy-halal` en/ru/ar 재실행 완료
  - before/after 확인:
    - en: `mirin (맛술)` 추정 설명 제거, `맛술`/`젤라틴` exact Korean token 유지
    - ru: `кулинарное вино` 추정 제거, `맛술`/`젤라틴` exact Korean token 유지
    - ar: backticks 제거, `맛술`/`젤라틴` exact Korean token 유지
    - 세 언어 모두 `status=ready_to_save`, `validation_status=failed` 유지 (dictionary block은 의도된 실패)
- **상태:** `applied`

### Change Set #5 — Dictionary-aware meal gate + per-notice ingredient dictionaries

- **해결하는 피드백:** `n03-lunch-allergy-halal`에서 mock dictionary를 준비해도 runner가 항상 빈 dictionary를 넘겨 실험이 불가능하던 문제, 그리고 mapped ingredient가 모두 준비돼도 validator가 `requires_dictionary_mapping=true`만으로 계속 fail 처리하던 문제
- **무엇을 바꿨는가:**
  - 파일: `scripts/run_iteration.py`
  - 파일: `scripts/translation_quality_driver.py`
  - 파일: `backend/app/translation/validators.py`
  - 파일: `backend/app/translation/orchestrator.py`
  - 파일: `backend/app/translation/prompts.py`
  - 파일: `notices/training/n03-lunch-allergy-halal/source-meta.json`
  - 변경 요약:
    - runner/driver가 notice별 `source-meta.json`에서 `approved_ingredient_dictionary`, `approved_ingredient_dictionary_target_by_language`를 읽어 파이프라인에 주입하도록 추가
    - `n03` source meta에 minimal mock dictionary(`맛술`, `젤라틴`)와 en/ru/ar target text를 추가
    - validator가 `ingredient_identity_map`을 함께 받아, critical ingredient가 모두 mapped이고 unmapped item이 없으면 meal/allergy gate를 통과시키도록 수정
    - target hard-fact extractor prompt에 "연도 미기재 시 year를 추론하지 말고 normalized=null" 규칙을 추가해 러시아어의 `2020-06-08`류 false extra-date를 억제
- **왜 이렇게 했는가:**
  - `n03`는 prompt 엔지니어링과 data-policy 검증이 섞여 있는 케이스라, dictionary를 실제로 주입해볼 수 있어야 prompt와 validator를 분리해서 판단할 수 있다.
  - dictionary가 모두 mapped된 뒤에도 gate가 계속 fail이면 그건 prompt 문제가 아니라 validator 설계 문제다.
- **기대 효과:**
  - meal/allergy 케이스에서 prompt 문제와 dictionary/data 문제를 명확히 분리
  - per-notice mock dictionary 실험 가능
  - yearless-date extractor hallucination 감소
- **회귀 리스크:**
  - mapped ingredient가 일부만 있을 때 too-permissive pass가 나면 안 되므로 unmapped/critical flag 조건을 계속 유지해야 함
  - `source-meta.json` 포맷이 notice별로 달라지면 runner가 dictionary를 놓칠 수 있음
- **검증 방법:**
  - `python3 -m py_compile scripts/run_iteration.py scripts/translation_quality_driver.py backend/app/translation/orchestrator.py backend/app/translation/prompts.py backend/app/translation/validators.py`
  - `PYTHONPATH=backend python3 -m unittest backend/tests/test_translation_validators.py`
  - `n03-lunch-allergy-halal` dictionary 주입 재실행:
    - v1: en/ru는 mapped ingredient가 보여도 gate fail, ar는 Vertex 429
    - v2 after fix: en `hard_fact=passed`, ru `hard_fact=passed`, ar `hard_fact=passed`; 세 언어 모두 `context_tone=passed`
- **상태:** `applied`

## 3. Deferred

## 4. Proposed for Next Iteration

- meal/allergy notice에서 unmapped critical ingredient가 있을 때 user-facing translation에 raw Korean 토큰을 어떻게 남길지 정책 점검
- `n02`/`n04` 계열에서 hard-fact extraction empty response가 반복되면 extractor prompt 또는 validator symmetry 추가 검토

## 5. Re-run Result Summary

- `n01-bike-safety-checklist`
  - en: `ready_to_save` -> `ready_to_save` 유지, 문장 자연스러움 개선
  - ru: `ready_to_save` -> `ready_to_save` 유지, 공문체 직역 감소
  - ar: `ready_to_save` -> `ready_to_save` 유지, MSA 용어/제목/연락처 라인 개선
- `n02-field-trip-consent-fee` / ru
  - before: `admin_review_required` with empty `target_hard_facts`
  - after: `ready_to_save`, `hard_fact=passed`, extracted target facts populated
- `n04-school-talent-show`
  - ru: `ready_to_save` 유지, title/manual tone 제거, Korean parenthetical school-term 제거
  - ar: `ready_to_save` 유지, title `إشعار ...`로 수정, Korean parenthetical school-term 제거
- `n03-lunch-allergy-halal`
  - phase 1: en/ru/ar `ready_to_save` 유지, validation failed는 그대로지만 unmapped critical ingredient를 추정 번역하지 않고 exact Korean token으로 통일
  - phase 2 with mock dictionary: en/ru/ar 모두 `hard_fact=passed`, `context_tone=passed`, ingredient mapping populated
- baseline 전체는 아직 진행 중이므로 `n02`~`n06`의 after run은 미실행

## 6. Files Changed

- `backend/app/translation/prompts.py` — Change Set #1 적용
- `backend/app/translation/prompts.py` — Change Set #3 적용
- `backend/app/translation/prompts.py` — Change Set #4 적용
- `backend/app/translation/prompts.py` — Change Set #5 적용
- `backend/app/translation/orchestrator.py` — Change Set #2 적용
- `backend/app/translation/orchestrator.py` — Change Set #5 적용
- `backend/app/services/notice_service.py` — Change Set #2 적용
- `backend/app/translation/validators.py` — Change Set #4 적용
- `backend/app/translation/validators.py` — Change Set #5 적용
- `scripts/run_iteration.py` — Change Set #5 적용
- `scripts/translation_quality_driver.py` — Change Set #5 적용

## 7. Handoff

- baseline이 아직 9/18 출력만 생성된 상태라 (`n01`~`n03`) 전체 training/held-out 비교는 보류
- baseline 종료 후 우선 재실행 후보:
  - `n01-bike-safety-checklist` 전체 언어
  - `n03-lunch-allergy-halal`은 dictionary block 분리 확인 및 product-level 표시 정책 점검
