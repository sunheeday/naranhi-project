# Phase 2 — RU_TARGET_RULES 작성 (iter-004 준비)

Verdict: `partial` — ru `target_rules` 슬롯만 채움. 신규 필드/다단계 주입은 의도적으로 하지 않음 (회귀 리스크 회피).

## 목적

iter-003에서 ru는 세 언어 중 최고 점수(train 4.70 / held 4.63·실측 4.75, critical 0).
따라서 ru 규칙의 목적은 **점수 상승 강요가 아니라 잘 되고 있는 동작의 명문화·고정 + 회귀 방지**다.
team-lead의 출력 무변화 리팩터로 ru 슬롯(`RU_TARGET_RULES`)이 빈 문자열로 남아 있었고, 이번에 그 슬롯만 채운다.

## 변경 범위

- `backend/app/translation/prompts.py`
  - `RU_TARGET_RULES` 상수(이전 `""`)를 EN/AR과 동일한 스타일의 불릿 규칙으로 채움.
  - `LANGUAGE_PROFILES["ru"]`는 이미 `RU_TARGET_RULES`를 참조하므로 **레지스트리는 자동 반영** (구조 변경 없음).
  - `EN_TARGET_RULES`, `AR_TARGET_RULES`, `LanguageProfile` 정의, 모든 stage 프롬프트 함수는 **무수정**.
- `context_tone_rules` 등 신규 필드 **추가하지 않음** (지시: 여러 언어/단계 주입은 en/ar 출력도 바꾸므로 리스크 큼 → 하지 마라).

## 단일 출처 매핑 (ru.md → 규칙)

각 불릿은 `language-criteria/ru.md`에 근거가 있다. ru.md에 없는 규칙은 넣지 않았다.

| RU_TARGET_RULES 불릿 | ru.md 근거 |
|---|---|
| Register lock: 표준 행정 등록, 문학·고전 어휘(소블라고볼리테 등) 금지, 2언어 화자 고려 일상 어휘, 추상명사 남발 금지 | "Migrant Parent Profile" + "이 페르소나의 평가 기준" (소비에트식 표준 행정 등록, 문학적 어휘 회피, 추상 명사 남발 금지) + 엔지니어 항목 #1 |
| 본문 일관 대문자 `Вы` + 적절 시 `Уважаемые родители!` 호명, 의례적 한국어 오프너 직역 금지 | 체크리스트 Register #1·#3, Cultural Mapping, 엔지니어 항목 #1, 직역 안티패턴(`안녕하십니까`) |
| 명령형 직접 사용 회피 → `Просим Вас + verb` / `Пожалуйста,...` / `Просим обратить внимание`, 단락당 1회 | 체크리스트 Register #2, 엔지니어 항목 #2, 안티패턴(`... 해 주시기 바랍니다` 반복 1회 권장) |
| 수-명사 일치: 1 주격단수 / 2–4 생격단수 / 5+ 생격복수 (`1 ребёнок / 2 ребёнка / 5 детей`), `2 ребёнок` 금지 | Grammar 체크리스트(수 일치), 엔지니어 항목 #3, 자주 깨지는 신호 표 |
| 동사 상(вид): 일회성=완료 / 반복·진행=불완료 | Grammar 체크리스트(동사 상), 엔지니어 항목 #4 |
| 24시간제(`14:30`), 12h/한국식(`AM 9`) 금지; 날짜 `1 июня 2026 г. (понедельник)` 월 소문자 | Numbers/Dates/Times 체크리스트, 엔지니어 항목 #5, 안티패턴(`с AM 9`) |
| 금액: 천단위 공백 구분, 첫 등장 통화 풀어쓰기 후 KRW/₩ (`30 000 южнокорейских вон (KRW)`) | Numbers 체크리스트(금액) |
| 전화·계좌 한국 형식 그대로, 국제번호 변환 금지 | Numbers 체크리스트(전화번호), 엔지니어 항목 #6 |
| 고유명사(학교·학생명) 주격 유지, 임의 격변화 금지, 인용부호 «»/" ", 한국식 「」 금지 | Grammar 체크리스트(격 일치, 따옴표), 엔지니어 항목 #7, Punctuation |
| 줄임표 `…`, 한국식 중점(·) → 콤마/세미콜론 | Punctuation/Typography 체크리스트 |
| 러시아 문화 설명(정교회·지역 풍습) 임의 추가 금지, 학교 개념은 의미/사전 매핑(맨 음역 금지) | Cultural Mapping 체크리스트, 엔지니어 항목 #8, 자주 깨지는 신호(맨 음역) |
| 알레르겐 `Содержит: ...` 형식, 사전 매핑만 | Meal/Allergy 체크리스트, 엔지니어 항목 #9 |

의도적으로 **넣지 않은 것**: ru.md가 "사실 추가 금지" 때문에 권장하지 않는다고 명시한 항목들
(예: 학년에 `(초등 X학년)` 보충, 학교 행사명 라틴 음역 + 러시아어 설명 보충). 규칙에 반영하지 않음.

## 회귀 리스크

- **en/ar**: 없음. EN/AR 상수와 모든 stage 프롬프트 함수가 무수정이고, ru만 레지스트리 값이 달라짐 (아래 해시 검증으로 확인).
- **ru**: 낮음. 규칙은 이미 관찰된 모범 동작을 명문화한 것이라 새 스타일 강제가 아님. 스모크에서 hf=passed/ct=passed 유지. 다만 신규 룰은 프롬프트 길이를 늘리므로 미세한 출력 변동 가능 → iter-004 풀런에서 점수 모니터링 필요(team-lead).

## Rollback 방법

ru 슬롯만 건드렸으므로 롤백은 단순하다.
- 파일 단위: `git checkout HEAD -- backend/app/translation/prompts.py`
- 또는 부분 롤백: `prompts.py`의 `RU_TARGET_RULES` 값을 다시 `""`로 되돌리면 iter-003 출력 무변화 상태(team-lead 리팩터 직후)로 복귀.
  레지스트리/함수는 안 건드렸으므로 그 한 상수만 비우면 끝.

## 검증 결과

1. **en/ar 출력 무변화 (바이트 동일)** — `git show HEAD:...prompts.py`를 임시 모듈로 로드해 `translate_en_to_target_prompt` 출력 sha256 비교:
   - en: old=`5282eb02226bf82a` new=`5282eb02226bf82a` → IDENTICAL
   - ar: old=`0de44f2c55380a5e` new=`0de44f2c55380a5e` → IDENTICAL
   - ru: old=`488112c6749ebd27` new=`064d2ab81a224261` → CHANGED (의도된 유일 변경)
   - 상수: `EN_TARGET_RULES`/`AR_TARGET_RULES` unchanged=True, RU old="" → 채워짐(len 2482).

2. **단위테스트** — `backend`에서 `../.venv/bin/python -m unittest tests.test_translation_validators -q`: **20 tests OK** (검증기 무수정, 통과 유지).

3. **ru 스모크 (n02-field-trip-consent, --langs ru, gemini-2.5-flash)**:
   - 결과: `ru: ready_to_save | hf=passed ct=passed | 122.0s` (429 없음).
   - 룰 반영 확인(신규 출력): 대문자 `Вы`/`Вас`, `Просим Вас` 패턴, 금액 `250 000 южнокорейских вон`(천단위 공백+통화 풀어쓰기), 전화 `032-815-4038` 보존, 날짜 `1 июня (понедельник)` 월 소문자, AM/PM 없음, 한국식 중점 없음, 학교명 «...».
   - 회귀 없음: baseline·신규 모두 의례적 오프너를 만들지 않고 원문 `안녕하십니까`를 `Здравствуйте.`로 동일 처리(사실 추가 금지 준수). 길이 base 3248 / new 3247 자로 사실상 동등.
   - baseline 백업: `pipeline-output-baseline/n02-field-trip-consent/ru.json`.

## 변경 파일

- `backend/app/translation/prompts.py` (RU_TARGET_RULES 채움)
- `.agents/translation-quality/iterations/2026-06-02_iter-003/engineering/phase2-ru-rules.md` (본 문서)
- `.agents/translation-quality/iterations/2026-06-02_iter-003/pipeline-output-baseline/n02-field-trip-consent/ru.json` (스모크 전 baseline 백업)
- `.agents/translation-quality/iterations/2026-06-02_iter-003/notices/training/n02-field-trip-consent/pipeline-output/ru.json` (스모크 재생성 — 새 ru 룰 적용 출력)
