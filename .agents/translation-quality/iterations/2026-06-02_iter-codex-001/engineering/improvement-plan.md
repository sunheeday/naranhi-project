# Improvement Plan — Iter-codex-001

**Verdict:** `partial`
**Iteration:** `2026-06-02_iter-codex-001`
**Date:** `2026-06-02`
**Based on:** partial baseline outputs under `notices/*/pipeline-output/`

## 1. Summary

- **다룬 이슈:** `n01-bike-safety-checklist`의 en/ru/ar 직역체, `n02-field-trip-consent-fee`의 ru target fact extraction instability, human review 분기 제거
- **보류한 이슈:** `n03-lunch-allergy-halal`의 dictionary/data block
- **Change Set 수:** 2
- **변경 파일:** `backend/app/translation/prompts.py`, `backend/app/translation/orchestrator.py`, `backend/app/services/notice_service.py`
- **재실행 결과:** `n01-bike-safety-checklist` 3개 언어 재실행 완료, `n02-field-trip-consent-fee` ru 재실행 완료

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

## 3. Deferred

### Deferred — `n03-lunch-allergy-halal`

- **사유:** `맛술`, `젤라틴`이 empty approved dictionary 때문에 validation failure가 발생함
- **다음 이터레이션 권고:** prompt 품질 문제로 보기보다 dictionary/data availability 문제로 분리

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
- baseline 전체는 아직 진행 중이므로 `n02`~`n06`의 after run은 미실행

## 6. Files Changed

- `backend/app/translation/prompts.py` — Change Set #1 적용
- `backend/app/translation/orchestrator.py` — Change Set #2 적용
- `backend/app/services/notice_service.py` — Change Set #2 적용

## 7. Handoff

- baseline이 아직 9/18 출력만 생성된 상태라 (`n01`~`n03`) 전체 training/held-out 비교는 보류
- baseline 종료 후 우선 재실행 후보:
  - `n01-bike-safety-checklist` 전체 언어
  - `n03-lunch-allergy-halal`은 dictionary block 분리 확인
