# Feedback Report — Iter-<NNN>

> Evaluator Agent 산출물. 엔지니어 에이전트가 그대로 받아 다음 이터레이션의 입력으로 사용한다.

**Verdict:** `ship_ready` | `needs_iteration` | `blocking_regression`
**Iteration:** <NNN>
**Date:** <YYYY-MM-DD>
**Source kind:** <weekly-notice / meal-menu / event-notice / safety-notice / etc.>
**Source path:** `input/source.ko.md`

---

## 1. Summary

- **언어별 가중 평균:** en=__ , ru=__ , ar=__
- **Critical 건수:** en=__ , ru=__ , ar=__
- **직전 이터레이션 대비:** (+0.3 / -0.1 등 / 첫 이터레이션이면 "N/A")
- **이번 이터레이션 한 줄 요약:** _(예: ar 톤 강압형 회귀, en 마감 표기 누락, ru placeholder 잔존)_

## 2. Score Matrix

| 축 | en | ru | ar |
|---|---|---|---|
| 1. Fact Preservation | | | |
| 2. Action Clarity | | | |
| 3. Tone & Register | | | |
| 4. Completeness | | | |
| 5. Naturalness | | | |
| 6. Culture & Linguistic | | | |
| 7. Meal / Allergy | | | |
| 8. Safety & Risk | | | |
| **Weighted Avg** | | | |
| **Critical count** | | | |

## 3. Priority Issues (엔지니어가 이번 이터레이션에서 다룰 항목)

이슈를 critical → high → medium → low 순으로 정렬. **상위 3–5건만** 적는다.

### Issue #1 — <한 줄 제목>

- **언어:** en | ru | ar | 공통
- **축:** Fact / Action / Tone / ...
- **심각도:** critical | high | medium | low
- **회귀 여부:** 신규 | 직전 iter에서 해결됐다가 재발
- **원문 스니펫:**
  ```
  <한국어 원문 부분>
  ```
- **번역 스니펫:**
  ```
  <문제가 된 번역 부분>
  ```
- **Back-translation 스니펫:**
  ```
  <역번역 부분>
  ```
- **진단:** _(왜 이렇게 나왔는가의 사실 관찰)_
- **추정 원인 (어느 단계 / 어느 룰):**
  - 예: `translate_en_to_target_prompt` — "make parent/student actions clear" 룰이 약해서 마감일 표현이 흐려짐
  - 예: `validators.py`의 `_extract_iso_dates`가 `6월 1일`처럼 연도 누락 케이스를 못 잡음
- **권고 방향:** _(코드를 직접 쓰지 말 것. 방향만)_
  - 예: 시스템 프롬프트에 "마감일은 반드시 절대 날짜로 표기하되 연도가 없으면 source 추출 단계에서 inferred_year_required=true로 표기" 룰 추가 검토
  - 예: 아랍어 전용 프롬프트로 분리해 격식 등급(فصحى المدارس)을 명시

### Issue #2 — ...
### Issue #3 — ...

## 4. Leverage Opportunities

단일 변경으로 다수 이슈가 풀릴 가능성이 있는 항목.

- _(예: 공통 시스템 프롬프트의 "Korean honorific tone has no exact equivalent" 문구를 언어별 격식 매핑 가이드로 교체하면 Tone 축이 세 언어 모두 동시에 개선될 가능성)_

## 5. Regression Watch

직전 이터레이션 대비 후퇴한 항목.

- _(예: iter-002에서 4점이던 ar Naturalness가 3점으로 하락. 직전 변경 중 ar 톤 강화가 어색함을 유발한 듯.)_
- 첫 이터레이션이면 "N/A".

## 6. Per-Language Notes

### English (en)
- 잘 작동한 지점:
- 반복 패턴 이슈:
- 다음 단계 권고:

### Russian (ru)
- 잘 작동한 지점:
- 반복 패턴 이슈:
- 다음 단계 권고:

### Arabic (ar)
- 잘 작동한 지점:
- 반복 패턴 이슈:
- 다음 단계 권고:

## 7. Rubric / Criteria 보강 제안

평가하다 보니 현재 rubric이나 language-criteria로 잡히지 않는 항목이 있다면 여기 적는다. 평가자는 직접 rubric을 바꾸지 않는다.

- _(예: meal/allergy 축에 "라마단·할랄 기간 식단 명시" 항목 신설 필요)_

## 8. Top 3 Recommendation for Engineer

엔지니어가 곧장 작업 착수할 우선순위 3건. Issue 번호로만 표기.

1. Issue #__
2. Issue #__
3. Issue #__

## 9. Artifacts

- `pipeline-output/en.json` — 영어 번역 결과
- `pipeline-output/ru.json` — 러시아어 번역 결과
- `pipeline-output/ar.json` — 아랍어 번역 결과
- `evaluation/scores.json` — 점수 매트릭스
- 직전 이터레이션 비교: `../<prev-iter>/evaluation/feedback-report.md` (있을 경우)
