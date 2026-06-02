# Held-out Detail — n03-parent-edu-program (평가자 전용 / 엔지니어 비공개)

> 격리 정책: 이 파일의 원문/번역/back-translation 스니펫·구체 진단은 feedback-report.md나 엔지니어에게 공유 금지. 다음 이터 회귀 점검용.

**Kind:** event-recruitment (학부모교육 3개 프로그램 모집) / cultural_sensitivity: multicultural-mention
**Status (pipeline):** en/ru/ar 모두 `admin_review_required` (hard_fact FAIL — 위양성 다수)

## 점수 (8축, meal=N/A)

| 축 | en | ru | ar |
|---|---|---|---|
| Fact | 4 | 4 | 4 |
| Action | 4 | 4 | 4 |
| Tone | 4 | 5 | 5 |
| Completeness | 5 | 5 | 5 |
| Naturalness | 4 | 5 | 4 |
| Culture | 4 | 4 | 4 |
| Meal | N/A | N/A | N/A |
| Safety | 5 | 5 | 5 |
| **Weighted** | **3.95** | **4.18** | **4.07** |
| critical | 0 | 0 | 0 |

## Comprehension Pass

- **무엇:** 3개 학부모교육 프로그램 중 선택해 온라인 선착순 신청 → 세 언어 모두 명확.
- **언제:** 6/9(화), 6/11(목), 6/27(토) 각 프로그램 일시 + "현재 접수 중~마감 시" → 일시는 명확. "마감 시"는 원문 자체가 모호(번역 탓 아님).
- **어떻게/어디서:** 평생학습관 누리집 → 회원가입 필요 → buly.kr 링크. 장소(동막역 3번 출구 앞 강의실) 명확. 세 언어 모두 답 가능.

## 발견 이슈 (스니펫 포함, 격리)

- **hard_fact 위양성(전 언어):** "수강료 무료(재료비 학습자 부담)" → fees `0` vs `material costs are borne by the learner` / `0 krw, يتحمل المتعلم...`로 "new critical value" FAIL. 전화번호 `032-899-1536`→`82328991536`(ru) 국제형 변환 위양성. 날짜 "6월 중"·"현재 접수 중"의 자연어가 정규화에서 mismatch. → 모두 Issue #1 패턴, 본문은 정확.
- **en culture(4):** 프로그램명 직역 양호하나 "Cornerstone School(주춧돌학교)"이 음역+직역으로 목적 불명확. "A Journey to Find Myself, Spring, Spring, Spring(봄봄봄)" 제목 반복이 영어로 어색.
- **ar naturalness(4):** 날짜 표기 `2026/6/9` 슬래시형 — criteria 권장은 `9 يونيو 2026`. 본문 다른 곳과 형식 흔들림. 화살표 글머리 `◀`(RTL 방향 맞음).
- **ru(최고, 4.18):** 정중 호명·요청형·날짜형 `9 июня 2026 г. (вт)` 모두 criteria 부합. 거의 흠 없음.
- **공통 culture:** multicultural-mention(세계시민/다문화/SDGs) 내용이 직역으로 잘 전달됨. 종교·문화 임의 보충 없음(양호).

## 다음 이터 회귀 워치
- ar 날짜 슬래시형(`2026/6/9`)이 다음 이터에서 `9 يونيو 2026`로 정규화되는지.
- "Cornerstone School" 등 한국 행정 고유명 의미 보충 개선 여부.
