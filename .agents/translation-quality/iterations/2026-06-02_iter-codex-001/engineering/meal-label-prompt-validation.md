# Meal Label Prompt Validation

**Iteration:** `2026-06-02_iter-codex-001`  
**Scope:** `translate_meal_labels_prompt`, meal-label structured translation path  
**Mode:** `codex-team` prompt audit + regression verification  
**Date:** `2026-06-03`

## Verdict

`ready_for_re_evaluation`

정적 감사 기준에서는 meal-label 전용 프롬프트가 notice 본문 번역 규칙과 분리되어 있고, 메뉴명/알레르기명/기호 보존 계약이 명시돼 있다. 추가로 structured-output unit tests를 붙여 parser/response contract를 고정했다.

## Engineer-Agent Audit

검토 대상:

- `backend/app/translation/prompts.py`
- `backend/app/services/notice_service.py`
- `lib/neis.ts`

핵심 판단:

1. 기존 notice 공통 프롬프트는 `meal, allergy, ingredient`에 대해 지나치게 보수적이라 메뉴명을 원문 유지할 가능성이 높았다.
2. `translate_meal_labels_prompt` 분리는 타당하다. 급식은 긴 공지문 번역이 아니라 **짧은 UI label translation**이므로 structured mapping이 맞다.
3. 프롬프트에 다음 계약이 포함돼 있어야 한다:
   - 메뉴명은 실제 음식명처럼 자연스럽게 번역
   - 알레르기명은 parent-facing standard label로 번역
   - `*`, `(9)` 같은 marker는 정확히 보존
   - item별 `id -> translation` JSON 반환
   - 항목 병합/설명 추가 금지

현재 상태:

- 위 5개 계약이 모두 prompt에 반영됨
- `NoticeService.translate_text(..., translation_kind="meal_labels")` 경로로 별도 처리됨
- `lib/neis.ts`는 `translations` map을 우선 사용하고, legacy line parser는 fallback으로만 남아 있음

## Evaluator-Agent Verification

Mock cases used:

- `기장밥` -> plain grain-rice dish name
- `*오쭈낙볶음` -> leading symbol preservation + seafood mixed dish
- `깍두기 (9)` -> trailing allergy marker preservation
- `한방닭곰탕` -> long compound soup label

Verification outcomes:

1. Prompt contract test:
   - meal-label specific wording exists
   - symbol-preservation rule exists
   - JSON schema with `id`, `translation` exists

2. Source parsing test:
   - `[[M001]] ...` rows are extracted correctly from synthetic source text

3. Service structured response test:
   - mocked Gemini JSON is returned as `translations`
   - `final_translation` is rebuilt deterministically from the map
   - missing items fall back to original Korean label instead of dropping keys

## Live Vertex Audit

샘플 세트:

- `기장밥`
- `*오쭈낙볶음`
- `깍두기 (9)`
- `호밀사과파이`
- `*한방닭곰탕`
- `Soybean`, `Wheat`, `Sulfites`, `Chicken`

Round 1 findings:

- en: `Jjukkumi` 잔존
- ru: `джуккуми`, `Ккактуги` 음역 잔존
- ar: 전체적으로 양호하지만 compound dish 단순화 경향

Prompt hardening applied:

- Hangul/romanization/transliteration 잔존 금지
- common Korean dish types는 plain target-language food label로 번역
- multi-component dish는 named component를 축약하지 말 것

Round 2 findings after hardening:

- en:
  - `Millet Rice`
  - `*Squid, Webfoot Octopus, and Long-arm Octopus Stir-fry`
  - `Diced Radish Kimchi (9)`
- ru:
  - `Кимчи из редьки (9)`로 개선
  - `*Жареные кальмары и осьминоги`로 transliteration 제거
  - 다만 `Пшенной рис`는 어색해 추가 자연화 여지 있음
- ar:
  - `*مقلي الحبار والأخطبوط`
  - `كيمتشي الفجل المكعب (9)`
  - transliteration/romanization 잔존 없음

## Residual Risk

- 러시아어 `기장밥`가 `Пшенной рис`처럼 어색하게 나올 수 있어, grain+rice 계열 dish naming은 러시아어 전용 rule 보강 여지가 있다.
- `오쭈낙볶음`의 3중 seafood shorthand는 영어에서는 잘 풀렸지만 ru/ar는 일부 component merge 경향이 남는다.
- `translation_complete` 수준의 UI fix로는 충분하지만, meal domain fully-polished 수준까지 가려면 실제 학교 menu sample 세트를 더 모아야 한다.

## Recommended Next Check

다음 우선순위:

- 러시아어 grain/rice naming 전용 보강 여부 판단
- 실제 급식 주간 데이터 1주치를 샘플로 묶어 held-out style 평가 수행
