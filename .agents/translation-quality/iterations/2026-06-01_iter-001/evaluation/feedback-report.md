# Feedback Report — Iter-001

> Evaluator Agent 산출물. 엔지니어 에이전트가 그대로 받아 다음 이터레이션의 입력으로 사용한다.
> **북극성(North Star):** 타겟 언어를 모국어로 쓰는 한국 거주 이주민 학부모가 통신문을 정확히 이해할 수 있는가.

**Verdict:** `needs_iteration`
**근거:** critical 0건이고 번역 본문 품질은 견고하나, 세 언어 모두 `train_avg_overall < 4.2`(en 3.86 / ar 3.98)이고, 단일 변경으로 다수 통신문이 개선될 high-leverage 후보(hard_fact 검증의 대량 위양성 + 영어 직역체)가 명확히 남아 있어 의미 있는 개선 여지가 있음. held-out 회귀 없음(gap −0.105, held-out이 오히려 높음).

**Iteration:** 001 (baseline, 직전 이터 없음)
**Date:** 2026-06-01
**Source kinds:** safety-notice / event-consent-form / recruitment-notice / recruitment-education (training); event-recruitment / event-info-session (held-out)
**Languages:** en, ru, ar (6 통신문 × 3 언어 = 18건)

---

## 1. Summary

- **언어별 가중 평균 (training):** en=3.86 , ru=4.10 , ar=3.98
- **언어별 가중 평균 (held-out):** en=4.02 , ru=4.16 , ar=4.08
- **Critical 건수:** 전 언어·전 통신문 0건 (training 0/0/0, held-out 0/0/0)
- **train_avg_overall=3.98 / held_out_avg_overall=4.08 / generalization_gap=−0.105** (held-out이 더 높음 → 과적합 신호 없음. baseline이므로 train 데이터로 튜닝 전 상태)
- **직전 이터레이션 대비:** N/A (최초 이터, baseline)
- **한 줄 요약:** 본문 번역은 전반적으로 정확·자연스럽고 안전 위험 없음. 그러나 (1) hard_fact 검증이 18건 중 17건을 admin_review로 보내는 **대량 위양성**(전화번호 국제형 변환·"무료"→"0 krw"·날짜 범위 병합·연락처 중복제거)이 파이프라인 신뢰도를 갉아먹고, (2) 영어가 한국어 구조를 직역하는 경향(명령형 나열, "Confirm helmet wearing" 류)으로 세 언어 중 가장 낮음. meal/allergy 통신문은 이번 세트에 없음(meal 축 전건 N/A).

> **meal 축 처리 주석:** 이번 6개 통신문에는 식단/식재료 정보가 없다. meal 축은 전건 N/A(rubric 0점=해당없음)로 두고, 가중평균은 meal 가중치(0.7)를 분모에서 제외해 계산했다(meal을 0점으로 합산하면 부당 감점되므로). scores.json의 `note` 참조.

## 2. Score Matrix

### Training 평균 (n01, n02, n05, n06)

| 축 | en | ru | ar |
|---|---|---|---|
| 1. Fact Preservation | 4.0 | 4.0 | 4.0 |
| 2. Action Clarity | 4.25 | 4.0 | 4.0 |
| 3. Tone & Register | 4.0 | 5.0 | 5.0 |
| 4. Completeness | 5.0 | 5.0 | 5.0 |
| 5. Naturalness | 4.0 | 4.75 | 4.0 |
| 6. Culture & Linguistic | 3.75 | 4.5 | 4.0 |
| 7. Meal / Allergy | N/A | N/A | N/A |
| 8. Safety & Risk | 5.0 | 5.0 | 5.0 |
| **Weighted Avg** | **3.86** | **4.10** | **3.98** |
| **Critical count** | 0 | 0 | 0 |

### Held-out 평균 (집계만, n03·n04 — 디테일 격리)

| 축 | en | ru | ar |
|---|---|---|---|
| **Weighted Avg** | **4.02** | **4.16** | **4.08** |
| **Critical count** | 0 | 0 | 0 |

전체 매트릭스(통신문 단위)는 `evaluation/scores.json` 참조. held-out 통신문별 스니펫·상세 진단은 본 보고서에 포함하지 않으며 `evaluation/held-out-detail/`에만 있다.

## 3. Priority Issues (엔지니어가 이번 이터레이션에서 다룰 항목)

### Issue #1 — hard_fact 검증의 대량 위양성으로 18건 중 17건이 admin_review로 직행

- **언어:** 공통 (en/ru/ar 전부)
- **축:** Fact (파이프라인 신뢰도) — 본문 자체는 정확하나 검증 게이트가 과민
- **심각도:** high (지렛대형)
- **회귀 여부:** 신규 (baseline)
- **원문/번역/추출 스니펫:**
  - 전화번호 정규화: source `032-320-0096` → 추출된 target fact `phone:82323200096` (ru n01), `phone:82324208137` (ru n05). 본문 final_translation에는 `032-320-0096`이 **정확히 그대로** 있는데, 추출기가 국제(+82) 형식으로 바꿔 source와 mismatch 처리.
  - "무료" 처리: source fact `free` → translated fact `0 krw` / `0` (n06 전 언어). 본문은 "Free / Бесплатно / مجانية"로 정확.
  - 날짜 범위 병합: source `2026-06-22, 2026-07-09` → translated `2026-06-22_2026-07-09` (n06 en). 같은 사실의 표기차일 뿐.
  - 연락처 묶음/분해: `기관명+전화`가 한쪽엔 묶이고 한쪽엔 분리돼 "missing"과 "new critical value"가 동시에 뜸 (n01 전 언어).
- **진단:** validator가 비교하는 것은 **본문 텍스트**가 아니라 source/target에서 각각 재추출한 normalized fact 리스트다. 이 정규화 단계가 (a) 한국 전화번호에 국가코드 +82를 임의로 붙이고, (b) "무료"를 `0 krw`로 캐스팅하고, (c) 날짜 범위를 단일 토큰으로 병합하고, (d) 연락처를 기관명/번호로 분해·재조합하면서 source 쪽 정규화와 target 쪽 정규화가 불일치 → 거의 모든 통신문이 FAIL. 실제 보호자가 받는 final_translation의 사실은 대부분 정확하다.
- **추정 원인 (어느 단계 / 어느 룰):**
  - hard_fact 추출/정규화 로직(`validators.py` 계열의 전화번호 normalize — 한국 0 prefix를 +82로 치환하는 규칙이 source/target 비대칭으로 적용)
  - "무료/free"의 fee 정규화가 `0 krw`로 강제 캐스팅되어 source의 `free`와 어긋남
  - 날짜·연락처 정규화의 묶음 단위 불일치(set 비교 시 grouping 차이를 mismatch로 처리)
- **권고 방향:** (코드 직접 수정 금지, 방향만)
  - 전화번호 비교는 **숫자만 추출해 정규화한 canonical form**으로 source/target 양쪽 동일 규칙 적용 — 국가코드 부여 여부를 한쪽에만 적용하지 않도록 대칭화.
  - `free`/`무료`/`0` 같은 "비용 없음" 표현을 하나의 동치 클래스로 매핑(`0 == free == 무료`)해 fee mismatch 위양성 제거.
  - 날짜 범위(`A~B`)와 개별 날짜(`A`,`B`)를 동치로 보는 비교 룰, 연락처는 기관명·번호·이메일을 **필드별로 분해 후 집합 비교**해 grouping 차이가 mismatch로 새지 않도록.
  - 본문에 사실이 보존됐는지(텍스트 포함 검사)를 보조 신호로 추가해 위양성 게이트를 완화.

### Issue #2 — 영어 직역체: 한국어 명령·구조를 그대로 옮겨 가독·자연스러움 저하

- **언어:** en
- **축:** Naturalness / Culture / Action
- **심각도:** medium
- **회귀 여부:** 신규
- **원문 스니펫 (n01):**
  ```
  ☑ 안전모 착용 여부 확인하기
  무면허 전동킥보드·위험 자전거 운행 금지 지도하기
  ```
- **번역 스니펫 (n01 en):**
  ```
  ☑ Confirm helmet wearing.
  Guide against operating unlicensed electric kickboards and dangerous bicycles.
  Continuously converse with them to prevent dangerous riding with friends.
  ```
- **진단:** 의미는 전달되나 "Confirm helmet wearing", "converse with them", "Guide against operating ..." 등은 영어 학교 통신문에서 쓰지 않는 직역투다. en.md가 권고하는 "Make sure your child wears a helmet", "Talk with your child about ..." 같은 행동 중심·자연 영어로 가지 못함. 또한 안전 통신문 본문이 "Prohibit ... / Prohibit ..." 식 명사 명령 나열로 흘러 보호자 친화도가 떨어짐(반면 ru/ar은 정중 요청형으로 잘 풀림).
- **추정 원인:** 영어 단계 프롬프트의 register/anti-literal 룰이 약함. en.md "Direct translation guardrails", "Action template(WHAT/WHEN/HOW)" 룰이 프롬프트에 충분히 박혀 있지 않음.
- **권고 방향:** 영어 전용(또는 `target==en`) 프롬프트에 en.md의 직역 안티패턴 예시와 "parent-facing action 문장은 'Make sure your child ...' / 'Please talk with your child about ...' 형태로" 룰을 명시. 체크리스트형 안전수칙은 명령 나열 대신 보호자 행동 동사로 재구성.

### Issue #3 — 한국 학교/행정 특유 개념·교육 콘텐츠 항목의 의미 미해소

- **언어:** en (대표), 일부 공통
- **축:** Culture & Linguistic
- **심각도:** medium
- **원문 스니펫 (n06 건강수업 표):**
  ```
  - 신호등을 지켜라
  ```
- **번역 스니펫 (n06 en / ar):**
  ```
  - Obey the Traffic Light (Eating Guide)   ← en은 괄호 보충 시도(👍)
  - اتبع إشارة المرور                         ← ar은 문자 그대로 "교통신호 지켜라"
  ```
- **진단:** "신호등을 지켜라"는 식품 영양 신호등(나트륨·당 색상 등급) 교육 항목인데, ar/ru는 도로 교통신호로 읽히게 직역됨. en은 "(Eating Guide)" 보충으로 그나마 낫지만 일관되지 않음. 또한 "수련회(training camp)", "주춧돌학교(Cornerstone School)" 등 한국 학교·행정 고유 개념이 음역/직역만 되어 이주민 학부모가 목적을 바로 잡기 어려운 지점이 산재.
- **추정 원인:** 한국 학교/교육행정 특유 개념에 대한 풀어쓰기 룰·사전 매핑이 약함. 사실 추가 금지 원칙과 충돌하지 않는 범위의 "원어 병기 + 짧은 의미 보충" 가이드 부재.
- **권고 방향:** 사전 매핑이 있는 한국 학교 개념에 한해 "원어 병기 + 1구 의미 보충" 허용 룰을 세 언어 공통으로. 교육 콘텐츠 표 셀처럼 맥락 없는 짧은 제목은 직역 위험이 크므로, 표/리스트 항목 번역 시 인접 칼럼 맥락을 활용하라는 룰 검토.

### Issue #4 — 러시아어·아랍어: 본문 인사말 의례구 처리 양호하나 표기·격식 미세 흔들림

- **언어:** ru, ar
- **축:** Tone / Naturalness
- **심각도:** low
- **진단:** ru/ar는 `Уважаемые родители!` / `حضرات أولياء الأمور` 정중 호명, `Просим Вас` / `يُرجى` 요청형, 24시간제, 아랍어 서양식 숫자 등 criteria를 대체로 잘 지킴(세 언어 중 톤 최고). 잔여 흔들림: (a) 학교 모토 `禮·智` → "Вежливость · Мудрость" / "الأدب · الحكمة"에서 한국식 중점(·) 잔존, (b) 카카오 채널명 `D플랜드`가 본문에 한글로 남음(검색용 고유명이라 일부 허용되나 음역 병기 권장), (c) 아랍어 RTL에서 한글 고유명사·URL 혼용 BiDi는 육안상 문제 없음.
- **권고 방향:** 한국식 중점(·)→각 언어 구두점(en `,`/`/`, ru `,`/`·`회피, ar `،`)으로 치환 룰. 검색 키워드형 고유명은 "음역(원어)" 병기 권장.

## 4. Leverage Opportunities

- **(최우선) Issue #1 단일 수정의 파급력:** hard_fact 정규화의 대칭화(전화번호 canonical, free=0 동치, 날짜·연락처 grouping 동치)만으로 18건 중 다수가 FAIL→PASS로 전환될 가능성이 매우 높다. 번역 본문을 건드리지 않고 파이프라인 통과율을 끌어올리는 가장 큰 지렛대. (검증 통과 자체는 rubric 점수에 직접 반영되진 않지만, admin_review_required 폭증은 운영 신뢰도·ship 가능성의 핵심 게이트.)
- **(차순위) Issue #2 영어 register 룰 강화:** en 세 training 통신문의 Naturalness/Culture를 동시에 끌어올려 en train_avg를 4.2 근처로 밀어올릴 단일 프롬프트 변경 후보.

## 5. Regression Watch

- N/A — 최초 이터레이션(baseline). 다음 이터부터 본 점수를 기준선으로 회귀 점검.
- 주의: 현재 held_out(4.08) > train(3.98)로 generalization_gap이 음수다. 다음 이터에서 train 데이터에 맞춰 프롬프트를 강화한 뒤 이 gap이 +0.3 이상으로 벌어지면 과적합 신호 → blocking_regression 검토.

## 6. Per-Language Notes

### English (en)
- **잘 작동한 지점:** 사실 보존(본문 기준), 완전성 우수. n04는 검증도 통과(`ready_to_save`)하며 본문 품질 최고. 한국 개념에 "(Eating Guide)" 등 보충 시도가 보임.
- **반복 패턴 이슈:** 직역체("Confirm helmet wearing", "converse with them", "Prohibit ..." 나열), 보호자 행동 문장이 자연 영어가 아님. 세 언어 중 톤·자연스러움 최저.
- **다음 단계 권고:** 영어 전용 register/anti-literal 룰 강화(Issue #2). 안전 체크리스트를 보호자 행동 동사형으로.

### Russian (ru)
- **잘 작동한 지점:** 정중 호명·`Просим Вас` 요청형·24시간제·금액 공백 구분·격수 일치 모두 양호. 세 언어 중 종합 최고(train 4.10). 직역 안티패턴 거의 없음.
- **반복 패턴 이슈:** 한국식 중점(·) 잔존, 카카오 채널명 한글 잔존. 사실상 미세 표기 수준.
- **다음 단계 권고:** 구두점 정규화 룰만 보완하면 4.2+ 진입 가능.

### Arabic (ar)
- **잘 작동한 지점:** MSA 접근가능 등록, `يُرجى` 요청형, 서양식 숫자 일관, 헤지라력·종교 관용어 임의 삽입 없음(criteria 충실). RTL/BiDi 육안 문제 없음.
- **반복 패턴 이슈:** 맥락 없는 표 항목 직역("اتبع إشارة المرور" = 영양 신호등을 도로신호로), 한국 개념 음역 후 의미 보충 부족.
- **다음 단계 권고:** 표/리스트 짧은 항목의 맥락 반영 + 한국 학교 개념 의미 보충 룰(Issue #3).

## 7. Rubric / Criteria 보강 제안

- **meal 축 N/A의 가중평균 처리 규약 명문화 필요:** 현재 rubric은 meal=0을 "해당없음"으로 정의하지만 가중평균 공식은 0을 그대로 합산해 식단 없는 통신문이 부당 감점된다. "meal=N/A인 통신문은 meal 항(0.7)을 분자·분모에서 동시 제외"를 공식으로 명시 권장. (본 평가는 이 방식으로 계산함.)
- **파이프라인 검증 위양성과 번역 품질의 분리 채점 가이드 필요:** hard_fact validator FAIL이 곧 Fact 축 저점은 아니다(본문은 정확한데 정규화 비대칭으로 FAIL). "검증 status"와 "Fact 축 점수"를 분리하라는 명시 규칙을 rubric에 추가 권장.
- 한국 학교/행정 고유 개념의 "원어 병기 + 의미 보충" 허용 경계(사실 추가 금지와의 선)를 language-criteria에 더 구체적 예시로.

## 8. Top 3 Recommendation for Engineer

1. **Issue #1** — hard_fact 정규화 대칭화(전화번호 canonical / free=0 동치 / 날짜·연락처 grouping 동치). 18건 중 17건 admin_review의 근본 원인, 최대 지렛대.
2. **Issue #2** — 영어 전용 register/anti-literal 룰 강화. en train_avg를 4.2 근처로 끌어올릴 단일 프롬프트 변경.
3. **Issue #3** — 한국 학교 개념·표 항목의 맥락 반영 + 의미 보충 룰(세 언어 공통). Culture 축 동시 개선.

## 9. Artifacts

- 각 통신문 `pipeline-output/{en,ru,ar}.json` — 파이프라인 결과 (18건)
- `evaluation/scores.json` — 통신문 × 언어 × 8축 점수 매트릭스 + train/held_out 집계
- `evaluation/held-out-detail/n03-parent-edu-program.md`, `n04-college-info-session.md` — held-out 상세(엔지니어 비공개, 평가자 회귀 점검용)
- 직전 이터레이션 비교: 없음 (baseline)
