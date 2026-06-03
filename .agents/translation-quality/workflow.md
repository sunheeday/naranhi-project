# Translation Quality Workflow

본 문서는 한 번의 이터레이션이 어떻게 흘러가는지, 각 산출물이 어디에 저장되는지, 어떻게 실행하는지를 정의한다.

## 한 이터레이션의 흐름

```
[0] 사용자: 가정통신문 제공 (텍스트/이미지/PDF)
       │
[1] 한국어 원문 추출
       │      → input/source.ko.md, input/source-meta.json
       │
[2] 번역 파이프라인 실행 (en, ru, ar 각각 1회)
       │      → pipeline-output/en.json, ru.json, ar.json
       │
[3] Evaluator Agent
       │      → evaluation/feedback-report.md
       │      → evaluation/scores.json
       │
[4] Engineer Agent
       │      → 코드 변경 (backend/app/translation/**)
       │      → engineering/improvement-plan.md
       │      → engineering/changes-summary.md
       │
[5] 같은 입력으로 파이프라인 재실행 (회귀 확인)
       │      → pipeline-output-after/en.json, ru.json, ar.json
       │
[6] 사용자: 다음 이터레이션으로 갈지 판단
```

## 이터레이션 폴더 규약 (multi-notice + held-out split)

매 이터에 N개의 통신문을 함께 다루며, 그 중 일부는 **held-out**(엔지니어가 디테일을 보지 못하는 일반화 측정용)으로 격리한다. 기본 분할: training 5 / held-out 3 (총 8).

```
.agents/translation-quality/iterations/<YYYY-MM-DD>_iter-<NNN>/
├── manifest.json                       # 모든 통신문의 메타 + role(training|held_out) + diversity tags
├── notices/
│   ├── training/
│   │   ├── n01-<kind>/                 # 예: n01-meal-menu
│   │   │   ├── source.ko.md
│   │   │   ├── source-meta.json
│   │   │   └── pipeline-output/
│   │   │       ├── en.json
│   │   │       ├── ru.json
│   │   │       └── ar.json
│   │   ├── n02-<kind>/
│   │   └── ...
│   └── held-out/
│       ├── n06-<kind>/                 # 엔지니어 접근 금지
│       ├── n07-<kind>/
│       └── n08-<kind>/
├── evaluation/
│   ├── feedback-report.md              # 엔지니어 가독 — training의 구체 이슈 + held-out 집계
│   ├── scores.json                     # 모든 통신문 × 언어 × 축 점수 (held-out도 점수만은 공개)
│   └── held-out-detail/                # 엔지니어 접근 금지. 평가자 본인 자료용.
│       ├── n06-<kind>.md
│       ├── n07-<kind>.md
│       └── n08-<kind>.md
├── engineering/
│   ├── improvement-plan.md
│   └── changes-summary.md
└── pipeline-output-after/              # 엔지니어 변경 적용 후 재실행 결과
    ├── training/
    │   ├── n01-<kind>/{en,ru,ar}.json
    │   └── ...
    └── held-out/
        ├── n06-<kind>/{en,ru,ar}.json
        └── ...
```

### manifest.json 형식

```json
{
  "iteration": 1,
  "date": "2026-06-01",
  "notices": [
    {
      "id": "n01-meal-menu",
      "role": "training",
      "kind": "meal-menu",
      "length": "medium",
      "fact_density": "meal-heavy",
      "tone": "routine",
      "audience": "school-wide",
      "time_reference": "weekly-range",
      "cultural_sensitivity": "critical-allergen",
      "source_path": "notices/training/n01-meal-menu/source.ko.md"
    },
    {
      "id": "n08-safety-urgent",
      "role": "held_out",
      "kind": "safety-notice",
      "length": "short",
      "fact_density": "action-heavy",
      "tone": "urgent",
      "audience": "school-wide",
      "time_reference": "immediate",
      "cultural_sensitivity": "neutral",
      "source_path": "notices/held-out/n08-safety-urgent/source.ko.md"
    }
  ]
}
```

### Held-out 정책 (엄격)

- **평가자**: training과 held-out 둘 다 채점한다. 단,
  - training 통신문 → `feedback-report.md`에 구체 스니펫·진단·권고 포함
  - held-out 통신문 → `feedback-report.md`에는 **집계 점수와 추이만**. 원문/번역/back-translation 스니펫을 엔지니어 가독 영역에 절대 적지 않는다. 상세는 `held-out-detail/`에 따로 저장 (평가자 본인용).
- **엔지니어**: `notices/held-out/`와 `evaluation/held-out-detail/`를 **읽지 않는다**. `scores.json`의 held-out 점수만 확인한다.
- **과적합 신호**: training 평균은 오르는데 held-out 평균이 정체 또는 하락 → 엔지니어는 직전 Change Set 중 가장 영향이 큰 것을 후보로 표시하고 `improvement-plan.md`에 "rollback candidate"로 적는다. 한 이터에서 즉시 롤백할지, 다음 이터에서 결정할지는 team-lead와 협의.

이터레이션 번호(`NNN`)는 0-padded 3자리. 같은 입력으로 2회차를 돌릴 때는 폴더만 새로 만들고 `input/`은 이전 폴더에서 복사한다.

## 파이프라인 실행 방법

엔지니어 에이전트는 다음 둘 중 하나로 파이프라인을 돌린다.

### Path A. 백엔드 가동 후 driver 스크립트 (자동)

권장. 통신문 한 개당 다음 한 줄로 3개 언어 결과를 만든다.

```bash
# 사전 조건: backend/.env 또는 환경변수에 Gemini/Vertex 설정
python scripts/translation_quality_driver.py \
  --source .agents/translation-quality/iterations/<DATE>_iter-<NNN>/notices/<role>/<notice-id>/source.ko.md \
  --langs en,ru,ar \
  --out    .agents/translation-quality/iterations/<DATE>_iter-<NNN>/notices/<role>/<notice-id>/pipeline-output/
```

manifest 전체를 한 번에 처리하려면 wrapper를 사용한다 (예정).

```bash
python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/<DATE>_iter-<NNN>/
```

driver는 통신문 단위 실행을 담당하고, wrapper는 manifest를 읽어 모든 통신문을 반복 호출한다. 첫 이터 시작 전 엔지니어가 만든다.

### Path B. 수동 (백엔드 미가동)

사용자가 한국어 원문과 3개 언어 번역 결과를 직접 붙여 넣어 주는 경우. 평가자 에이전트가 `pipeline-output/<lang>.json` 형태로 직접 정리해 저장한다 (`raw_steps`가 비어 있으면 그 부분은 평가에서 제외).

## 한국어 원문 추출 (Step 1)

가정통신문 입력 형태별 처리:

| 입력 | 처리 |
|---|---|
| 평문 텍스트 | `input/source.ko.md`에 그대로 저장 |
| 카카오톡/캡처 이미지 | 이미지 → OCR → 사람이 한 번 손보고 `source.ko.md` 저장. 원본은 `input/original/`에 보관 |
| PDF | 텍스트 PDF면 추출, 스캔 PDF면 OCR. 마찬가지로 사람이 한 번 검수 |
| 백엔드의 `content_extraction_service` 결과 | 그대로 `source.ko.md`에 저장 |

`source-meta.json` 최소 필드:
```json
{
  "origin": "원본 파일명 또는 출처",
  "kind": "weekly-notice | meal-menu | event-notice | safety-notice | etc.",
  "extracted_by": "manual | content_extraction_service | ocr",
  "notes": "특이사항"
}
```

## 두 에이전트 호출 방법

### Evaluator 호출 예시 (Agent 도구로 호출)

```
description: "Iter-NNN 번역 결과 평가"
subagent_type: "general-purpose"
prompt: |
  너는 .agents/translation-quality/evaluator-agent.md에 정의된 Translation Evaluator Agent다.
  대상 이터레이션 폴더: .agents/translation-quality/iterations/<YYYY-MM-DD>_iter-<NNN>/

  - evaluator-agent.md, templates/evaluation-rubric.md, language-criteria/{en,ru,ar}.md를 모두 읽고 시작한다.
  - input/, pipeline-output/을 읽고 8축 평가를 수행한다.
  - 직전 이터레이션이 있다면 회귀 항목을 표시한다.
  - 산출: evaluation/feedback-report.md, evaluation/scores.json
  - 코드/프롬프트는 절대 수정하지 않는다.
```

### Engineer 호출 예시

```
description: "Iter-NNN 피드백 기반 파이프라인 개선"
subagent_type: "general-purpose"
prompt: |
  너는 .agents/translation-quality/engineer-agent.md에 정의된 Translation Engineer Agent다.
  대상 이터레이션 폴더: .agents/translation-quality/iterations/<YYYY-MM-DD>_iter-<NNN>/

  - engineer-agent.md를 읽고 시작한다.
  - evaluation/feedback-report.md, evaluation/scores.json, pipeline-output/*.json, input/source.ko.md를 모두 읽는다.
  - 우선순위 Top 3–5건만 다룬다. 한 이터레이션에서 5개 넘는 Change Set 금지.
  - 산출: engineering/improvement-plan.md, engineering/changes-summary.md, 그리고 backend/app/translation/** 코드 변경
  - 변경 적용 후 파이프라인 재실행 결과를 pipeline-output-after/에 저장한다.
  - 평가 기준은 임의로 바꾸지 않는다.
```

## 이터레이션 간 점수 추적

평가자가 `scores.json`을 매 이터레이션에서 생성하므로, 시계열 비교용 집계는 다음 형식으로 누적한다.

```
.agents/translation-quality/iterations/_history.json
[
  { "iter": 1, "date": "2026-06-01", "scores": { "en": {...}, "ru": {...}, "ar": {...} }, "critical_count": 3 },
  { "iter": 2, "date": "2026-06-03", "scores": {...}, "critical_count": 1 }
]
```

매 이터레이션이 끝날 때 평가자가 직접 append. 점수가 하락한 축이 있으면 다음 평가자가 회귀로 잡아낸다.

## 이터레이션 종료 판정 (전체 루프 종료)

매 이터 끝에 평가자가 `verdict`를 4가지 중 하나로 표기. team-lead는 verdict를 보고 다음을 결정.

| Verdict | team-lead 행동 |
|---|---|
| `ship_ready` | **자동 종료.** 사용자에게 결과 보고 후 더 이상 이터 진행 안 함. |
| `diminishing_returns` | **자동 종료 후보.** 사용자에게 옵션 제시 (그대로 종료 / 새 통신문 추가 / 특정 언어만 계속). |
| `blocking_regression` | **강제 정지.** 사용자에게 회귀 보고 + rollback / 룰 일반화 / 평가 기준 변경 결정 요청. |
| `needs_iteration` | 다음 이터레이션 자동 진행. |

구체 임계치는 `templates/evaluation-rubric.md`의 "Stopping Criteria" 섹션 참조. 핵심:
- ship_ready 조건: 세 언어 모두 train_avg ≥ 4.2 & held_out_avg ≥ 4.0, critical 0, safety ≥ 4, Comprehension Pass 전체 통과
- 끝없이 돌리지 않는다. 사용자가 명시적으로 더 진행하라고 하지 않는 한, 위 3 verdict에서 즉시 멈춘다.

## 한 이터레이션의 완료 정의 (DoD)

- [ ] `manifest.json` 작성, 모든 통신문에 role/diversity tag 명시
- [ ] 모든 통신문에 `source.ko.md` + `source-meta.json` 저장
- [ ] 모든 통신문 × 3개 언어 `pipeline-output/<lang>.json` 존재
- [ ] `feedback-report.md` + `scores.json` 저장 (held-out 정책 준수: 디테일은 `held-out-detail/`에만)
- [ ] `improvement-plan.md` + `changes-summary.md` 저장
- [ ] 코드 변경 적용 후 동일 입력으로 재실행한 `pipeline-output-after/` 존재
- [ ] `iterations/_history.json` 업데이트 — `train_avg`, `held_out_avg`, `generalization_gap` 포함
