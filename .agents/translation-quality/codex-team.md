# Codex Translation Prompt Team

이 문서는 Codex가 `.agents/translation-quality/` 자산을 이용해 **병렬 역할 분담형 프롬프트 엔지니어링 팀**으로 움직일 때의 운영 가이드다.

## 목적

Claude 쪽에서 만든 번역 품질 개선 루프를 Codex에서도 독립적으로 재현한다.

- 목표 1: 현재 프롬프트/검증기가 언어 기준(en/ru/ar)과 실제로 정렬되어 있는지 감시
- 목표 2: 목업 데이터로 반복 가능한 baseline/after 비교 세트를 빠르게 생성
- 목표 3: 한 번의 사람 입력으로도 Codex가 분석, 개선, 검증 역할을 분담해서 다음 액션을 남기게 함

## 권장 팀 구성

1. **Lead Codex**
   - 전체 이터레이션 오너
   - 어떤 notice set을 쓸지 결정
   - sub-agent 결과를 통합
   - 실제 코드 수정과 최종 판정 담당

2. **Prompt Auditor**
   - `backend/app/translation/prompts.py`
   - `.agents/translation-quality/language-criteria/{en,ru,ar}.md`
   - `docs/translation-quality.md`
   - 역할: 문서가 요구하는 규칙이 프롬프트에 실제로 들어가 있는지 감시

3. **Mock Scenario Curator**
   - `.agents/translation-quality/mock-notices/seed-set-v1.json`
   - `manifest.json`
   - 역할: 언어별로 잘 깨지는 상황을 training / held-out으로 균형 배치

4. **Regression Verifier**
   - `evaluation/scores.json`
   - `_history.json`
   - `pipeline-output/*.json`
   - 역할: 개선이 과적합인지, 상태 변화가 품질 저하인지 게이트 artifact인지 분리

## Codex 운영 순서

### 1. 이터레이션 생성

```bash
python scripts/scaffold_translation_quality_iteration.py \
  --iter-dir .agents/translation-quality/iterations/2026-06-02_iter-codex-001
```

기본값으로 `mock-notices/seed-set-v1.json`을 사용한다.

### 2. 구조 검증

```bash
python scripts/validate_translation_iteration.py \
  --iter-dir .agents/translation-quality/iterations/2026-06-02_iter-codex-001
```

이 단계는 manifest, source 파일, role split, 언어 설정, 필수 폴더를 검사한다.

### 3. baseline 파이프라인 실행

```bash
python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/2026-06-02_iter-codex-001
```

### 4. 병렬 Codex 역할 분담

Lead Codex는 sub-agent를 병렬로 호출한다.

- Auditor 프롬프트 예시:
  `prompts.py`와 `language-criteria/*.md`의 정합성만 감사하고, 코드 수정 없이 누락 규칙을 severity와 함께 보고하라.
- Curator 프롬프트 예시:
  seed notice set이 en/ru/ar 각각의 실패 모드를 충분히 덮는지 평가하고, 부족한 notice 유형을 제안하라.
- Verifier 프롬프트 예시:
  `scores.json`, `_pipeline_run_summary.json`, `_history.json`을 보고 품질 회귀와 게이트 artifact를 분리하라.

### 5. Lead가 코드 수정

수정 범위:

- `backend/app/translation/prompts.py`
- `backend/app/translation/validators.py`
- 필요 시 `backend/app/translation/orchestrator.py`

### 6. 재실행과 after 검증

```bash
python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/2026-06-02_iter-codex-001
```

필요하면 `pipeline-output-after/`로 결과를 따로 저장하도록 후속 스크립트를 추가하거나 수동 복사 정책을 둔다.

## seed-set-v1 설계 의도

`mock-notices/seed-set-v1.json`은 다음 실패 모드를 의도적으로 섞는다.

- `n01`: 영어 action phrasing, anti-literal safety checklist
- `n02`: fee/deadline/action preservation
- `n03`: 아랍어 halal / allergen / gelatin / alcohol-sensitive wording
- `n04`: 한국 학교 개념(학예회, 알림장) 의미 번역
- `n05`: line-structure preservation, email vs inquiry separation
- `n06`: table preservation, grade targets, Russian date/time formatting

## Codex 판정 원칙

- 문서에만 있고 프롬프트에 없는 규칙은 “설계 누락”으로 본다.
- pipeline status만으로 번역 품질을 단정하지 않는다.
- held-out 점수는 일반화 판단용이고, held-out 디테일은 여전히 누설 금지 원칙을 따른다.
- 고위험 식단/종교 항목은 번역문 자연스러움보다 안전성과 dictionary discipline을 우선한다.
