# Held-out Detail — n04-college-info-session (평가자 전용 / 엔지니어 비공개)

> 격리 정책: 이 파일의 스니펫·구체 진단은 feedback-report.md나 엔지니어에게 공유 금지. 다음 이터 회귀 점검용.

**Kind:** event-info-session (진로진학 설명회) / cultural_sensitivity: neutral
**Status (pipeline):** en=`ready_to_save`(유일하게 검증 통과), ru/ar=`admin_review_required`(grade_class_targets 단일 위양성)

## 점수 (8축, meal=N/A)

| 축 | en | ru | ar |
|---|---|---|---|
| Fact | 5 | 5 | 5 |
| Action | 5 | 5 | 5 |
| Tone | 4 | 5 | 5 |
| Completeness | 5 | 5 | 5 |
| Naturalness | 5 | 5 | 4 |
| Culture | 4 | 4 | 4 |
| Meal | N/A | N/A | N/A |
| Safety | 5 | 5 | 5 |
| **Weighted** | **4.41** | **4.55** | **4.47** |
| critical | 0 | 0 | 0 |

→ 이번 세트 최고 통신문. 세 언어 모두 4.4+ (ship 기준 4.2 상회). 짧고 사실 밀도 적당, 표 구조 단순.

## Comprehension Pass

- **무엇:** 진로진학 설명회 참석 희망 시 온라인 설문으로 신청 → 세 언어 명확.
- **언제:** 설명회 6/9(화) 15:00~17:00, 신청 5/26(화)~6/3(수) 20:00 → 명확(요일 동반).
- **어떻게/어디서:** naver 설문 링크, 장소(신관 2층 다목적 회의실) 명확. "꼭 참석할 분만 신청" 단서도 전달. 세 언어 답 가능.

## 발견 이슈 (스니펫 포함, 격리)

- **hard_fact(ru/ar):** 유일 이슈는 `grade_class_targets`: source `grade:3` vs translated `1, 2, 3` / `1,2,3`. 원문 "1,2,3학년"을 정확히 옮긴 것인데 추출기가 source를 `grade:3`로만 잡아 위양성. 본문 정확 → Issue #1 패턴(추출 누락측 오류). en은 통과.
- **en(4.41):** 인사말 "In May, as the greenery of early summer deepens, we wish health and peace to your families." — 원문 의례구를 충실 번역. en.md는 영어 통신문에서 의례 인사 생략/축약 권장 → 직역 흔적(감점 사유는 아니나 자연스러움 한 끗). tone 4.
- **ar(naturalness 4):** "مدير المدرسة"(교장)로 끝맺음 — 원문 "연수중학교장"의 학교명 누락(축약). 본문 상단엔 학교 정보 있음. 미세. 날짜 `9 يونيو 2026 (الثلاثاء)` 형식 양호.
- **culture(공통 4):** "특성화고/고교학점제/2028 대입" 등 한국 입시 고유 개념 직역. 이주민 학부모에게 배경 설명 부재(사실 추가 금지와 트레이드오프).

## 다음 이터 회귀 워치
- en 의례 인사 축약 룰 적용 시 이 통신문 tone이 5로 오르는지(과축약으로 사실 손실 없는지 동시 확인).
- grade_class_targets 추출 위양성(Issue #1)이 해소되면 ru/ar도 `ready_to_save` 전환되어야 함 — 회귀 지표.
- 이번 세트 최고점 통신문이므로 다음 이터에서 점수 하락 시 즉시 regression 플래그.
