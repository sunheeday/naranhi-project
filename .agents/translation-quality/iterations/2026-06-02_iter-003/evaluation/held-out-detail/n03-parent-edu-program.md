# Held-out Detail — n03-parent-edu-program (Iter-003)

> **엔지니어 접근 금지.** 평가자 본인의 다음 이터 회귀 점검용. 스니펫 포함.

**Kind:** event-recruitment | **Issuer:** Incheon Office of Education Lifelong Learning Center
**Cultural sensitivity:** multicultural-mention
**Status:** en=admin_review (fees+urls), ru=ready_to_save, ar=admin_review (fees)

## Scores (iter-003, iter-002 delta)

| 축 | en (Δ) | ru (Δ) | ar (Δ) |
|---|---|---|---|
| Fact | 4 (0) | 4 (0) | 4 (0) |
| Action | 4 (0) | 4 (0) | 4 (0) |
| Tone | 4 (0) | 5 (0) | 5 (0) |
| Completeness | 5 (0) | 5 (0) | 5 (0) |
| Naturalness | 5 (0) | 5 (0) | 4 (0) |
| Culture | 4 (0) | 4 (0) | 4 (0) |
| Safety | 5 (0) | 5 (0) | 5 (0) |
| **Weighted** | **4.49 (0)** | **4.61 (0)** | **4.51 (0)** |

iter-002: en 4.49 / ru 4.61 / ar 4.51. **8축 무변동.** 본문 품질 iter-002 그대로 최상급. ru는 이번에 PASS·ready로 전환(검증 게이트 통과) — 점수는 동일하나 status 개선.

## Comprehension Pass
- 무엇: 3개 프로그램(세계시민 부모 클래스 / 나를 찾아 떠나는 여행 / 인천의 재발견) 중 선착순 신청
- 언제: 현재 접수 중 ~ 마감 시 (각 일자 6/9 화, 6/11 목, 6/27 토 명시)
- 어떻게: 누리집 → 평생학습프로그램 → 학부모교육, 링크 https://buly.kr/7x8GXFZ, 회원가입 필요
→ PASS (3언어). 일자·장소·대상 인원 모두 명확.

## 문화 개념 처리 (CS#3 유지 확인)
- "주춧돌학교" → en "Cornerstone School" / ru "Краеугольная школа" / ar "مدرسة حجر الزاوية" — 의미 음차+직역, 학부모교육 맥락 충분, 이해 가능. iter-002 그대로.
- "세계시민 부모 클래스" → en "Global Citizen Parent Class" / ru "Родительский класс глобального гражданина" / ar "فصل الوالدين المواطنين العالميين" 자연 처리.
- 다문화/SDGs/인권 → 정확.

## 검증 위양성 (Issue 동일 뿌리) — 회귀 점검용 기록
- **en hard_fact FAIL (2필드):**
  - fees: source `free` vs translated `material costs are to be borne by the learner`. 원문 "수강료: 무료 (단, 재료비는 학습자 부담)" → 본문 "Course Fee: Free (However, material costs are to be borne by the learner)" **완전 정확.** 추출기가 `free`와 재료비 하위절을 다른 값으로 비교 → 오탐.
  - urls: source `https://buly.kr/7x8GXFZ` vs translated `incheon ... lifelong learning center website`(누리집 경로 설명). 본문엔 URL과 경로 안내 둘 다 정확히 존재 → 추출기가 URL 대신 경로 설명을 한쪽에서 뽑음.
- **ar hard_fact FAIL:** fees: source `free` vs translated `learner bears material costs`. 본문 "رسوم الدورة: مجانية / ※ ومع ذلك، يتحمل المتعلم تكاليف المواد." **정확.** en과 동일 split-clause 위양성.
- **ru:** PASS·ready (이번 run에서 fees 추출이 대칭으로 떨어짐). iter-002에서도 점수 동일했으나 status가 admin이었다가 이번에 통과.

→ 전부 정규화/추출 비대칭(run-to-run 변동 포함). 본문 품질 회귀 없음.

## 다음 이터 회귀 watch (만약 추가 이터 발생 시)
- en placeholder 토큰 `2026-06-xx`가 본문에 새지 않는지 → **이번 본문 클린 확인**(6/9·6/11·6/27 정상, placeholder 없음).
- fees split-clause("무료(단, 재료비 부담)") 위양성이 추가 validator 작업 후 사라지는지.
- ar URL/경로 융합이 본문에 영향 주지 않는지(현재 본문 정확).
