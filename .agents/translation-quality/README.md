# Translation Quality Agent Team

## North Star

본 팀의 모든 평가·개선은 단 하나의 기준으로 수렴한다:

> **번역 언어를 모국어로 사용하는 해외 이주민 학부모가 통신문을 정확하게 이해할 수 있어야 한다.**

자연스러움·톤·격식·문화 적절성 등 다른 모든 축은 이 기준에 종속된다. 어떤 축의 점수가 높아도 페르소나가 "무엇을/언제까지/어떻게 해야 하는지 모름"이면 종합 verdict는 fail.

페르소나 정의:
- 타겟 언어를 모국어로 함
- 한국 거주 이주민 학부모
- 한국 학교 문화 친숙도 낮음 (학예회·알림장·체험학습·돌봄교실 등 사전 지식 없음)
- 일반적 성인 가독 수준 (문학·법무·종교 고급 어휘 익숙하지 않음)
- 언어별 디테일: `language-criteria/<lang>.md`의 "Migrant Parent Profile"

---

학교 가정통신문 번역(현재 `backend/app/translation/`)의 품질을 위 north star로 반복 개선하는 2-에이전트 팀.

## 멤버

- **Translation Evaluator Agent** — [`evaluator-agent.md`](evaluator-agent.md)
  - 입력: 한국어 원문, 타겟 언어 번역(en/ru/ar), back-translation, 파이프라인 검증 결과
  - 출력: `feedback-report.md` (정량 점수 + 정성 이슈 + 우선순위 권고)
  - 코드/프롬프트를 직접 수정하지 **않는다**.

- **Translation Engineer Agent** — [`engineer-agent.md`](engineer-agent.md)
  - 입력: `feedback-report.md`
  - 출력: 코드/프롬프트 변경 + `improvement-plan.md` (적용된 피드백, 보류된 피드백, 검증 방법)
  - 평가자의 기준을 임의로 바꾸지 **않는다**.

## 흐름 요약

```
가정통신문(원본)
   │
   ▼  (1) 한국어 원문 추출
한국어 source.ko.md
   │
   ▼  (2) 번역 파이프라인 (orchestrator.run 3회 — en, ru, ar)
타겟 번역 + back_translation + 검증 결과
   │
   ▼  (3) Evaluator Agent
feedback-report.md
   │
   ▼  (4) Engineer Agent
코드 변경 + improvement-plan.md
   │
   ▼  (5) 같은 입력으로 재실행 → 점수 비교 → 다음 이터레이션
```

전체 단계와 산출물 규약은 [`workflow.md`](workflow.md) 참조.

## 폴더 구조

```
.agents/translation-quality/
├── README.md                          # 본 문서
├── evaluator-agent.md                 # 평가자 명세
├── engineer-agent.md                  # 엔지니어 명세
├── workflow.md                        # 단계별 절차와 사용법
├── templates/
│   ├── feedback-report.md             # 평가자 산출물 템플릿
│   ├── improvement-plan.md            # 엔지니어 산출물 템플릿
│   └── evaluation-rubric.md           # 평가 축·점수 기준
├── language-criteria/
│   ├── en.md                          # 영어 평가/번역 가이드
│   ├── ru.md                          # 러시아어 평가/번역 가이드
│   └── ar.md                          # 아랍어 평가/번역 가이드
└── iterations/
    └── <YYYY-MM-DD>_iter-<NNN>/       # 이터레이션별 산출물
        ├── manifest.json              # 통신문 목록 + role(training|held_out) + diversity tags
        ├── notices/
        │   ├── training/              # 엔지니어가 디테일 볼 수 있는 set
        │   └── held-out/              # 일반화 측정용. 엔지니어 접근 금지.
        ├── evaluation/
        │   ├── feedback-report.md
        │   ├── scores.json
        │   └── held-out-detail/       # 엔지니어 접근 금지.
        ├── engineering/
        └── pipeline-output-after/
```

## 데이터 분할 정책

- 매 이터에 N개 통신문을 다룬다. 다양성 매트릭스(통신문 종류/길이/hard fact 밀도/톤/대상/시간표현/문화민감도)에서 가능한 한 다르게.
- **Training set**: 엔지니어가 구체 이슈를 보고 직접 개선
- **Held-out set**: 엔지니어가 점수와 추세만 본다. 원문/번역/이슈 디테일 접근 금지. 일반화 측정용.
- 과적합 신호 시 직전 Change Set의 rollback candidate를 표시.

## 대상 언어

en, ru, ar — 세 언어를 우선 다룬다. 엔지니어 에이전트는 언어별 프롬프트 분리(예: `prompts_en.py`, `prompts_ru.py`, `prompts_ar.py`)도 권한 범위에 포함된다.

## 엔지니어의 개선 권한 범위

- `backend/app/translation/prompts.py` 전체
- `backend/app/translation/orchestrator.py` (단계 추가/순서/temperature/자동수정 횟수)
- `backend/app/translation/validators.py` (검증 규칙)
- 새 모듈/패키지 추가 (예: 언어별 스타일 가이드 데이터, 새 사전, 신규 검증기)

평가 기준(`evaluation-rubric.md`, `language-criteria/*`)은 엔지니어가 임의로 변경하지 않는다. 변경이 필요하다면 `improvement-plan.md`에서 제안하고 사용자 승인을 받는다.
