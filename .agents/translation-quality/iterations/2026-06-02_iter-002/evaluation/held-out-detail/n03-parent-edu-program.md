# Held-out Detail — n03-parent-edu-program (Iter-002)

> **엔지니어 접근 금지.** 평가자 본인의 다음 이터 회귀 점검용. 스니펫 포함.

**Kind:** event-recruitment | **Issuer:** Incheon Office of Education Lifelong Learning Center
**Cultural sensitivity:** multicultural-mention | **Status:** admin_review_required (3 lang)

## Scores (iter-002, iter-001 delta)

| 축 | en (Δ) | ru (Δ) | ar (Δ) |
|---|---|---|---|
| Fact | 4 (0) | 4 (0) | 4 (0) |
| Action | 4 (0) | 4 (0) | 4 (0) |
| Tone | 4 (0) | 5 (0) | 5 (0) |
| Completeness | 5 (0) | 5 (0) | 5 (0) |
| Naturalness | 5 (+1) | 5 (0) | 4 (0) |
| Culture | 4 (0) | 4 (0) | 4 (0) |
| Safety | 5 (0) | 5 (0) | 5 (0) |
| **Weighted** | **4.49 (+0.64)** | **4.63 (+0.59)** | **4.55 (+0.60)** |

iter-001: en 3.852 / ru 4.037 / ar 3.951. en Naturalness +1.0이 CS#2 일반화 효과(held-out에도 직역체 해소 전이).

## Comprehension Pass
- 무엇: 3개 프로그램(세계시민 부모 클래스 / 나를 찾아 떠나는 여행 / 인천의 재발견) 중 선착순 신청
- 언제: 현재 접수 중 ~ 마감 시 (각 일자 6/9 화, 6/11 목, 6/27 토 명시)
- 어떻게: 누리집 → 평생학습프로그램 → 학부모교육, 링크 https://buly.kr/7x8GXFZ, 회원가입 필요
→ PASS (3언어). 일자·장소·대상 인원 모두 명확.

## 문화 개념 처리 (CS#3 일반화 확인)
- "주춧돌학교" → en "Cornerstone School" / ru "Краеугольная школа" / ar "مدرسة حجر الزاوية" — 의미 음차+직역. 학부모교육 맥락이 제목·본문에 충분해 이해 가능. (held-out에서도 음역만 되던 iter-001 우려 완화.)
- "세계시민 부모 클래스" → 3언어 모두 "World Citizen Parent / граждан мира / المواطنين العالميين" 자연 처리.
- 다문화/SDGs/인권 → 정확.

## 검증 위양성 (Issue #1 동일 뿌리) — 회귀 점검용 기록
hard_fact FAIL, 전 언어. 본문 사실은 정확. 위양성 필드:
- dates: source `2026, 2026. 6월 중, 현재 접수 중` vs translated `2026-06-09, 2026-06-11, 2026-06-27, 2026-06-xx`(en) / `2026-06`(ru,ar). `6월 중`·`현재 접수 중` fuzzy 토큰 비대칭. en은 `2026-06-xx` placeholder성 토큰 생성(추출기 산물, 본문엔 없음).
- deadlines: source `마감 시` vs translated `until registration closes` / `حتى إغلاق التسجيل` — 같은 의미, 토큰 mismatch.
- fees: source `free` vs translated `free, material costs borne by learner`(en) — 원문 "무료(단, 재료비는 학습자 부담)" 그대로 정확 번역인데 추출기가 free 단일값과 비교해 "new critical value" 오탐. **본문은 원문 충실.**
- urls: source `https://buly.kr/7x8GXFZ` vs translated ar `موقع ... ← ... ← تعليم الوالدين`(누리집 경로 설명) — URL과 경로 안내를 같은 필드로 비교. 본문엔 URL·경로 둘 다 정확.
- grade_class_targets: source `전체 학부모 20명, 초등학교 학부모 20명` vs translated `elementary school students`(ar) 등 — 대상 라벨 정규화 비대칭. ar은 "students"로 축약 추출(본문은 "أولياء أمور طلاب المرحلة الابتدائية"=초등 학부모로 정확).

→ 전부 정규화 비대칭. 다음 이터 Issue #1 수정 후 PASS 전환 기대 대상. 본문 품질 회귀 없음.

## 다음 이터 회귀 watch
- en placeholder 토큰 `2026-06-xx`가 본문에 새지 않는지 재확인(현재는 추출기에만 존재, 본문 클린).
- ar URL/경로 융합이 본문에 영향 주지 않는지.
