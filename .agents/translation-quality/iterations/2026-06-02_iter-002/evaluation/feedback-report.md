# Feedback Report — Iter-002

> Evaluator Agent 산출물. 엔지니어 에이전트가 그대로 받아 다음 이터레이션의 입력으로 사용한다.
> **북극성(North Star):** 타겟 언어를 모국어로 쓰는 한국 거주 이주민 학부모가 통신문을 정확히 이해할 수 있는가.

**Verdict:** `needs_iteration`
**근거:** iter-001의 3대 변경(검증 정규화 대칭화 / en register 룰 / 문화 룰)이 전부 의도대로 적중해 세 언어 모두 train·held-out에서 큰 폭(+0.56~+0.76) 상승, critical 0, 회귀 없음(gap −0.057, held-out이 여전히 더 높음). 품질 임계치는 모두 충족하나 `ship_ready`의 6개 하드스톱 중 "직전 2회 이터 모두 held-out 무하락" 단 하나가 아직 성립 불가(이터 2회차 → 전이가 1개뿐). 또한 hard_fact 검증기가 여전히 15/18을 admin_review로 보내는 **위양성(번역 본문은 정확)**이라는 단일 high-leverage 비-번역 이슈가 남아 있어, 한 번 더 클린 이터로 안정성 게이트를 확정하는 것이 타당.

**Iteration:** 002
**Date:** 2026-06-02
**Source kinds:** safety-notice / event-consent-form / recruitment-notice / recruitment-education (training); event-recruitment / event-info-session (held-out)
**Languages:** en, ru, ar (6 통신문 × 3 언어 = 18건, driver_error 없음)

---

## 1. Summary

- **언어별 가중 평균 (training):** en=4.61 , ru=4.70 , ar=4.54
- **언어별 가중 평균 (held-out):** en=4.63 , ru=4.75 , ar=4.65 (집계만)
- **Critical 건수:** 전 언어·전 통신문 0건
- **train_avg_overall=4.62 / held_out_avg_overall=4.68 / generalization_gap=−0.057** (held-out이 여전히 더 높음 → 과적합 신호 없음)
- **직전 이터레이션 대비:** train en +0.76 / ru +0.61 / ar +0.56 ; held-out en +0.62 / ru +0.59 / ar +0.57 ; overall train +0.64, held +0.59, gap −0.105→−0.057(소폭 축소, 여전히 음수)
- **status 분포:** ready_to_save 3건(n01 전 언어), admin_review_required 15건
- **한 줄 요약:** 세 변경 모두 효과 확인 — (1) en 직역체가 자연 영어로 전환(Naturalness 축 +1.0), (2) "신호등을 지켜라"가 3언어 모두 영양 신호등으로 정정(Culture 동시 상승), (3) 검증 정규화 대칭화로 n01이 전 언어 PASS·ready. 남은 병목은 번역이 아니라 **dates·grade_class_targets 정규화 비대칭으로 인한 검증 위양성**.

> **meal 축 처리 주석:** 이번 6개 통신문에도 식단/식재료 정보 없음. meal 축 전건 N/A(rubric 0=해당없음), 가중평균은 meal 가중치(0.7)를 분모에서 제외해 계산(iter-001과 동일 방식).
> **채점 엄격도 주석:** iter-001과 동일 anchor·동일 엄격도 유지. 축 점수는 **구체적·관측 가능한 변화가 있는 곳에서만** 이동(en register fix, 영양 신호등 정정). hard_fact 검증 FAIL은 Fact 축 감점이 아니라 파이프라인 게이트 신호로 분리(본문 사실은 육안 확인 결과 정확). iter-001 보고서의 "검증 status ≠ Fact 축" 규약을 그대로 적용.

## 2. Score Matrix

### Training 평균 (n01, n02, n05, n06) — iter-001 → iter-002 delta

| 축 | en (Δ) | ru (Δ) | ar (Δ) |
|---|---|---|---|
| 1. Fact Preservation | 4.00 (+0.00) | 4.00 (+0.00) | 4.00 (+0.00) |
| 2. Action Clarity | 4.25 (+0.00) | 4.25 (+0.00) | 4.25 (+0.00) |
| 3. Tone & Register | 4.50 (+0.50) | 5.00 (+0.00) | 5.00 (+0.00) |
| 4. Completeness | 5.00 (+0.00) | 5.00 (+0.00) | 4.75 (−0.25) |
| 5. Naturalness | 5.00 (+1.00) | 4.75 (+0.00) | 4.00 (+0.00) |
| 6. Culture & Linguistic | 4.25 (+0.50) | 4.75 (+0.25) | 4.25 (+0.25) |
| 7. Meal / Allergy | N/A | N/A | N/A |
| 8. Safety & Risk | 5.00 (+0.00) | 5.00 (+0.00) | 5.00 (+0.00) |
| **Weighted Avg** | **4.61 (+0.76)** | **4.70 (+0.61)** | **4.54 (+0.56)** |
| **Critical count** | 0 | 0 | 0 |

### Held-out 평균 (집계만, n03·n04 — 디테일 격리)

| 축 | en | ru | ar |
|---|---|---|---|
| **Weighted Avg** | **4.63 (+0.62)** | **4.75 (+0.59)** | **4.65 (+0.57)** |
| **Critical count** | 0 | 0 | 0 |

전체 매트릭스(통신문 단위)는 `evaluation/scores.json` 참조. held-out 통신문별 스니펫·상세 진단은 본 보고서에 포함하지 않으며 `evaluation/held-out-detail/`에만 있다.

## 3. Change Set 효과 검증 (요청 항목)

### CS#1 — 검증 정규화 대칭화: **부분 성공**
- **n01 전 언어 PASS·ready 유지 확인.** 본문 품질 훼손 없음 — 전화번호 `032-320-0096` 그대로 보존, 기관명/연락처가 prose로 묶여도 게이트 통과. iter-001에서 n01이 전 언어 FAIL이던 것과 대비되는 명확한 개선. 정규화 수정이 본문을 건드리지 않고 통과시킴(번역 텍스트 무손상).
- **그러나 잔여 위양성:** `free=무료=0` 동치, 전화 +82↔0, URL canonical, 기관명 prose 제외는 적중했으나, **dates와 grade_class_targets**는 여전히 비대칭. n02/n05/n06/n03/n04가 이 두 필드에서 FAIL → 15건 admin_review의 지배 원인(Issue #1).

### CS#2 — en 전용 register/anti-literal: **성공**
- en Naturalness train **4.00→5.00 (+1.0)**, Tone +0.5, Culture +0.5. iter-001의 직역체("Confirm helmet wearing", "converse with them", "Prohibit ..." 명사 명령 나열)가 "Please confirm that your child wears a helmet / Please talk with your child regularly / Please instruct your child not to ..."로 전면 전환. 안전 체크리스트가 보호자 행동 동사형으로 재구성됨. 영어가 iter-001 최저 → iter-002에서 ru에 근접.

### CS#3 — 문화/학교 개념 룰 (3언어): **성공**
- 핵심 신호 "신호등을 지켜라"(영양 신호등 교육 항목)가 **3언어 모두 정정**:
  - en "Follow the food traffic light guide"
  - ru "Следуйте руководству «Светофор питания»"
  - ar "اتبع دليل إشارة المرور الغذائية" (الغذائية="식품/영양" 한정 추가)
  iter-001에서 ar/ru가 도로 교통신호로 직역되던 critical-인접 오해가 사라짐. n06 Culture가 en 3→5, ru/ar 4→5로 동시 상승. "주춧돌학교(Cornerstone School)", "수련회(Overnight School Camp)" 등도 의미 보충형으로 안정 처리.

## 4. Priority Issues (엔지니어가 이번 이터레이션에서 다룰 항목)

### Issue #1 — hard_fact 검증 위양성 잔존: dates·grade_class_targets 정규화 비대칭으로 15/18 admin_review

- **언어:** 공통 (en/ru/ar)
- **축:** 파이프라인 신뢰도 (Fact 축 점수 아님 — 본문 사실은 정확)
- **심각도:** high (지렛대형, 비-번역)
- **회귀 여부:** 신규(CS#1 이후 남은 잔여). n01은 해결됨.
- **대표 스니펫 (training):**
  - n02 dates: source `2026-06-01, 2026학년도` vs translated `2026-01, 2026-05-27, 2026-10-19, 2026-10-21`. 본문에는 마감 `6월 1일(월)`·작성일 `5월 27일`·일정 `10월 19~21일`이 모두 정확히 있음. 추출기가 `2026학년도`(academic-year)와 `6월 1일`을 서로 다른 단위로 normalize하고 일정 날짜를 한쪽만 펼침 → set mismatch.
  - n05 dates: source `2026-05-29` vs translated `2026, 2026-06, 2026-06-12, 2027` — 활동기간 "위촉 후~2027" 같은 상대표현을 한쪽만 연도 토큰으로 펼침.
  - n06 times: source `19:30 - 20:10, 20:30 - 21:10` vs translated에 `40 minutes`·`09:00`·`18:00`가 섞여 "new critical value"로 오탐. 본문 표의 시간은 정확.
  - n06 grade_class_targets: source `... 도서지역 ...` vs translated `class a~d, grades 1,2,3, grades 4,5,6` — 표의 반(class) 라벨을 grade target으로 흡수.
- **진단:** validator가 비교하는 것은 본문이 아니라 source/target에서 각각 재추출한 normalized fact 리스트. CS#1로 phone/fee/URL/org은 대칭화됐으나, (a) **날짜 범위 vs 개별 날짜 펼침**, (b) **`2026학년도`·`6월 중`·`현재 접수 중`·`마감 시` 같은 fuzzy/상대 토큰**, (c) **표의 class 라벨↔grade target 흡수**가 여전히 비대칭이라 거의 모든 다중-날짜/표 통신문이 FAIL.
- **추정 원인 (어느 단계 / 어느 룰):**
  - hard_fact 추출/정규화의 dates 그룹핑(`A~B`와 `A`,`B` 동치 미적용, academic-year/상대표현 정규화 불일치)
  - grade_class_targets 정규화가 표 헤더(class 라벨)와 대상 학년을 같은 집합에 섞음
  - times에서 회당 소요시간(`40분`)·모집창 시각(`09:00`,`18:00`)을 수업시간과 동일 필드로 합쳐 비교
- **권고 방향:** (코드 직접 수정 금지)
  - 날짜는 **canonical interval/날짜집합으로 정규화**해 범위↔개별, 펼침 차이를 동치 처리. `2026학년도`·`6월 중`·`마감 시`·`현재 접수 중` 같은 비-절대 토큰은 결정 게이트에서 제외(또는 fuzzy-equal 클래스).
  - grade_class_targets는 **class 라벨과 대상 학년을 별도 필드로 분리**해 표 헤더가 target 집합에 새지 않도록.
  - times는 시각(time-of-day)과 소요시간(duration)을 분리 필드로 비교.
  - (보조) 본문 텍스트 포함 검사를 게이트 완화 신호로.

### Issue #2 — en n04 표 분할(셀 다수 표를 2개 표로 쪼갬) — 경미한 형식 저하

- **언어:** en (held-out 집계 영향, 디테일은 held-out-detail)
- **축:** Completeness / Naturalness (형식)
- **심각도:** low
- **진단:** 정보는 1:1 보존되나 "내용+강사" 한 표를 내용 표와 강사 표 2개로 분리해 행-대응 가독이 약간 떨어짐. ru/ar은 단일 표 유지. (held-out이므로 본문 스니펫 비공개.)
- **권고 방향:** en 표 처리에 "원문 표 열 구조 유지(셀 행 대응 보존)" 룰 보강 검토. training에서 표가 풍부한 n06으로 회귀 점검 가능.

### Issue #3 — ar 사소 흔들림: completeness 미세 하락 + 인사 의례구 보존

- **언어:** ar
- **축:** Completeness / Naturalness
- **심각도:** low
- **원문 스니펫 (n05):**
  ```
  ○ 문의: 소통협력담당관 ☎ 032-420-8137
  ```
- **번역 스니펫 (n05 ar):**
  ```
  ○ للاستفسارات: ... على الرقم 032-420-8137 أو عبر البريد الإلكتروني um12um@ice.go.kr
  ```
- **진단:** 문의 라인에 원문에 없던 이메일(앞 접수방법 라인의 주소)을 덧붙임 — 사실 추가는 아니나(문서 내 존재) 라인 매핑이 약간 흐트러져 completeness 미세 감점. ar Naturalness는 여전히 세 언어 중 최저(4.0) — 긴 행정 복합문 경향 잔존.
- **추정 원인:** ar 단계의 라인-단위 충실 매핑 룰이 약해 인접 정보가 한 라인에 융합.
- **권고 방향:** ar 전용 프롬프트에 "원문 라벨-값 라인 구조 보존, 인접 라인 정보 융합 금지" 명시. 복합문 분절 가이드 보강.

## 5. Leverage Opportunities

- **(최우선) Issue #1:** dates·grade_class_targets·times 정규화 대칭화 단일 수정으로 15건 admin_review 중 대다수가 PASS 전환 가능. CS#1이 phone/fee/URL에서 이미 효과를 증명했으므로 같은 패턴을 남은 3필드로 확장하는 명확한 지렛대. 번역 본문 무손상.
- **(부차) en/ar 표·라인 구조 보존 룰:** Issue #2·#3을 함께 잡아 Completeness 흔들림 제거.

## 6. Regression Watch

- **언어 단위 회귀 없음.** 세 언어 train·held-out 모두 상승. 0.5점 이상 급락 축 없음 → `blocking_regression` 미해당.
- **status 회귀(품질 회귀 아님):** n04 en/ar이 iter-001 대비 ready_to_save → admin_review_required. **검토 결과 번역 품질 하락 아님 — 검증 게이트 변화만.** n04 en은 `grade_class_targets` source `grade:3` vs translated `1 2 3`(본문은 "grades 1, 2, and 3"로 정확), n04 ar은 dates `2026, 2028`(2028은 "2028 대입"으로 본문에 정당히 존재). 정규화 비대칭이 원인이며 Issue #1과 동일 뿌리. 상세는 held-out-detail.
- **generalization_gap:** −0.105 → −0.057. 여전히 음수(held-out 우위) → 과적합 신호 없음. train 데이터에 룰을 강화했음에도 held-out이 동반 상승해 일반화 양호.

## 7. Comprehension Pass (통신문별 무엇/언제/어떻게)

| 통신문 | 무엇 | 언제 | 어떻게 | 판정 |
|---|---|---|---|---|
| n01 안전수칙 | 자녀와 안전수칙 점검·지도 | 마감 없음(상시) | 가정 내 점검 항목 4개 | PASS (3언어) |
| n02 수련회 동의 | 참가 여부 회신 제출 | 6/1(월)까지 | 담임에게 신청서 제출 | PASS (3언어) |
| n05 기자단 모집 | 자소서·동의서 제출 | 5/29(금) 17:30까지 | 이메일 um12um@ice.go.kr | PASS (3언어) |
| n06 건강교실 | 온라인 신청 | 6/1~6/12 18:00 | QR/링크/카카오 'D플랜드' | PASS (3언어, 표 시간·반 명확) |
| n03 학부모교육 | 3개 프로그램 선착순 신청 | 현재~마감 시(각 일자 명시) | 누리집 링크(회원가입 필요) | PASS (집계) |
| n04 진로설명회 | 참석 신청 | 5/26~6/3 20시 | 온라인 설문 링크 | PASS (집계) |

→ **Comprehension Pass 전체 통과.** 모든 통신문에서 무엇/언제/어떻게 3질문 답 가능. iter-001 대비 n06의 "영양 신호등" 오해 해소가 가장 큰 이해도 개선.

## 8. Per-Language Notes

### English (en)
- **잘 작동한 지점:** CS#2로 직역체 완전 해소, Naturalness +1.0. 보호자 행동 문장이 자연 영어. n01 전 언어 PASS. 영양 신호등 정정.
- **반복 패턴 이슈:** 표가 많은 통신문에서 표 분할 경향(n04). dates/grade 검증 위양성(공통).
- **다음 단계 권고:** 표 열 구조 보존 룰. en 자체 번역 품질은 ship 수준 근접.

### Russian (ru)
- **잘 작동한 지점:** 정중 호명·`Просим Вас`·24시간제·금액 공백·격수 일치 모두 견고. 세 언어 중 최고(train 4.70). 영양 신호등 정정.
- **반복 패턴 이슈:** 사실상 미세 표기 수준만 잔존. dates 검증 위양성(공통).
- **다음 단계 권고:** 추가 번역 룰 필요성 낮음. 검증 게이트만 통과시키면 ship.

### Arabic (ar)
- **잘 작동한 지점:** MSA 접근가능 등록, `يُرجى` 요청형, 서양식 숫자 일관, 헤지라력·종교 관용어 미삽입. 영양 신호등에 "الغذائية" 한정 추가로 의미 명확화.
- **반복 패턴 이슈:** 긴 복합문 경향(Naturalness 4.0 최저), 라인 정보 융합(n05 문의+이메일).
- **다음 단계 권고:** 라인 구조 보존 + 복합문 분절(Issue #3). 본문 품질은 임계치 충족.

## 9. Rubric / Criteria 보강 제안

- iter-001의 두 제안(meal N/A 가중평균 규약, 검증 status ↔ Fact 축 분리)은 본 이터에서 그대로 적용해 유효함을 확인. **rubric 본문에 명문화 권장**(현재는 평가자 주석으로만 운용 중).
- "status 회귀 ≠ 품질 회귀" 판정 규약 추가 권장: 검증 게이트 변화로 인한 status 후퇴는 blocking_regression 판단 시 제외하고, 동일 통신문의 8축 점수 delta로만 회귀를 판정한다는 규칙. (이번 n04 en/ar 케이스가 정확히 이 구분을 요구했다.)
- ship_ready의 "직전 2회 이터 held-out 무하락" 조건은 이터 2회차에서는 구조적으로 성립 불가 → "최소 1회 무하락 전이 + 다음 이터 무하락 확정 시 충족"으로 운용 해석을 명시 권장.

## 10. Top 3 Recommendation for Engineer

1. **Issue #1** — hard_fact 정규화 대칭화를 **dates(범위↔개별 동치, 학년도/상대 토큰 게이트 제외), grade_class_targets(class 라벨 분리), times(시각↔소요시간 분리)**로 확장. 15건 admin_review의 근본 원인, 최대 지렛대. (n04 status 회귀도 동시 해소.)
2. **Issue #2** — en 표 열 구조 보존(셀 행 대응 유지) 룰. n06 회귀 점검 가능.
3. **Issue #3** — ar 라인 구조 보존 + 복합문 분절. ar Naturalness·Completeness 미세 흔들림 제거.

## 11. Artifacts

- 각 통신문 `pipeline-output/{en,ru,ar}.json` — 파이프라인 결과 (18건)
- `evaluation/scores.json` — 통신문 × 언어 × 8축 매트릭스 + train/held_out 집계 + iter-001 delta 필드
- `evaluation/held-out-detail/n03-parent-edu-program.md`, `n04-college-info-session.md` — held-out 상세(엔지니어 비공개, 평가자 회귀 점검용; n04 en/ar status 회귀 상세 포함)
- 직전 이터레이션 비교: `../2026-06-01_iter-001/evaluation/feedback-report.md`, `scores.json`
