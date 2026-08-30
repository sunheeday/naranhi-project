from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.translation.json_client import JsonModelClient
from app.translation.prompts import (
    back_translate_to_ko_prompt,
    build_supabase_payload_prompt,
    extract_source_hard_facts_prompt,
    extract_target_hard_facts_prompt,
    fix_context_tone_prompt,
    fix_hard_facts_prompt,
    map_ingredient_identity_prompt,
    translate_en_to_target_prompt,
    translate_ko_to_en_pivot_prompt,
    validate_context_tone_prompt,
    validate_hard_facts_prompt,
)
from app.translation.validators import validate_hard_facts_by_code, validate_output_by_code

LOGGER = logging.getLogger(__name__)

# 기계적 추출·역번역 콜은 thinking(추론)이 불필요해 0으로 끈다 — 콜당 수십 초와
# 추론 토큰 비용을 줄인다. 번역(피벗·타겟)·검증·카드 콜은 기본(동적 thinking)을 유지.
MECHANICAL_THINKING_BUDGET = 0


async def _discard_task(task: asyncio.Task[Any] | None) -> None:
    """미리 띄워둔 작업을 조용히 버린다 — 이미 무효해진 작업의 결과·예외는 모두 무시."""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001 - 버리는 작업의 실패(429 등)가 본 흐름을 깨면 안 된다.
        pass


@dataclass(frozen=True)
class TranslationPipelineInput:
    source_text: str
    target_language: str
    approved_ingredient_dictionary: list[dict[str, Any]]
    approved_ingredient_dictionary_target: list[dict[str, Any]]
    max_auto_fix_attempts_per_stage: int = 1
    max_target_hard_fact_extraction_attempts: int = 2


class TranslationPipeline:
    def __init__(self, gemini: JsonModelClient) -> None:
        self.gemini = gemini
        # 비기계 단계에 넘길 thinking 예산. None 이면 모델 기본값을 그대로 쓴다.
        self.thinking_budget = get_settings().translation_thinking_budget
        # 문맥·어조 검증 단계만 thinking을 되돌리는 부분 적용 스위치(계획서 §6.2, arm-b2).
        # thinking 전면 off(arm-b) 실측에서 hard_fact 보존이 무너졌다(학년 오기재·없는
        # 날짜 생성·이메일을 전화번호로 지어냄) — 검증 단계만 모델 기본(동적) thinking을
        # 쓰고 나머지 비기계 단계는 self.thinking_budget 그대로 둔다.
        self.context_tone_thinking_budget = (
            None
            if get_settings().translation_context_tone_thinking_override
            else self.thinking_budget
        )

    async def run(self, payload: TranslationPipelineInput) -> dict[str, Any]:
        # ①(원문 하드팩트)과 ②(식재료 매핑)은 둘 다 source_text 만 읽는다.
        # ②가 ①의 meal_and_allergy 를 보긴 하지만 «식사 정보가 있나» 게이트일 뿐이라,
        # 둘을 동시에 띄우고 게이트는 결과가 다 온 뒤에 적용한다. 프롬프트는 그대로다.
        source_hard_facts_task = asyncio.create_task(
            self.gemini.generate_json(
                prompt=extract_source_hard_facts_prompt(payload.source_text),
                temperature=0.0,
                model=getattr(self.gemini, "source_hard_fact_model", None),
                thinking_budget=MECHANICAL_THINKING_BUDGET,
            )
        )
        ingredient_map_task = asyncio.create_task(
            self._map_ingredients_unconditional(payload=payload)
        )
        try:
            source_hard_facts = await source_hard_facts_task
        except BaseException:
            await _discard_task(ingredient_map_task)
            raise

        risk_profile = _risk_profile_from_source(
            source_text=payload.source_text,
            source_hard_facts=source_hard_facts,
        )

        if _has_meal_info(source_hard_facts):
            ingredient_map = await ingredient_map_task
        else:
            # 식사 정보가 없으면 매핑 결과를 쓰지 않는다 — 기존 게이트와 같은 판정이다.
            await _discard_task(ingredient_map_task)
            ingredient_map = _empty_ingredient_map()

        pivot = await self.gemini.generate_json(
            prompt=translate_ko_to_en_pivot_prompt(
                source_text=payload.source_text,
                source_hard_facts=source_hard_facts,
                ingredient_map=ingredient_map,
            ),
            temperature=0.1,
            thinking_budget=self.thinking_budget,
        )
        pivot_translation_en = str(pivot.get("pivot_translation_en") or "")

        target = await self.gemini.generate_json(
            prompt=translate_en_to_target_prompt(
                target_language=payload.target_language,
                pivot_translation_en=pivot_translation_en,
                source_hard_facts=source_hard_facts,
                ingredient_map=ingredient_map,
                target_dictionary=payload.approved_ingredient_dictionary_target,
            ),
            temperature=0.1,
            thinking_budget=self.thinking_budget,
        )
        target_translation = str(target.get("target_translation") or "")

        # 역번역(⑤)은 번역본만 입력으로 쓰므로, 번역본 하드팩트 추출(④)·검증과
        # 병렬로 미리 띄운다. 검증이 번역문을 고치면 결과를 버리고 새로 돈다.
        back_translation_task: asyncio.Task[dict[str, Any]] | None = None
        translation_when_back_started = target_translation
        if risk_profile["level"] != "low":
            back_translation_task = asyncio.create_task(
                self.gemini.generate_json(
                    prompt=back_translate_to_ko_prompt(
                        target_language=payload.target_language,
                        target_translation=target_translation,
                    ),
                    temperature=0.0,
                    thinking_budget=MECHANICAL_THINKING_BUDGET,
                )
            )

        try:
            target_hard_facts = await self._extract_target_hard_facts_with_retry(
                payload=payload,
                source_hard_facts=source_hard_facts,
                target_translation=target_translation,
            )

            hard_fact_validation = validate_hard_facts_by_code(
                source_hard_facts,
                target_hard_facts,
                ingredient_map,
            )
            hard_fact_attempts = 0

            # 코드 검사가 먼저다(AI 호출 0회). 한글 잔존·잘림 같은 것은 정규식이
            # 0원·0초로 100% 잡는다 — 여기서 걸리면 LLM 검증을 부르지 않고 바로 고친다.
            output_check = validate_output_by_code(
                source_text=payload.source_text,
                translated_text=target_translation,
                target_language=payload.target_language,
            )
            if output_check["status"] == "failed":
                hard_fact_validation = _merge_validation(
                    hard_fact_validation,
                    {
                        "verdict": "FAIL",
                        "mismatches": [
                            {"field": i["code"], "issue": i["detail"]}
                            for i in output_check["issues"]
                        ],
                    },
                )

            if hard_fact_validation["verdict"] == "FAIL":
                llm_validation = await self.gemini.generate_json(
                    prompt=validate_hard_facts_prompt(
                        source_hard_facts=source_hard_facts,
                        translated_hard_facts=target_hard_facts,
                    ),
                    temperature=0.0,
                    thinking_budget=self.thinking_budget,
                )
                hard_fact_validation = _merge_validation(hard_fact_validation, llm_validation)

            while (
                hard_fact_validation["verdict"] == "FAIL"
                and hard_fact_attempts < payload.max_auto_fix_attempts_per_stage
            ):
                hard_fact_attempts += 1
                fixed = await self.gemini.generate_json(
                    prompt=fix_hard_facts_prompt(
                        source_text=payload.source_text,
                        source_hard_facts=source_hard_facts,
                        current_target_translation=target_translation,
                        mismatches=list(hard_fact_validation.get("mismatches") or []),
                        target_language=payload.target_language,
                        ingredient_map=ingredient_map,
                        target_dictionary=payload.approved_ingredient_dictionary_target,
                    ),
                    temperature=0.0,
                    thinking_budget=self.thinking_budget,
                )
                target_translation = str(
                    fixed.get("corrected_target_translation") or target_translation
                )
                target_hard_facts = await self._extract_target_hard_facts_with_retry(
                    payload=payload,
                    source_hard_facts=source_hard_facts,
                    target_translation=target_translation,
                )
                hard_fact_validation = validate_hard_facts_by_code(
                    source_hard_facts,
                    target_hard_facts,
                    ingredient_map,
                )
                output_check = validate_output_by_code(
                    source_text=payload.source_text,
                    translated_text=target_translation,
                    target_language=payload.target_language,
                )
                if output_check["status"] == "failed":
                    hard_fact_validation = _merge_validation(
                        hard_fact_validation,
                        {
                            "verdict": "FAIL",
                            "mismatches": [
                                {"field": i["code"], "issue": i["detail"]}
                                for i in output_check["issues"]
                            ],
                        },
                    )
        except BaseException:
            await _discard_task(back_translation_task)
            raise

        if hard_fact_validation["verdict"] == "FAIL":
            await _discard_task(back_translation_task)
            return await self._validation_failed_result(
                payload=payload,
                source_hard_facts=source_hard_facts,
                target_hard_facts=target_hard_facts,
                ingredient_map=ingredient_map,
                target_translation=target_translation,
                hard_fact_validation=hard_fact_validation,
                hard_fact_attempts=hard_fact_attempts,
                context_tone_validation={"status": "skipped", "issues": []},
                reason="hard_fact_validation_failed",
            )

        if risk_profile["level"] == "low":
            validation_results = {
                "hard_fact": {
                    "status": "passed",
                    "attempts": hard_fact_attempts,
                    "issues": [],
                },
                "context_tone": {
                    "status": "skipped",
                    "attempts": 0,
                    "issues": list(risk_profile.get("reasons") or []),
                },
            }
            metadata = await self.gemini.generate_json(
                prompt=build_supabase_payload_prompt(
                    source_text=payload.source_text,
                    final_target_translation=target_translation,
                    source_hard_facts=source_hard_facts,
                    validation_results=validation_results,
                    target_language=payload.target_language,
                ),
                temperature=0.0,
                thinking_budget=self.thinking_budget,
            )

            return {
                "status": "ready_to_save",
                "source_language": "ko",
                "target_language": payload.target_language,
                "source_text": payload.source_text,
                "final_translation": target_translation,
                "source_hard_facts": source_hard_facts,
                "target_hard_facts": target_hard_facts,
                "ingredient_identity_map": ingredient_map,
                "validation": validation_results,
                "admin_review": {
                    "required": False,
                    "reason": None,
                    "priority": "normal",
                },
                "metadata": metadata,
                "raw_steps": {
                    "pivot": pivot,
                    "target": target,
                    "risk_profile": risk_profile,
                },
            }

        if (
            back_translation_task is not None
            and target_translation == translation_when_back_started
        ):
            back_translation = await back_translation_task
        else:
            # 수정 루프가 번역문을 바꿨으면 미리 띄운 역번역은 무효 — 버리고 새로 돈다.
            await _discard_task(back_translation_task)
            back_translation = await self.gemini.generate_json(
                prompt=back_translate_to_ko_prompt(
                    target_language=payload.target_language,
                    target_translation=target_translation,
                ),
                temperature=0.0,
                thinking_budget=MECHANICAL_THINKING_BUDGET,
            )
        back_translation_ko = str(back_translation.get("back_translation_ko") or "")

        # ⑧(카드 메타데이터)은 최종 번역문만 필요하고 검증 결과와 무관하다.
        # ⑤'(역번역)와 같은 폐기 패턴으로 검증과 병렬로 미리 띄운다.
        translation_when_metadata_started = target_translation
        metadata_task: asyncio.Task[dict[str, Any]] | None = asyncio.create_task(
            self.gemini.generate_json(
                prompt=build_supabase_payload_prompt(
                    source_text=payload.source_text,
                    final_target_translation=target_translation,
                    source_hard_facts=source_hard_facts,
                    validation_results={
                        "hard_fact": {
                            "status": "passed",
                            "attempts": hard_fact_attempts,
                            "issues": [],
                        },
                        "context_tone": {"status": "passed", "attempts": 0, "issues": []},
                    },
                    target_language=payload.target_language,
                ),
                temperature=0.0,
                thinking_budget=self.thinking_budget,
            )
        )
        # 위에서 만든 태스크가 실제로 스케줄러에 올라가도록 한 틱 양보한다.
        # 그렇지 않으면 바로 다음 줄의 검증 호출이 같은 태스크 안에서 곧장 실행돼
        # «투기적 선실행»이 아니라 매번 검증이 끝난 뒤에야 카드가 시작되는
        # 순차 실행이 되어 버린다(콜 자체는 그대로지만 시간 절약 효과가 없어진다).
        await asyncio.sleep(0)

        context_tone_validation = await self.gemini.generate_json(
            prompt=validate_context_tone_prompt(
                source_text=payload.source_text,
                target_translation=target_translation,
                back_translation_ko=back_translation_ko,
                source_hard_facts=source_hard_facts,
                target_language=payload.target_language,
            ),
            temperature=0.0,
            thinking_budget=self.context_tone_thinking_budget,
        )
        context_tone_attempts = 0

        while (
            context_tone_validation.get("verdict") == "FAIL_FIXABLE"
            and context_tone_attempts < payload.max_auto_fix_attempts_per_stage
        ):
            # 자동수정 루프가 번역문을 바꾸면 미리 띄운 카드는 무효 — 버린다.
            await _discard_task(metadata_task)
            context_tone_attempts += 1
            fixed = await self.gemini.generate_json(
                prompt=fix_context_tone_prompt(
                    source_text=payload.source_text,
                    current_target_translation=target_translation,
                    back_translation_ko=back_translation_ko,
                    issues=list(context_tone_validation.get("issues") or []),
                    target_language=payload.target_language,
                    source_hard_facts=source_hard_facts,
                ),
                temperature=0.0,
                thinking_budget=self.thinking_budget,
            )
            target_translation = str(
                fixed.get("corrected_target_translation") or target_translation
            )
            back_translation = await self.gemini.generate_json(
                prompt=back_translate_to_ko_prompt(
                    target_language=payload.target_language,
                    target_translation=target_translation,
                ),
                temperature=0.0,
                thinking_budget=MECHANICAL_THINKING_BUDGET,
            )
            back_translation_ko = str(back_translation.get("back_translation_ko") or "")
            context_tone_validation = await self.gemini.generate_json(
                prompt=validate_context_tone_prompt(
                    source_text=payload.source_text,
                    target_translation=target_translation,
                    back_translation_ko=back_translation_ko,
                    source_hard_facts=source_hard_facts,
                    target_language=payload.target_language,
                ),
                temperature=0.0,
                thinking_budget=self.context_tone_thinking_budget,
            )

        if context_tone_validation.get("verdict") != "PASS":
            await _discard_task(metadata_task)
            return await self._validation_failed_result(
                payload=payload,
                source_hard_facts=source_hard_facts,
                target_hard_facts=target_hard_facts,
                ingredient_map=ingredient_map,
                target_translation=target_translation,
                hard_fact_validation=hard_fact_validation,
                hard_fact_attempts=hard_fact_attempts,
                context_tone_validation=context_tone_validation,
                reason="context_tone_validation_failed",
            )

        validation_results = {
            "hard_fact": {
                "status": "passed",
                "attempts": hard_fact_attempts,
                "issues": [],
            },
            "context_tone": {
                "status": "passed",
                "attempts": context_tone_attempts,
                "issues": [],
            },
        }
        if metadata_task is not None and target_translation == translation_when_metadata_started:
            metadata = await metadata_task
        else:
            # 자동수정 루프가 번역문을 바꿨으면 미리 띄운 카드는 무효 — 버리고 새로 돈다.
            await _discard_task(metadata_task)
            metadata = await self.gemini.generate_json(
                prompt=build_supabase_payload_prompt(
                    source_text=payload.source_text,
                    final_target_translation=target_translation,
                    source_hard_facts=source_hard_facts,
                    validation_results=validation_results,
                    target_language=payload.target_language,
                ),
                temperature=0.0,
                thinking_budget=self.thinking_budget,
            )

        return {
            "status": "ready_to_save",
            "source_language": "ko",
            "target_language": payload.target_language,
            "source_text": payload.source_text,
            "final_translation": target_translation,
            "source_hard_facts": source_hard_facts,
            "target_hard_facts": target_hard_facts,
            "ingredient_identity_map": ingredient_map,
            "validation": validation_results,
            "admin_review": {
                "required": False,
                "reason": None,
                "priority": "normal",
            },
            "metadata": metadata,
            "raw_steps": {
                "pivot": pivot,
                "target": target,
                "back_translation": back_translation,
                "context_tone_validation": context_tone_validation,
                "risk_profile": risk_profile,
            },
        }

    async def _map_ingredients_unconditional(
        self,
        *,
        payload: TranslationPipelineInput,
    ) -> dict[str, Any]:
        """식재료 매핑을 게이트 없이 돌린다. 게이트는 호출부가 결과 폐기로 적용한다."""
        return await self.gemini.generate_json(
            prompt=map_ingredient_identity_prompt(
                meal_text=payload.source_text,
                ingredients_raw=[],
                approved_dictionary=payload.approved_ingredient_dictionary,
            ),
            temperature=0.0,
            thinking_budget=self.thinking_budget,
        )

    async def _extract_target_hard_facts_with_retry(
        self,
        *,
        payload: TranslationPipelineInput,
        source_hard_facts: dict[str, Any],
        target_translation: str,
    ) -> dict[str, Any]:
        attempts = max(1, payload.max_target_hard_fact_extraction_attempts)
        extracted: dict[str, Any] = {}

        for _ in range(attempts):
            extracted = await self.gemini.generate_json(
                prompt=extract_target_hard_facts_prompt(
                    target_language=payload.target_language,
                    target_translation=target_translation,
                ),
                temperature=0.0,
                thinking_budget=MECHANICAL_THINKING_BUDGET,
            )
            if not _target_hard_facts_need_retry(source_hard_facts, extracted):
                break

        return extracted

    async def _validation_failed_result(
        self,
        *,
        payload: TranslationPipelineInput,
        source_hard_facts: dict[str, Any],
        target_hard_facts: dict[str, Any],
        ingredient_map: dict[str, Any],
        target_translation: str,
        hard_fact_validation: dict[str, Any],
        hard_fact_attempts: int,
        context_tone_validation: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        LOGGER.warning(
            "translation validation warning: target_language=%s reason=%s hard_fact_verdict=%s context_verdict=%s hard_fact_mismatches=%s context_issues=%s",
            payload.target_language,
            reason,
            hard_fact_validation.get("verdict"),
            context_tone_validation.get("verdict"),
            json.dumps(list(hard_fact_validation.get("mismatches") or [])[:5], ensure_ascii=False, default=str),
            json.dumps(list(context_tone_validation.get("issues") or [])[:5], ensure_ascii=False, default=str),
        )

        # 검증이 실패해도 번역 본문은 저장되므로, 제목·요약·카드 메타데이터도
        # 최선으로 생성한다 (실패 시에만 최소 메타데이터로 폴백 — 이전 동작).
        metadata: dict[str, Any] = {
            "validation_status": "passed",
            "validation_failure_reason": reason,
        }
        try:
            generated = await self.gemini.generate_json(
                prompt=build_supabase_payload_prompt(
                    source_text=payload.source_text,
                    final_target_translation=target_translation,
                    source_hard_facts=source_hard_facts,
                    validation_results={
                        "hard_fact": hard_fact_validation,
                        "context_tone": context_tone_validation,
                    },
                    target_language=payload.target_language,
                ),
                temperature=0.0,
                thinking_budget=self.thinking_budget,
            )
            if isinstance(generated, dict):
                metadata = {**generated, **metadata}
        except Exception as exc:  # noqa: BLE001 - metadata is best-effort here.
            LOGGER.warning(
                "validation-failed metadata generation skipped: target_language=%s reason=%s error=%s",
                payload.target_language,
                reason,
                exc,
            )

        return {
            "status": "ready_to_save",
            "source_language": "ko",
            "target_language": payload.target_language,
            "source_text": payload.source_text,
            "final_translation": target_translation,
            "source_hard_facts": source_hard_facts,
            "target_hard_facts": target_hard_facts,
            "ingredient_identity_map": ingredient_map,
            "validation": {
                "hard_fact": {
                    "status": "passed" if hard_fact_validation["verdict"] == "PASS" else "failed",
                    "attempts": hard_fact_attempts,
                    "issues": list(hard_fact_validation.get("mismatches") or []),
                },
                "context_tone": {
                    "status": _validation_status(context_tone_validation),
                    "attempts": 0,
                    "issues": list(context_tone_validation.get("issues") or []),
                },
            },
            "admin_review": {
                "required": False,
                "reason": None,
                "priority": "normal",
            },
            "metadata": metadata,
            "raw_steps": {
                "hard_fact_validation": hard_fact_validation,
                "context_tone_validation": context_tone_validation,
            },
        }


def _merge_validation(
    code_validation: dict[str, Any],
    llm_validation: dict[str, Any],
) -> dict[str, Any]:
    mismatches = list(code_validation.get("mismatches") or [])
    mismatches.extend(llm_validation.get("mismatches") or [])
    verdict = "FAIL" if mismatches or llm_validation.get("verdict") == "FAIL" else "PASS"
    return {
        "verdict": verdict,
        "severity": llm_validation.get("severity") or code_validation.get("severity") or "high",
        "mismatches": mismatches,
        "requires_human_review": bool(llm_validation.get("requires_human_review")),
    }


def _review_priority(
    hard_fact_validation: dict[str, Any],
    context_tone_validation: dict[str, Any],
) -> str:
    severities = {
        str(hard_fact_validation.get("severity") or "").lower(),
        *{
            str(issue.get("severity") or "").lower()
            for issue in context_tone_validation.get("issues") or []
            if isinstance(issue, dict)
        },
    }
    if "critical" in severities:
        return "critical"
    if "high" in severities:
        return "high"
    return "normal"


def _validation_status(validation: dict[str, Any]) -> str:
    status = str(validation.get("status") or "").strip().lower()
    if status in {"skipped", "failed", "passed"}:
        return status
    return "passed" if validation.get("verdict") == "PASS" else "failed"


def _has_meal_info(source_hard_facts: dict[str, Any]) -> bool:
    meal = source_hard_facts.get("meal_and_allergy") or {}
    return bool(
        meal.get("has_meal_info")
        or list(meal.get("ingredients_raw") or [])
        or list(meal.get("menu_items_raw") or [])
    )


def _empty_ingredient_map() -> dict[str, Any]:
    return {
        "mapped_ingredients": [],
        "unmapped_ingredients": [],
        "critical_flags": {
            "contains_allergen": False,
            "contains_religious_restriction_item": False,
            "contains_unmapped_critical_item": False,
        },
    }


def _risk_profile_from_source(
    *,
    source_text: str,
    source_hard_facts: dict[str, Any],
) -> dict[str, Any]:
    facts = _hard_facts(source_hard_facts)
    meal = source_hard_facts.get("meal_and_allergy") or {}
    reasons: list[str] = []

    high_risk_fact_fields = (
        "deadlines",
        "fees",
        "contacts",
        "urls",
        "submissions",
        "warnings",
    )
    for field in high_risk_fact_fields:
        if _field_has_values(facts.get(field)):
            reasons.append(f"has_{field}")

    action_count = len(_values(facts.get("actions_required")))
    if action_count > 1:
        reasons.append("has_multiple_actions_required")

    if meal.get("has_meal_info") or meal.get("requires_dictionary_mapping"):
        reasons.append("has_meal_or_dictionary_sensitive_content")

    if len(_values(facts.get("dates"))) > 2 or len(_values(facts.get("times"))) > 2:
        reasons.append("has_multiple_schedule_facts")

    compact_source = source_text.strip()
    if len(compact_source) > 1600:
        reasons.append("long_notice")

    high_risk_text_cues = (
        "첨부",
        "붙임",
        "별첨",
        "양식",
        "서식",
        "qr",
        "링크",
        "계좌",
        "스쿨뱅킹",
        "납부",
        "수납",
        "동의서",
        "서명",
    )
    lowered_source = compact_source.lower()
    if any(cue in lowered_source for cue in high_risk_text_cues):
        reasons.append("has_high_risk_text_cues")

    level = "high" if reasons else "low"
    return {
        "level": level,
        "reasons": reasons or ["simple_notice_without_actions_or_deadlines"],
    }


_CRITICAL_EXTRACTION_FIELDS = (
    "dates",
    "times",
    "deadlines",
    "fees",
    "contacts",
    "urls",
    "grade_class_targets",
)


def _field_has_values(value: Any) -> bool:
    return bool(_values(value))


def _hard_facts(value: dict[str, Any]) -> dict[str, Any]:
    facts = value.get("hard_facts")
    return facts if isinstance(facts, dict) else {}


def _values(value: object) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    values: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = (
                item.get("normalized")
                or item.get("value")
                or item.get("text")
                or item.get("raw_text")
                or item.get("date")
                or item.get("time")
                or item.get("name")
            )
        else:
            text = item
        optional = str(text).strip() if text is not None else ""
        if optional:
            values.append(optional)
    return _dedupe(values)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _target_hard_facts_need_retry(
    source_hard_facts: dict[str, Any],
    target_hard_facts: dict[str, Any],
) -> bool:
    if not isinstance(target_hard_facts, dict):
        return True

    target_facts = target_hard_facts.get("hard_facts")
    if not isinstance(target_facts, dict):
        return True

    if not any(_fact_list_count(target_facts, field) for field in _CRITICAL_EXTRACTION_FIELDS):
        source_facts = source_hard_facts.get("hard_facts")
        if isinstance(source_facts, dict) and any(
            _fact_list_count(source_facts, field) for field in _CRITICAL_EXTRACTION_FIELDS
        ):
            return True

    return False


def _fact_list_count(hard_facts: dict[str, Any], field: str) -> int:
    value = hard_facts.get(field)
    return len(value) if isinstance(value, list) else 0
