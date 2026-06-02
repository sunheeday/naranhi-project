# Held-out Detail — n04-college-info-session (Iter-002)

> **엔지니어 접근 금지.** 평가자 본인의 다음 이터 회귀 점검용. 스니펫 포함.
> **★ 본 파일에 n04 en status 회귀 상세 분석 포함 (요청 항목).**

**Kind:** event-info-session | **Issuer:** Yeonsu Middle School
**Status:** admin_review_required (3 lang) ← iter-001: en/ru/ar 모두 ready_to_save였던 통신문

## Scores (iter-002, iter-001 delta)

| 축 | en (Δ) | ru (Δ) | ar (Δ) |
|---|---|---|---|
| Fact | 5 (0) | 5 (0) | 5 (0) |
| Action | 5 (0) | 5 (0) | 5 (0) |
| Tone | 4 (0) | 5 (0) | 5 (0) |
| Completeness | 5 (0) | 5 (0) | 5 (0) |
| Naturalness | 5 (0) | 5 (0) | 4 (0) |
| Culture | 4 (0) | 4 (0) | 4 (0) |
| Safety | 5 (0) | 5 (0) | 5 (0) |
| **Weighted** | **4.18 → 4.18 (0)** | **4.28 → 4.30 (~0)** | **4.20 → 4.20 (0)** |

iter-001: en 4.185 / ru 4.284 / ar 4.198. **8축 점수 사실상 무변동.** 번역 본문 품질은 iter-001 그대로 최상급(en/ru fact·action·natural 5).

## ★ n04 en status 회귀 판정: **검증 게이트만의 변화 — 번역 품질 하락 아님**

### 사실 관계
- iter-001: en `ready_to_save` (hard_fact PASS).
- iter-002: en `admin_review_required` (hard_fact FAIL, attempts 1).
- 유일 FAIL 항목:
  ```
  field=grade_class_targets
  issue=source fact is missing or changed in translated facts
  source_value='grade:3'
  translated_value='1 2 3'
  ```
- 본문(final_translation) 해당 문장:
  ```
  b. Target Audience: Students in grades 1, 2, and 3 of our school, and their parents (guardians)
  ```
  원문: `대상 : 본교 1, 2, 3학년 학생 및 학부모(보호자)님` → **정확히 1, 2, 3학년으로 번역됨.**

### 진단
- source 추출기가 `1, 2, 3학년`을 `grade:3`(마지막 값만 또는 단일 토큰)으로 normalize, target 추출기는 `1 2 3`(세 값)으로 normalize → set 비교 불일치. **양쪽 정규화 규칙이 비대칭.**
- CS#1이 phone/fee/URL/org을 대칭화했으나 grade_class_targets 정규화는 손대지 않아 이번에 표면화. (iter-001에서 우연히 PASS였던 것이 검증 로직 변경 과정에서 이 통신문의 grade 추출 경로가 바뀌며 FAIL로 노출된 것으로 추정.)
- **결론: 본문은 1·2·3학년을 정확히 전달. 보호자 이해도·사실 보존에 0 영향. status 후퇴는 순수 validator 산물.** → blocking_regression의 "품질 0.5 급락"에 **미해당**. Issue #1 수정 시 자동 해소.

## n04 ar dates 위양성 (병기)
```
field=dates | issue=translated facts contain a new critical value
source='2026-05-26, 2026-06-03, 2026-06-09'  translated='2026, 2028'
```
- `2028`은 본문 "2028 College Admissions Preparation Strategy"(2028 대입)에서 정당히 유래 — 원문 `2028 대입 준비 전략`에 존재. `2026`은 연도. 추출기가 연도 토큰만 뽑아 날짜 집합과 비교 → 오탐. **본문 날짜(5/26, 6/3, 6/9, 15:00~17:00) 모두 정확.**

## Comprehension Pass
- 무엇: 진로진학 설명회 참석 신청 (특성화고 안내 / 고교학점제·2028 대입 전략)
- 언제: 설명회 6/9(화) 15:00~17:00, 신청 5/26~6/3 20시
- 어떻게: 온라인 설문 https://m.site.naver.com/28Aoi, "참석 확실한 분만"
→ PASS (3언어).

## 형식 관찰 (Issue #2 근거)
- **en만** "내용+강사" 단일 표를 [내용 표] + [강사 표] 2개로 분리. 행 대응 가독 약화(강사가 어느 세션인지 인접 매칭 필요). 정보 누락은 없음 → completeness 5 유지하되 Naturalness/형식 경미 흔들림으로 기록. ru/ar은 `| № | 내용 | 강사 |` 단일 표 유지(더 우수).
- ar 표 정렬(긴 dash row) RTL에서 육안 문제 없음.

## 문화 개념
- "고교 학점제" → en "High School Credit System" / ru "система кредитов средней школы" / ar "نظام الساعات المعتمدة في المدارس الثانوية" — 정확. 단 이주민 학부모에게 제도 자체 생소(Culture 4 유지, 의미 보충 여지).
- "특성화고" → en "Specialized High Schools" 등 적절.

## 다음 이터 회귀 watch
- Issue #1(grade_class_targets, dates 정규화) 수정 후 n04 en/ar이 PASS·ready로 복귀하는지 **반드시 재확인** — status 회귀의 직접 원인이므로.
- en 표 분할이 training n06 등에서도 재현되는지(표 구조 보존 룰 효과 점검).
