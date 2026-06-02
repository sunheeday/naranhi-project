# Held-out Detail — n04-college-info-session (Iter-003)

> **엔지니어 접근 금지.** 평가자 본인의 다음 이터 회귀 점검용. 스니펫 포함.
> **★ iter-002 status 회귀(n04 en/ar)의 복구 확인 포함.**

**Kind:** event-info-session | **Issuer:** Yeonsu Middle School
**Status:** en=ready_to_save, ru=admin_review (grade_class_targets), ar=ready_to_save

## Scores (iter-003, iter-002 delta)

| 축 | en (Δ) | ru (Δ) | ar (Δ) |
|---|---|---|---|
| Fact | 5 (0) | 5 (0) | 5 (0) |
| Action | 5 (0) | 5 (0) | 5 (0) |
| Tone | 4 (0) | 5 (0) | 5 (0) |
| Completeness | 5 (0) | 5 (0) | 5 (0) |
| Naturalness | 5 (0) | 5 (0) | 4 (0) |
| Culture | 4 (0) | 4 (0) | 4 (0) |
| Safety | 5 (0) | 5 (0) | 5 (0) |
| **Weighted** | **4.78 (0)** | **4.89 (0)** | **4.79 (0)** |

iter-002: en 4.775 / ru 4.887 / ar 4.789. **8축 무변동.** 본문 최상급 유지(en/ru fact·action·natural 5). 이 통신문이 6건 중 최고 점수대.

## ★ iter-002 status 회귀 복구 확인 (요청 항목)
- **n04 en:** iter-002 admin_review(`grade_class_targets` src 'grade:3' vs tgt '1 2 3') → **iter-003 ready_to_save (hard_fact PASS, attempts 1).** CS#1의 grade_class_targets 정규화 대칭화가 적중. 본문 `b. Target Audience: Students in grades 1, 2, and 3 of our school, and their parents (guardians)` — 원문 `대상 : 본교 1, 2, 3학년 ...` 정확. **status 회귀 완전 해소.**
- **n04 ar:** iter-002 admin_review(`dates` 2028 위양성) → **iter-003 ready_to_save (hard_fact PASS, attempts 0).** `2028 대입 준비 전략`의 2028이 더 이상 critical date로 오탐되지 않음. 본문 날짜(6/9 15:00~17:00, 신청 5/26~6/3 20시) 모두 정확.

## n04 ru 신규 위양성 (회귀 점검용)
- hard_fact FAIL: `grade_class_targets` source `grade:1, grade:2, grade:3` vs translated `''`(빈 집합).
- 본문: `б. Целевая аудитория: Учащиеся 1, 2 и 3 классов нашей школы, а также их родители (опекуны).` → **1·2·3학년 정확 번역.** target 추출기가 이 run에서 grade 집합을 못 뽑음(LLM 추출 run-to-run 변동). en/ar은 같은 통신문에서 PASS — 즉 동일 root가 이번엔 ru에서만 표면화. **본문 품질 0 영향.**

## Comprehension Pass
- 무엇: 진로진학 설명회 참석 신청 (특성화고 안내 / 고교학점제·2028 대입 전략)
- 언제: 설명회 6/9(화) 15:00~17:00, 신청 5/26~6/3 20시
- 어떻게: 온라인 설문 https://m.site.naver.com/28Aoi, "참석 확실한 분만"
→ PASS (3언어).

## 형식/문화 관찰
- **en 표 분할 회귀 없음:** iter-002에서 "내용+강사" 표를 2개로 쪼갰던 경향이 이번 n04 en에는 **단일 표 `| No. | Session Content | Speaker |`로 유지**(CS#2 표 열 구조 보존 효과). ru/ar도 단일 표. → Issue #2 해소 확인.
- "고교 학점제" → en "High School Credit System" / ru "система кредитов" / ar "نظام الساعات المعتمدة" 정확. 제도 자체는 이주민 학부모에게 생소(Culture 4 유지) — 단 ship 임계치 충족.
- "특성화고" → en "Vocational/Specialized High Schools" 등 적절.

## 다음 이터 회귀 watch (만약 추가 이터 발생 시)
- n04 ru grade_class_targets 빈 집합 위양성이 추가 validator 작업 후 PASS 전환하는지(en/ar은 이미 PASS).
- en 단일 표 유지가 다른 표-풍부 통신문에서도 안정적인지(현재 n04·n06 모두 양호).
