# Feedback Report — Iter-004

> Evaluator Agent 산출물.
> **북극성(North Star):** 타겟 언어를 모국어로 쓰는 한국 거주 이주민 학부모가 통신문을 정확히 이해할 수 있는가.

**Verdict:** `ship_ready`
**근거:** Phase-2에서 RU_TARGET_RULES만 신규 추가됐고, 이번 평가의 핵심 질문 두 개가 모두 통과로 판정됐다. (1) **ru는 회귀 없이 유지 + 미세 개선**: RU 본문이 iter-003 대비 실제로 바뀌었으나(새 규칙 적용) ru.md 체크리스트 기준으로 maintain-to-marginal-improvement다 — n02 첫인사 `Здравствуйте.`→`Уважаемые родители!`로 직역 안티패턴 제거, `Просим Вас` 요청형이 더 일관됨, 그리고 대문자 Вы·천단위 공백(250 000)·«»·24시간제·러시아식 월이름 날짜·수명사 일치가 전부 무회귀로 보존됨. RU 톤·문화 축은 iter-003에서 이미 천장권이라 미세 개선이 축 임계치를 넘기지 않음 → 축 점수 동일. (2) **en/ar 무회귀**: 본문 품질 iter-003과 동일, 어떤 축도 0.5 이상 급락 없음. status는 admin_review 5→7로 늘었으나 두 신규 건(n03 ru fees, n04 en grade_class_targets)은 iter-003에서 이미 식별된 동일 검증 위양성 패밀리가 LLM 추출 run-to-run 변동으로 다른 언어에 표면화된 것이며 본문은 전수 정확 — 품질 회귀 아님, RU 규칙 탓도 아님. ship_ready 6개 하드스톱 6/6 유지, held-out 무하락(0.0), gap 음수(−0.057) 유지. blocking_regression 미해당 → **RU_TARGET_RULES rollback 불필요**. 자동 종료 권장.

**Iteration:** 004
**Date:** 2026-06-02
**Source kinds:** safety-notice / event-consent-form / recruitment-notice / recruitment-education (training); event-recruitment / event-info-session (held-out)
**Languages:** en, ru, ar (6 통신문 × 3 언어 = 18건, driver_error 0)

---

## 1. Summary

- **언어별 가중 평균 (training):** en=4.61 , ru=4.70 , ar=4.54
- **언어별 가중 평균 (held-out, 집계만):** en=4.63 , ru=4.75 , ar=4.65
- **Critical 건수:** 전 언어·전 통신문 0건
- **train_avg_overall=4.62 / held_out_avg_overall=4.68 / generalization_gap=−0.057** (held-out 우위 유지 → 과적합 신호 없음)
- **직전 이터(iter-003) 대비:** 축 점수 전 언어·전 축 **±0.00**. 변화는 점수가 아니라 **status**: ready_to_save 13→11, admin_review 5→7.
- **이번 이터 핵심:** RU_TARGET_RULES만 추가. **ru = 유지 + 미세 개선(회귀 0)**, **en/ar = 무회귀**. status 증가 2건은 검증/LLM-추출 위양성(품질 무관).
- **한 줄 요약:** RU 전용 규칙이 ru.md 안티패턴(직역 인사)을 깔끔히 잡으며 ru를 무회귀로 유지·미세 개선했고, en/ar는 손상 없이 plateau를 유지했다. ship_ready 그대로.

> **meal 축 주석:** 6개 통신문 모두 식단/식재료 정보 없음. meal 축 전건 N/A, 가중평균 분모에서 meal 가중치(0.7) 제외(iter-001~003 동일).
> **채점 엄격도 주석:** iter-001~003과 **동일 anchor·동일 엄격도·동일 페르소나 frame**. RU 본문이 이번에 실제로 바뀌었으나(아래 §3) 변화가 축 임계치를 넘지 않아 축 점수는 iter-003과 동일하게 유지. hard_fact FAIL은 Fact 축 감점이 아니라 파이프라인 게이트 신호로 분리(전 18건 본문 육안 검증 결과 사실 정확).

## 2. Score Matrix

### Training 평균 (n01, n02, n05, n06) — iter-003 → iter-004 delta

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

## 3. RU 변화 판정 — 유지(+미세 개선), 회귀 아님 (이번 이터 핵심 질문 1)

RU 본문은 iter-003 대비 **실제로 텍스트가 바뀌었다**(새 RU_TARGET_RULES가 다른 출력 생성). 6개 통신문 전부 final_translation 길이/문구가 달라짐을 확인. 그러나 ru.md 기준으로 **maintain-to-marginal-improvement**이며 회귀 신호는 0건이다.

| ru.md 항목 | iter-003 | iter-004 | 판정 |
|---|---|---|---|
| 첫인사(안녕하세요 처리) | n02 `Здравствуйте.` (직역 안티패턴) | n02 `Уважаемые родители!` | **개선** (ru.md L80 안티패턴 제거) |
| 요청형 | 혼용(`Мы убедительно просим`/`просим`) | `Просим Вас + ...` 더 일관 | **개선** (ru.md Register 체크리스트) |
| 대문자 Вы 일관 | 적용 | 적용 (소문자 вы 누수 0 확인) | 유지 |
| 천단위 공백 | `250 000`/`71 600`/`1 600` | 동일 | 유지 |
| 24시간제 | `15:00-17:00`/`19:30-20:10` | 동일 | 유지 |
| 러시아식 날짜(월 소문자) | `19 октября (понедельник)` | 동일 | 유지 |
| «» 인용부호 | 적용 | 적용 | 유지 |
| 수-명사 일치 | `1, 2 и 3 классов`/`20 родителей` | 동일 | 유지 |
| 한국 학교개념 처리 | 수련회→`внеклассное мероприятие (школьный лагерь)` | 동일 의미번역 | 유지 |

- **개선의 성격:** RU는 iter-003에서 이미 톤 5.0(train)·문화 4.75(train)로 천장권이었다. 이번 미세 개선(직역 인사 제거·`Просим Вас` 일관화)은 **이미 5.0인 톤을 보강**하는 것이지 임계치 미달 점수를 끌어올리는 게 아니다. 따라서 RU 축 점수는 iter-003과 동일하게 유지된다(정직한 채점: 관측된 텍스트 개선이 있으나 축 단위 점수 이동을 정당화할 임계치 교차는 없음).
- **회귀 0:** 위 표의 어떤 must-pass 항목도 후퇴하지 않음. 고전·관료 어휘(`соблаговолите` 등) 삽입 없음, 12시간제 누수 없음, 학교개념 단순 음역 없음.

## 4. en/ar 회귀 여부 (이번 이터 핵심 질문 2)

- **en/ar 본문 품질 = iter-003과 동일.** Phase-2가 en/ar 프롬프트 출력을 사실상 건드리지 않았다는 전제와 일치. 어떤 언어·어떤 축도 점수 이동 없음, 0.5 이상 급락 0건.
- 검증: n01·n02·n05 en/ar PASS·ready 유지. en 자연 영어 동사형, "Dear Parents", 표 구조 보존, 영양 신호등("Follow the Traffic Light (Nutrition Guide)") 한정어 유지. ar 접근가능 MSA, `يُرجى` 요청형, 서양식 숫자, 헤지라력/종교관용어 미삽입, 영양 신호등 한정어 유지.
- **결론: en/ar 회귀 없음.** (status 변동 2건은 §5에서 별도 판정.)

## 5. status 회귀 성격 판정 (n03 ru / n04 en) — 품질 vs 게이트 (요청 항목)

iter-003 대비 ready→admin으로 후퇴한 통신문은 정확히 2건이다. **둘 다 본문 품질 하락이 아니라, iter-003에서 이미 식별된 동일 검증 위양성 패밀리가 LLM 추출 run-to-run 변동으로 다른 언어에 표면화된 것**이다.

| 케이스 | iter-003 | iter-004 | FAIL 필드 | 본문 검증 | 판정 |
|---|---|---|---|---|---|
| **n03 ru** | ready_to_save | admin_review | fees (src 'free' vs tgt '재료비 학습자 부담' 하위절 비교) | 본문 정확: "Стоимость курса: Бесплатно. Расходы на материалы оплачиваются слушателем." (무료+단서절 모두 보존) | **게이트 아티팩트** (iter-003에 n03 en/ar에서 나온 split-clause 패밀리가 이번엔 ru에 표면화) |
| **n04 en** | ready_to_save | admin_review | grade_class_targets (src 'grade:1,2,3' vs tgt 빈 집합) | 본문 정확: "Students in grades 1, 2, and 3 of our school" | **게이트 아티팩트** (iter-003에 n04 ru에서 나온 빈-추출 패밀리가 이번엔 en에 표면화) |

- 두 패밀리(fees split-clause / grade_class_targets 빈-추출)는 iter-002·003에서도 "검증 게이트/LLM 추출 위양성"으로 판정된 바로 그 root다. **언어 간 회전(rotation)**만 일어났을 뿐 — n04 en은 iter-003에 CS#1로 ready 복귀했었는데 이번에 추출기가 빈 집합을 반환해 다시 admin으로 회전, n04 ru는 두 run 모두 admin.
- **RU_TARGET_RULES와 무관:** RU 규칙은 번역 register만 건드린다. n03 ru fees FAIL은 fee 추출 단계 위양성이고, n04 en은 en 파이프라인의 target 추출 문제다. 둘 다 RU 규칙 추가로 생긴 것이 아니다.
- 나머지 admin 5건(n06 en/ru, n03 en/ar, n04 ru)은 iter-003과 동일 — 전부 동일 두 패밀리, 본문 정확.

→ **품질 문제 0건.** status 7건 admin 전부 비-번역 게이트/추출 위양성. 종료 판정의 품질 임계치를 깎지 않는다.

## 6. Comprehension Pass (통신문별 무엇/언제/어떻게)

| 통신문 | 무엇 | 언제 | 어떻게 | 판정 |
|---|---|---|---|---|
| n01 안전수칙 | 자녀와 안전수칙 점검·지도 | 마감 없음(상시) | 가정 내 점검 항목 4개 | PASS (3언어) |
| n02 수련회 동의 | 참가 여부 회신 제출 | 6/1(월)까지 | 담임에게 신청서 제출, 비용 표 명확 | PASS (3언어) |
| n05 기자단 모집 | 자소서·동의서 제출 | 5/29(금) 17:30까지 | 이메일 tv63tv@ice.go.kr | PASS (3언어) |
| n06 건강교실 | 온라인 신청 | 모집 6/1~6/12 18:00, 프로그램 6/22~7/9 | QR/링크/카카오 'D플랜드', 표 시간·반 명확 | PASS (3언어) |
| n03 학부모교육 | 3개 프로그램 선착순 신청 | 6월 중(6/9·6/11·6/27)~마감 시 | 누리집 링크(회원가입 필요) | PASS (집계) |
| n04 진로설명회 | 참석 신청 | 설명회 6/9(화) 15:00~17:00, 신청 5/26~6/3 20시 | 온라인 설문 링크 | PASS (집계) |

→ **Comprehension Pass 전체 통과.** 모든 training+held-out 통신문에서 무엇/언제/어떻게 3질문 답 가능. ship_ready 조건5 충족.

## 7. Stopping Criteria — Verdict 판정

### ship_ready 6개 하드스톱 (전부 ✓ → 자동 종료)

| # | 조건 | 결과 | 판정 |
|---|---|---|---|
| 1 | 세 언어 train≥4.2 AND held-out≥4.0 | train 4.61/4.70/4.54, held 4.63/4.75/4.65 | ✓ |
| 2 | 세 언어 critical_count==0 | 전부 0 | ✓ |
| 3 | 세 언어 safety≥4 | 전부 5.0 | ✓ |
| 4 | 세 언어 fact≥4 AND action≥4 AND meal≥4(N/A 제외) | fact 4.0+, action 4.25+, meal N/A | ✓ |
| 5 | Comprehension Pass 전체 통과 | 6/6 통신문 PASS | ✓ |
| 6 | 직전 2회 이터 held-out 무하락 | iter-002→003 0.0, iter-003→004 0.0 — 둘 다 무하락 | ✓ |

**6/6 모두 충족 → ship_ready (하드 스톱).**

### 보조 판정 (참고)
- **diminishing_returns:** iter-002→003·iter-003→004 held-out 개선 둘 다 0.0(<0.1)이고 남은 이슈 critical 0/high 0. 트리거 조건엔 해당하나 ship_ready(하드 스톱)가 우선. 어느 쪽이든 결론은 **종료**.
- **blocking_regression:** held-out 무하락, 어떤 언어도 0.5 급락 없음(ru 유지/미세개선, en/ar 평탄), 3연속 회귀 없음 → **미해당. RU_TARGET_RULES rollback 불필요.**

## 8. Regression Watch

- **언어·축 단위 회귀 없음.** 세 언어 train·held-out 평탄(±0.00). 0.5 급락 축 없음.
- **RU 무회귀 확정:** §3 표대로 ru.md must-pass 9항목 전부 유지, 2항목 미세 개선. RU_TARGET_RULES가 회귀를 유발하지 않음.
- **status 회전 watch:** fees split-clause(n03)·grade_class_targets 빈-추출(n04, n06) 두 위양성 패밀리가 run마다 언어를 바꿔 표면화(n04 en: iter-003 ready→iter-004 admin; n03 ru: iter-003 ready→iter-004 admin). 본문은 매번 정확. **비-번역(validator/추출) 영역** 이슈로 유지.
- **generalization_gap:** −0.057 유지(held-out 우위) → 과적합 신호 없음.

## 9. Per-Language Notes

### English (en)
- **잘 작동한 지점:** 자연 영어 동사형, "Dear Parents/Guardians", 표 열 구조 보존, 영양 신호등 한정어, 본문 사실 정확 모두 iter-003 수준 유지.
- **반복 패턴 이슈:** 본문 이슈 없음. n04 en·n06 en·n03 en admin_review는 검증/추출 위양성(품질 아님). n04 en은 iter-003 ready였다가 빈-추출 위양성으로 admin 회전.
- **다음 단계 권고:** 번역 측 추가 작업 불필요(ship 수준).

### Russian (ru)
- **잘 작동한 지점:** RU_TARGET_RULES 적용 후 `Уважаемые родители!`(직역 인사 제거)·`Просим Вас` 일관화·대문자 Вы·천단위 공백·24시간제·러시아식 날짜·수명사 일치·학교개념 의미번역 전부 견고. 세 언어 중 최고(train 4.70). 회귀 0.
- **반복 패턴 이슈:** 본문 이슈 없음. n03 ru(이번 신규)·n04 ru·n06 ru admin_review는 fees/grade 추출 위양성(품질 아님).
- **다음 단계 권고:** RU 규칙 유지. rollback 불필요. 추가 번역 룰 불필요.

### Arabic (ar)
- **잘 작동한 지점:** 접근가능 MSA, `يُرجى` 요청형, 서양식 숫자 일관, 헤지라력·종교 관용어 미삽입, 표·라인 구조 보존, 영양 신호등 한정어. iter-003 수준 유지.
- **반복 패턴 이슈:** Naturalness 4.0이 여전히 세 언어 중 최저(긴 행정 복합문 경향) — 이해도 임계치 충족, ship 기준 통과. n03 ar admin_review는 fees 위양성(품질 아님).
- **다음 단계 권고:** 본문 품질 임계치 충족. (선택) ar 복합문 분절이 유일한 미세 개선 여지지만 high-leverage 아님.

## 10. Leverage Opportunities

- **비-번역(validator) 위양성 2패밀리가 admin_review의 유일한 잔여 원인.** fees split-clause 비교 + grade_class_targets 빈/비대칭 추출. 이 둘만 비-번역 영역에서 정리하면 admin_review가 거의 0으로 수렴(번역 품질과 무관, 사용자 선택 사항). 번역 측에는 high-leverage 후보 없음.

## 11. Rubric / Criteria 보강 제안

- **"status 회귀 ≠ 품질 회귀" 규약 rubric 본문 명문화 권장.** iter-002/003에 이어 iter-004에서도 동일 구분이 필요했다(n03 ru·n04 en이 게이트만 회전). 회귀 판정은 동일 통신문의 8축 점수 delta로만, status는 별도 신호로 분리한다는 규칙.
- **"RU 본문 변경 + 축 점수 무이동" 케이스 운용 해석 확정 권장.** 텍스트가 실제로 바뀌었어도 변화가 이미 천장권인 축의 임계치를 넘지 않으면 축 점수는 유지하는 게 정직한 채점이다. 단, 변경의 방향(개선/회귀/유지)은 본 보고서 §3처럼 별도로 명시한다.

## 12. Top 3 Recommendation for Engineer

번역 측에는 ship 수준이라 작업 항목이 없다. 비-번역(선택) 우선순위만:
1. (선택, 비-번역) fees split-clause 검증 비교 로직 정리 — n03 전 언어 위양성 해소.
2. (선택, 비-번역) grade_class_targets target 추출 안정화 — n04/n06 빈-추출 위양성 해소.
3. 번역: 추가 작업 없음. RU_TARGET_RULES 유지(rollback 금지).

## 13. Artifacts

- 각 통신문 `pipeline-output/{en,ru,ar}.json` — 파이프라인 결과 (18건)
- `evaluation/scores.json` — 통신문 × 언어 × 8축 매트릭스 + train/held_out 집계 + iter-003 delta + ru_change_assessment + en_ar_regression_check + ship_ready/blocking/diminishing 체크
- `evaluation/held-out-detail/n03-parent-edu-program.md`, `n04-college-info-session.md` — held-out 상세(엔지니어 비공개, 평가자 회귀 점검용; status 회귀 상세 포함)
- 직전 이터 비교: `../2026-06-02_iter-003/evaluation/feedback-report.md`, `scores.json`; `../_history.json`
