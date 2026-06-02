# Improvement Plan — Iter-<NNN>

> Engineer Agent 산출물. 어떤 피드백을 어떻게 풀었는지, 무엇을 보류했는지 명확히 기록한다.

**Verdict:** `ready_for_re_evaluation` | `blocked` | `partial`
**Iteration:** <NNN>
**Date:** <YYYY-MM-DD>
**Based on:** `evaluation/feedback-report.md`

---

## 1. Summary

- **다룬 이슈 번호:** Issue #__, #__, #__
- **보류한 이슈 번호:** Issue #__, #__
- **Change Set 수:** N개 (5개 이하 권장)
- **변경 파일:** `backend/app/translation/prompts.py`, `orchestrator.py`, ...
- **신규 모듈:** (있다면)
- **재실행 결과:** `pipeline-output-after/` 저장 완료 여부

## 2. Change Sets

### Change Set #1 — <한 줄 제목>

- **해결하는 피드백:** Issue #__ (필요시 다수 가능)
- **무엇을 바꿨는가:**
  - 파일: `backend/app/translation/prompts.py`
  - 함수: `translate_en_to_target_prompt`
  - 변경 요약: _(코드 그대로가 아니라 의도 단위로)_
- **왜 이렇게 했는가:** _(피드백이 요구한 방향과의 정렬, 다른 옵션을 검토했다면 비교)_
- **기대 효과:** _(어느 축 점수가 오를 것으로 예상)_
- **회귀 리스크:** _(혹시 깨질 수 있는 다른 시나리오)_
- **검증 방법:**
  - 같은 입력으로 재실행 후 `pipeline-output-after/<lang>.json`의 해당 부분 확인
  - 필요 시 추가 테스트 (`backend/tests/test_translation_*`)
- **상태:** `applied` | `partially_applied`

### Change Set #2 — ...

## 3. Deferred (이번에 적용하지 않은 피드백)

엔지니어가 의도적으로 보류한 항목과 사유.

### Deferred Issue #__ — <제목>

- **사유:** _(예: 평가 기준 변경 필요 / 사용자 결정 필요 / 데이터 부족 / 다른 Change Set과 결합해 측정 효과가 흐려질 위험)_
- **다음 이터레이션 권고:** _(언제·어떻게 풀자)_

## 4. Proposed for Next Iteration (다음 이터에 시도하고 싶은 변경)

엔지니어가 자체적으로 발견한 개선 아이디어. 평가자가 요청하지 않은 사항은 이 섹션에만 적는다.

- _(예: ar 톤 안정화 후 ru 격변화 정합 강화로 이동)_

## 5. Backward Compatibility / Schema

- 데이터 스키마 변경 여부: 없음 | 있음 (`HARD_FACT_SCHEMA`의 ___ 필드)
- `TranslationPipelineInput` 시그니처 변경: 없음 | 있음 (호출부 동시 수정 완료)
- Supabase 컬럼 영향: 없음 | 있음 (별도 마이그레이션 제안)

## 6. Rubric / Criteria 변경 제안

평가 기준을 바꿔야 한다고 판단한 경우만. 직접 수정하지 말고 사용자 승인을 받는다.

- _(예: language-criteria/ar.md에 "라마단 기간 메뉴 별도 라벨링" 항목 추가 제안)_

## 7. Re-run Result Summary

`pipeline-output-after/`로 재실행한 결과 자체 점검.

| 항목 | iter-NNN before | iter-NNN after | 변화 |
|---|---|---|---|
| en hard_fact 검증 | pass/fail | pass/fail | |
| ru hard_fact 검증 | | | |
| ar hard_fact 검증 | | | |
| en final_translation 길이 | | | |
| ru final_translation 길이 | | | |
| ar final_translation 길이 | | | |
| (이슈별 핵심 스니펫 변화) | | | |

전체 점수 산정은 다음 이터레이션에서 평가자가 수행.

## 8. Files Changed

- `backend/app/translation/prompts.py` — Change Set #1, #2 적용
- `backend/app/translation/orchestrator.py` — Change Set #3 적용
- `backend/app/translation/prompts_ar.py` — 신규
- `backend/tests/test_translation_orchestrator.py` — 회귀 테스트 추가

`changes-summary.md`에 더 자세한 diff 요약.

## 9. Handoff

다음 이터레이션 평가자에게 전달할 사항.

- **반드시 확인할 것:** Change Set이 의도한 축 점수가 실제로 올랐는지
- **회귀 watch:** _(예: ar Naturalness가 톤 강화로 깎이지 않았는지)_
- **새 평가 항목:** Rubric 변경 제안 적용 여부 (사용자 승인 필요)
