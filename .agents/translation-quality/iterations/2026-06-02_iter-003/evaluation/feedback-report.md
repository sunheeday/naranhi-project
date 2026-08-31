# Feedback Report — Iter-003

> Evaluator Agent 산출물.
> **북극성(North Star):** 타겟 언어를 모국어로 쓰는 한국 거주 이주민 학부모가 통신문을 정확히 이해할 수 있는가.

**Verdict:** `ship_ready`
**근거:** ship_ready 6개 하드스톱이 전부 충족됐다. 세 언어 train 4.54~4.70 / held-out 4.63~4.75, critical 0, safety 전부 5, fact·action 전부 ≥4, Comprehension Pass 전건 통과. 그리고 iter-002에서 유일하게 미충족이던 6번 조건("직전 2회 이터 held-out 무하락")이 이번에 판정 가능해졌고 충족됐다 — 전이가 둘(iter-001→002 held +0.59, iter-002→003 held 0.0) 모두 무하락. CS#1(검증 정규화를 dates/times/grade_class_targets로 확장)이 의도대로 적중해 admin_review 15→5로 격감, 번역 본문은 무손상(축 점수 전부 iter-002와 동일). 남은 admin_review 5건은 전수 검토 결과 검증 게이트/LLM 추출 변동에 의한 위양성이며 번역 품질 문제가 아니다. 회귀 없음(held-out 평탄, 어떤 언어·축도 하락 없음, iter-002 status 회귀였던 n04 en/ar은 ready 복귀). 더 손볼 high-leverage 번역 변경 후보가 보이지 않는다 → 자동 종료 권장.

**Iteration:** 003
**Date:** 2026-06-02
**Source kinds:** safety-notice / event-consent-form / recruitment-notice / recruitment-education (training); event-recruitment / event-info-session (held-out)
**Languages:** en, ru, ar (6 통신문 × 3 언어 = 18건, driver_error 0)

---

## 1. Summary

- **언어별 가중 평균 (training):** en=4.61 , ru=4.70 , ar=4.54
- **언어별 가중 평균 (held-out, 집계만):** en=4.63 , ru=4.75 , ar=4.65
- **Critical 건수:** 전 언어·전 통신문 0건
- **train_avg_overall=4.62 / held_out_avg_overall=4.68 / generalization_gap=−0.057** (held-out 우위 유지 → 과적합 신호 없음)
- **직전 이터(iter-002) 대비:** 축 점수 전 언어·전 축 **±0.00** (번역 본문 품질 plateau). 변화는 점수가 아니라 **status**: ready_to_save 3→13, admin_review 15→5.
- **status 분포:** ready_to_save 13 / admin_review_required 5 / driver_error 0.
- **한 줄 요약:** 깨끗한 안정화 이터. CS#1이 검증 위양성을 대거 해소(15→5)하면서 본문은 한 글자도 품질이 깎이지 않음. 품질은 iter-002 수준에서 고원(plateau)을 형성했고, 안정성 게이트(조건6)가 이번에 확정됨 → ship_ready.

> **meal 축 주석:** 이번 6개 통신문에도 식단/식재료 정보 없음. meal 축 전건 N/A(rubric 0=해당없음), 가중평균은 meal 가중치(0.7)를 분모에서 제외(iter-001/002 동일 방식).
> **채점 엄격도 주석:** iter-001/002와 **동일 anchor·동일 엄격도·동일 페르소나 frame**. 축 점수는 번역 TEXT에 관측 가능한 변화가 있는 곳에서만 이동한다는 규약을 그대로 적용. CS#1은 validator 전용 수정이라 본문을 건드리지 않으므로 축 점수 무변동이 정상. hard_fact FAIL은 Fact 축 감점이 아니라 파이프라인 게이트 신호로 분리(전 18건 본문 육안 검증 결과 사실 정확).

## 2. Score Matrix

### Training 평균 (n01, n02, n05, n06) — iter-002 → iter-003 delta

| 축 | en (Δ) | ru (Δ) | ar (Δ) |
|---|---|---|---|
| 1. Fact Preservation | 4.00 (±0.00) | 4.00 (±0.00) | 4.00 (±0.00) |
| 2. Action Clarity | 4.25 (±0.00) | 4.25 (±0.00) | 4.25 (±0.00) |
| 3. Tone & Register | 4.50 (±0.00) | 5.00 (±0.00) | 5.00 (±0.00) |
| 4. Completeness | 5.00 (±0.00) | 5.00 (±0.00) | 4.75 (±0.00) |
| 5. Naturalness | 5.00 (±0.00) | 4.75 (±0.00) | 4.00 (±0.00) |
| 6. Culture & Linguistic | 4.25 (±0.00) | 4.75 (±0.00) | 4.25 (±0.00) |
| 7. Meal / Allergy | N/A | N/A | N/A |
| 8. Safety & Risk | 5.00 (±0.00) | 5.00 (±0.00) | 5.00 (±0.00) |
| **Weighted Avg** | **4.61 (±0.00)** | **4.70 (±0.00)** | **4.54 (±0.00)** |
| **Critical count** | 0 | 0 | 0 |

### Held-out 평균 (집계만, n03·n04 — 디테일 격리)

| 축 | en | ru | ar |
|---|---|---|---|
| **Weighted Avg** | **4.63 (±0.00)** | **4.75 (±0.00)** | **4.65 (±0.00)** |
| **Critical count** | 0 | 0 | 0 |

전체 매트릭스(통신문 단위)는 `evaluation/scores.json` 참조. held-out 통신문별 스니펫·상세 진단은 본 보고서에 미포함, `evaluation/held-out-detail/`에만 있다.

## 3. iter-002 → iter-003 핵심 변화: 점수가 아니라 status

이번 이터의 핵심 변화는 8축 점수가 아니라 검증 게이트 통과율이다.

| 지표 | iter-002 | iter-003 | 변화 |
|---|---|---|---|
| ready_to_save | 3 | 13 | +10 |
| admin_review_required | 15 | 5 | −10 |
| train_avg_overall | 4.62 | 4.62 | ±0.00 |
| held_out_avg_overall | 4.68 | 4.68 | ±0.00 |
| generalization_gap | −0.057 | −0.057 | ±0.00 |
| critical | 0 | 0 | 0 |

- **CS#1 (dates/times/grade_class_targets 정규화 확장): 성공.** iter-002에서 admin_review의 지배 원인이던 날짜 범위↔개별 펼침, 학년도/상대 토큰, 수업시간↔소요시간/모집창 시각 혼동이 정리됨. n02·n05(다중 날짜·요일·금액 표)가 전 언어 PASS·ready로 전환. **iter-002의 status 회귀였던 n04 en(grade_class_targets)·n04 ar(dates 2028 위양성)이 둘 다 ready_to_save로 복귀** → status 회귀 완전 해소.
- **CS#2/CS#3 효과 유지:** en 자연 영어 문장(보호자 행동 동사형), 영양 신호등(en "food traffic light", ru "Светофор питания", ar 한정어 추가), 표·라인 구조 보존이 iter-003에서도 그대로 유지됨(회귀 없음). 본문 품질이 iter-002 수준에서 안정적으로 재현됨.

## 4. 남은 admin_review 5건 성격 판정 (요청 항목)

전수 본문 검증 결과 **5건 모두 번역 품질 문제가 아니라 검증 게이트/LLM 추출 변동에 의한 위양성**이다. 따라서 8축 점수에 영향 없음(전부 본문 사실 정확).

| 케이스 | FAIL 필드 | 성격 | 판정 |
|---|---|---|---|
| n06 en | grade_class_targets (src 'grade:1,2,4,5' vs tgt 'grade:3,6') | 표의 반(class) 라벨↔대상 학년 집합을 양쪽 추출기가 다르게 펼침. 본문은 A~D반 1~6학년 전부 정확. | 게이트 아티팩트 |
| n06 ru | grade_class_targets (tgt 빈 집합) | target 추출이 표의 학년을 못 집계. 본문 표에 1~6학년 정확. | 게이트 아티팩트 |
| n03 en | fees (src 'free' vs tgt 'material costs...') + urls (URL vs 경로 설명) | 동일 원문 "무료(단, 재료비는 학습자 부담)"의 서로 다른 하위절을 비교. URL은 본문에 그대로(`https://buly.kr/7x8GXFZ`). | 게이트 아티팩트 |
| n03 ar | fees (src 'free' vs tgt 'learner bears material costs') | 위와 동일 split-clause 비교. 본문은 전체 절 정확 번역. | 게이트 아티팩트 |
| n04 ru | grade_class_targets (tgt 빈 집합) | 본문 "Учащиеся 1, 2 и 3 классов" 정확. 동일 root가 이번엔 ru에서 표면화. | 게이트 아티팩트 |

→ **품질 문제 0건.** 5건 전부 추출/정규화 비대칭(LLM 추출의 run-to-run 변동 포함). 이주민 학부모 이해도·사실 보존에 영향 없음. 종료 판정의 품질 임계치를 깎지 않는다.

## 5. Comprehension Pass (통신문별 무엇/언제/어떻게)

| 통신문 | 무엇 | 언제 | 어떻게 | 판정 |
|---|---|---|---|---|
| n01 안전수칙 | 자녀와 안전수칙 점검·지도 | 마감 없음(상시) | 가정 내 점검 항목 4개 | PASS (3언어) |
| n02 수련회 동의 | 참가 여부 회신 제출 | 6/1(월)까지 | 담임에게 신청서 제출, 비용 표 명확 | PASS (3언어) |
| n05 기자단 모집 | 자소서·동의서 제출 | 5/29(금) 17:30까지 | 이메일 tv63tv@ice.go.kr | PASS (3언어) |
| n06 건강교실 | 온라인 신청 | 모집 6/1~6/12 18:00, 프로그램 6/22~7/9 | QR/링크/카카오 'D플랜드', 표 시간·반 명확 | PASS (3언어) |
| n03 학부모교육 | 3개 프로그램 선착순 신청 | 6월 중(각 일자 6/9·6/11·6/27 명시)~마감 시 | 누리집 링크(회원가입 필요) | PASS (집계) |
| n04 진로설명회 | 참석 신청 | 설명회 6/9(화) 15:00~17:00, 신청 5/26~6/3 20시 | 온라인 설문 링크 | PASS (집계) |

→ **Comprehension Pass 전체 통과.** 모든 training+held-out 통신문에서 무엇/언제/어떻게 3질문 답 가능. ship_ready 조건5 충족.

## 6. Stopping Criteria — Verdict 판정

### ship_ready 6개 하드스톱 (전부 ✓ → 자동 종료)

| # | 조건 | 결과 | 판정 |
|---|---|---|---|
| 1 | 세 언어 train≥4.2 AND held-out≥4.0 | train 4.61/4.70/4.54, held 4.63/4.75/4.65 | ✓ |
| 2 | 세 언어 critical_count==0 | 전부 0 | ✓ |
| 3 | 세 언어 safety≥4 | 전부 5.0 | ✓ |
| 4 | 세 언어 fact≥4 AND action≥4 AND meal≥4(N/A 제외) | fact 4.0+, action 4.25+, meal N/A | ✓ |
| 5 | Comprehension Pass 전체 통과 | 6/6 통신문 PASS | ✓ |
| 6 | 직전 2회 이터 held-out 무하락 | iter-001→002 +0.59, iter-002→003 0.0 — 둘 다 무하락 | ✓ |

**조건6 명시:** 이제 held-out 전이가 둘 존재한다. (a) iter-001→002: held-out overall 4.08→4.68 (+0.59, 무하락). (b) iter-002→003: 4.68→4.68 (0.0, 무하락). 두 전이 모두 하락 없음 → 조건6 충족. iter-002에서 유일하게 미충족이던 조건이 해소됐다. → **6/6 모두 충족 → ship_ready (하드 스톱).**

### 보조 판정 (참고)
- **diminishing_returns:** iter-002→003 held-out 개선 0.0(<0.1)이고 남은 이슈가 critical 0/high 0. 만약 ship_ready가 미충족이었다면 이 조건이 트리거됐을 것이나, ship_ready(하드 스톱)가 우선한다. 어느 쪽이든 결론은 **종료**다.
- **blocking_regression:** held-out 무하락, 어떤 언어도 0.5 급락 없음, 3연속 회귀 없음 → **미해당.**

## 7. Regression Watch

- **언어·축 단위 회귀 없음.** 세 언어 train·held-out 평탄(±0.00). 0.5 급락 축 없음.
- **iter-002 status 회귀 해소 확인:** iter-002에서 ready→admin으로 후퇴했던 n04 en(grade_class_targets)·n04 ar(dates 2028)이 **이번에 ready_to_save로 복귀.** CS#1 적중의 직접 증거.
- **iter-002 회귀 watch 항목 점검:** (a) n03 en placeholder 토큰 `2026-06-xx`가 본문에 새지 않는지 → **본문 클린**(6/9·6/11·6/27 정상, placeholder 없음). (b) en 표 분할(n04) → 이번 n04 en 표 구조 단일 표로 유지(CS#2 표 열 보존 효과), n06 표도 행 대응 보존. (c) ar 라인 정보 융합 → n05 ar 문의/이메일 라인 분리 양호.
- **generalization_gap:** −0.057 유지(held-out 우위) → 과적합 신호 없음.

## 8. Per-Language Notes

### English (en)
- **잘 작동한 지점:** 자연 영어(보호자 행동 동사형), "Dear Parents/Guardians" 정중 호명, "We kindly request" 행정 톤, 표 열 구조 보존, 영양 신호등 정정 모두 안정 재현. n04 en grade target ready 복귀.
- **반복 패턴 이슈:** 번역 본문 이슈 없음. n06 en·n03 en의 admin_review는 검증 게이트 위양성(품질 아님).
- **다음 단계 권고:** 번역 측 추가 작업 불필요(ship 수준). (선택) 검증 게이트 잔여 위양성만 비-번역 영역에서 추가 정리 가능.

### Russian (ru)
- **잘 작동한 지점:** `Уважаемые родители!`·`Просим Вас`·24시간제·금액 공백·격수 일치 견고. 세 언어 중 최고(train 4.70). 영양 신호등 정정 유지.
- **반복 패턴 이슈:** 본문 이슈 없음. n04 ru·n06 ru admin_review는 grade_class_targets 추출 위양성(품질 아님).
- **다음 단계 권고:** 추가 번역 룰 불필요.

### Arabic (ar)
- **잘 작동한 지점:** 접근가능 MSA, `يُرجى` 요청형, 서양식 숫자 일관, 헤지라력·종교 관용어 미삽입. 표·라인 구조 보존 양호. 영양 신호등 한정어 유지.
- **반복 패턴 이슈:** Naturalness 4.0이 여전히 세 언어 중 최저(긴 행정 복합문 경향) — 단 이해도 임계치 충족, ship 기준 통과. n03 ar admin_review는 fees 위양성(품질 아님).
- **다음 단계 권고:** 본문 품질 임계치 충족. (선택) 향후 추가 이터 시 ar 복합문 분절이 유일하게 남은 미세 개선 여지지만 high-leverage 아님.

## 9. Rubric / Criteria 보강 제안

- **"status 회귀 ≠ 품질 회귀" 규약을 rubric 본문에 명문화 권장.** iter-002에 이어 iter-003에서도 동일 구분이 필요했다(n04 ru가 게이트만 후퇴). 회귀 판정은 동일 통신문의 8축 점수 delta로만, status는 별도 신호로 분리한다는 규칙.
- **조건6 운용 해석 확정 권장:** "직전 2회 이터 held-out 무하락"은 이터 3회차부터 구조적으로 판정 가능하며, 두 전이 모두 무하락이면 충족 — 이번 이터에서 이 해석이 실제로 작동함을 확인.
- meal N/A 가중평균 규약, 검증 status↔Fact 축 분리 규약은 3개 이터 연속 유효 — rubric 본문 반영 권장(현재 평가자 주석으로만 운용).

## 10. 종료 사유 (Verdict=ship_ready)

1. **품질 임계치 전부 충족 + 안정성 게이트 확정.** 6개 하드스톱 6/6. 특히 마지막까지 남았던 조건6(2회 무하락)이 이번에 충족.
2. **회귀 없음.** held-out 평탄, 과적합 신호 없음(gap 음수 유지), iter-002 status 회귀까지 복구.
3. **남은 5건은 비-번역 게이트 위양성.** 번역 품질로는 추가로 손댈 high-leverage 변경 후보가 없음(번역 측 plateau). 더 돌려도 점수 개선 기대 < 0.1.
4. 따라서 **자동 다음 이터를 시작하지 않고 종료를 권장**한다. (남은 검증 게이트 위양성 5건은 사용자가 원하면 비-번역(validator) 영역의 후속 작업으로 별도 처리 가능하나, 번역 ship 판정에는 영향 없음.)

## 11. Artifacts

- 각 통신문 `pipeline-output/{en,ru,ar}.json` — 파이프라인 결과 (18건)
- `evaluation/scores.json` — 통신문 × 언어 × 8축 매트릭스 + train/held_out 집계 + iter-002 delta + ship_ready/blocking/diminishing 체크
- `evaluation/held-out-detail/n03-parent-edu-program.md`, `n04-college-info-session.md` — held-out 상세(엔지니어 비공개, 평가자 회귀 점검용)
- 직전 이터 비교: `../2026-06-02_iter-002/evaluation/feedback-report.md`, `scores.json`; `../iterations/_history.json`
