import logging
import re
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.crawler.detail_content_extractor import fetch_notice_detail_content
from app.translation.gemini_client import GeminiJsonClient
from app.translation.orchestrator import TranslationPipeline, TranslationPipelineInput
from app.translation.prompts import (
    build_supabase_payload_prompt,
    extract_source_hard_facts_prompt,
    translate_meal_labels_prompt,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_YEARLESS_NOTICE_YEAR = 2026
# 할일(action) 카드 항목 수 상한 — 한국어/번역 카드 공통 강제
_MAX_ACTION_CARD_ITEMS = 5


class NoticeService:
    async def create_notice(self, payload: dict[str, Any]) -> dict[str, object]:
        settings = get_settings()

        if not settings.supabase_configured:
            raise RuntimeError("Supabase is not configured.")

        school_id = _optional_str(payload.get("school_id"))
        if not school_id:
            raise RuntimeError("school_id is required for school-only notices.")

        supabase = get_supabase_client()
        result = (
            supabase.table("notices")
            .insert(
                {
                    "title": payload["title"],
                    "original_text": payload.get("raw_text"),
                    "school_id": school_id,
                    "detail_url": _optional_str(payload.get("source_url")),
                    "status": "pending",
                }
            )
            .execute()
        )

        data = result.data[0] if result.data else None

        return {"ok": True, "notice": data}

    async def analyze_notice(
        self,
        notice_id: str,
        target_language: str,
        source_text: str | None = None,
        approved_ingredient_dictionary: list[dict[str, object]] | None = None,
        approved_ingredient_dictionary_target: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return await self.translate_notice(
            notice_id=notice_id,
            target_language=target_language,
            source_text=source_text,
            approved_ingredient_dictionary=approved_ingredient_dictionary or [],
            approved_ingredient_dictionary_target=approved_ingredient_dictionary_target or [],
        )

    async def translate_notice(
        self,
        notice_id: str,
        target_language: str,
        source_text: str | None = None,
        approved_ingredient_dictionary: list[dict[str, object]] | None = None,
        approved_ingredient_dictionary_target: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        if not target_language or target_language.strip().lower() == "ko":
            return await self._return_korean_notice(
                notice_id=notice_id,
                source_text=source_text,
            )

        settings = get_settings()
        if not settings.supabase_configured:
            raise RuntimeError("Supabase is not configured.")
        if not settings.gemini_configured:
            raise RuntimeError("VERTEX_AI_PROJECT_ID 또는 GEMINI_API_KEY(S)가 필요합니다.")

        supabase = get_supabase_client()
        notice_result = (
            supabase.table("notices")
            .select(
                "id,school_id,title,original_text,extracted_content,status,due_date,event_dates,event_location,source_hard_facts,"
                "detail_url,source_post_uid,crawl_result"
            )
            .eq("id", notice_id)
            .single()
            .execute()
        )
        notice = notice_result.data
        if not notice:
            raise RuntimeError("Notice was not found.")

        explicit_source_text = _optional_str(source_text)
        cached_translation = None
        if not explicit_source_text:
            cached_translation = _usable_cached_translation(
                supabase=supabase,
                notice_id=notice_id,
                target_language=target_language,
            )

        if cached_translation is not None:
            cached_validation_status = (
                _optional_str(cached_translation.get("validation_status"))
                or "passed"
            )
            if (
                cached_validation_status == "failed"
                and _optional_str(cached_translation.get("translated_text"))
            ):
                cached_validation_status = "passed"
            if _can_use_cached_translation_fast_path(notice):
                if not _has_complete_card_translation_cache(
                    supabase=supabase,
                    notice_id=notice_id,
                    target_language=target_language,
                ):
                    cached_translation = None
                else:
                    saved: dict[str, Any] = {"cached": True}
                    return {
                        "ok": True,
                        "notice_id": notice_id,
                        "target_language": target_language,
                        "status": cached_validation_status,
                        "admin_review": {
                            "required": False,
                            "reason": None,
                        },
                        "translation": cached_translation.get("translated_text"),
                        "saved": saved,
                    }

        try:
            notice = await self._ensure_notice_text(
                supabase=supabase,
                notice=notice,
                timeout_seconds=settings.crawler_timeout_seconds,
            )
            resolved_source_text = self._resolve_notice_source_text(notice, explicit_source_text)
            if not resolved_source_text:
                raise RuntimeError("번역할 원문이 없습니다.")

            gemini = GeminiJsonClient.from_settings(settings)
            pipeline = TranslationPipeline(gemini)
            try:
                result = await pipeline.run(
                    TranslationPipelineInput(
                        source_text=resolved_source_text,
                        target_language=target_language,
                        approved_ingredient_dictionary=[
                            dict(item) for item in (approved_ingredient_dictionary or [])
                        ],
                        approved_ingredient_dictionary_target=[
                            dict(item) for item in (approved_ingredient_dictionary_target or [])
                        ],
                    )
                )
            except Exception as exc:
                if not _is_gemini_quota_error(exc):
                    raise
                result = await self._best_effort_translate_notice(
                    gemini=gemini,
                    notice=notice,
                    target_language=target_language,
                    source_text=resolved_source_text,
                )

            saved = self._save_translation_result(
                supabase=supabase,
                notice=notice,
                notice_id=notice_id,
                target_language=target_language,
                pipeline_result=result,
                source_metadata=self._build_source_metadata(notice),
            )
        except Exception as exc:  # noqa: BLE001 - normalize external fetch/AI failures.
            message = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(message) from exc

        return {
            "ok": True,
            "notice_id": notice_id,
            "target_language": target_language,
            "status": result["status"],
            "admin_review": result["admin_review"],
            "translation": result.get("final_translation"),
            "saved": saved,
        }

    async def translate_text(
        self,
        *,
        source_text: str,
        target_language: str,
        translation_kind: str | None = None,
        approved_ingredient_dictionary: list[dict[str, object]] | None = None,
        approved_ingredient_dictionary_target: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        if (
            not target_language
            or (
                target_language.strip().lower() == "ko"
                and translation_kind != "message_to_ko"
            )
        ):
            return {
                "ok": True,
                "target_language": "ko",
                "status": "ready_to_save",
                "translation": source_text,
                "pipeline_result": {
                    "status": "ready_to_save",
                    "final_translation": source_text,
                    "source_language": "ko",
                    "target_language": "ko",
                },
            }

        settings = get_settings()
        if not settings.gemini_configured:
            raise RuntimeError("VERTEX_AI_PROJECT_ID 또는 GEMINI_API_KEY(S)가 필요합니다.")

        if translation_kind == "meal_labels":
            return await self._translate_meal_labels(
                source_text=source_text,
                target_language=target_language,
            )

        if translation_kind in {"notice_summary", "notice_source"}:
            try:
                fallback = await self._best_effort_translate_notice(
                    gemini=GeminiJsonClient.from_settings(settings),
                    notice={},
                    target_language=target_language,
                    source_text=source_text,
                )
            except Exception as exc:
                raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

            return {
                "ok": True,
                "target_language": target_language,
                "status": fallback["status"],
                "translation": fallback.get("final_translation"),
                "pipeline_result": fallback,
            }

        if translation_kind == "message_to_ko":
            try:
                fallback = await self._translate_message_to_korean(
                    gemini=GeminiJsonClient.from_settings(settings),
                    source_text=source_text,
                )
            except Exception as exc:
                raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

            return {
                "ok": True,
                "target_language": "ko",
                "status": fallback["status"],
                "translation": fallback.get("final_translation"),
                "pipeline_result": fallback,
            }

        try:
            gemini = GeminiJsonClient.from_settings(settings)
            pipeline = TranslationPipeline(gemini)
            result = await pipeline.run(
                TranslationPipelineInput(
                    source_text=source_text,
                    target_language=target_language,
                    approved_ingredient_dictionary=[
                        dict(item) for item in (approved_ingredient_dictionary or [])
                    ],
                    approved_ingredient_dictionary_target=[
                        dict(item) for item in (approved_ingredient_dictionary_target or [])
                    ],
                )
            )
        except Exception as exc:
            if not _is_gemini_quota_error(exc):
                raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

            fallback = await self._best_effort_translate_notice(
                gemini=GeminiJsonClient.from_settings(settings),
                notice={},
                target_language=target_language,
                source_text=source_text,
            )
            return {
                "ok": True,
                "target_language": target_language,
                "status": fallback["status"],
                "translation": fallback.get("final_translation"),
                "pipeline_result": fallback,
            }

        return {
            "ok": True,
            "target_language": target_language,
            "status": result["status"],
            "translation": result.get("final_translation"),
            "pipeline_result": result,
        }

    async def _return_korean_notice(
        self,
        *,
        notice_id: str,
        source_text: str | None,
    ) -> dict[str, object]:
        settings = get_settings()
        if not settings.supabase_configured:
            raise RuntimeError("Supabase is not configured.")

        supabase = get_supabase_client()
        notice_result = (
            supabase.table("notices")
            .select("id,title,original_text,detail_url,crawl_result")
            .eq("id", notice_id)
            .single()
            .execute()
        )
        notice = notice_result.data
        if not notice:
            raise RuntimeError("Notice was not found.")

        notice = await self._ensure_notice_text(
            supabase=supabase,
            notice=notice,
            timeout_seconds=settings.crawler_timeout_seconds,
        )
        resolved_source_text = self._resolve_notice_source_text(
            notice,
            _optional_str(source_text),
        )
        if not resolved_source_text:
            raise RuntimeError("번역할 원문이 없습니다.")

        return {
            "ok": True,
            "notice_id": notice_id,
            "target_language": "ko",
            "status": "ready_to_save",
            "admin_review": {
                "required": False,
                "reason": None,
            },
            "translation": resolved_source_text,
            "saved": {},
        }

    async def refresh_notice_canonical_artifacts(
        self,
        *,
        notice_id: str,
        source_text: str | None,
    ) -> dict[str, object]:
        settings = get_settings()
        if not settings.supabase_configured:
            raise RuntimeError("Supabase is not configured.")

        supabase = get_supabase_client()
        notice_result = (
            supabase.table("notices")
            .select(
                "id,school_id,title,original_text,extracted_content,status,due_date,event_dates,event_location,source_hard_facts,"
                "detail_url,source_post_uid,crawl_result"
            )
            .eq("id", notice_id)
            .single()
            .execute()
        )
        notice = notice_result.data
        if not notice:
            raise RuntimeError("Notice was not found.")

        notice = await self._ensure_notice_text(
            supabase=supabase,
            notice=notice,
            timeout_seconds=settings.crawler_timeout_seconds,
        )
        resolved_source_text = self._resolve_notice_source_text(
            notice,
            _optional_str(source_text),
        )
        if not resolved_source_text:
            raise RuntimeError("구조화할 원문이 없습니다.")

        if _notice_has_canonical_artifacts(supabase=supabase, notice=notice):
            return {
                "ok": True,
                "notice_id": notice_id,
                "target_language": "ko",
                "status": "ready_to_save",
                "admin_review": {
                    "required": False,
                    "reason": None,
                },
                "translation": resolved_source_text,
                "saved": {"cached": True},
            }

        if not settings.gemini_configured:
            return {
                "ok": True,
                "notice_id": notice_id,
                "target_language": "ko",
                "status": "ready_to_save",
                "admin_review": {
                    "required": False,
                    "reason": None,
                },
                "translation": resolved_source_text,
                "saved": {},
            }

        gemini = GeminiJsonClient.from_settings(settings)
        pipeline_result = await self._build_korean_notice_artifacts(
            gemini=gemini,
            source_text=resolved_source_text,
        )
        saved = self._save_translation_result(
            supabase=supabase,
            notice=notice,
            notice_id=notice_id,
            target_language="ko",
            pipeline_result=pipeline_result,
            source_metadata=self._build_source_metadata(notice),
        )
        return {
            "ok": True,
            "notice_id": notice_id,
            "target_language": "ko",
            "status": "ready_to_save",
            "admin_review": {
                "required": False,
                "reason": None,
            },
            "translation": resolved_source_text,
            "saved": saved,
        }

    async def _build_korean_notice_artifacts(
        self,
        *,
        gemini: GeminiJsonClient,
        source_text: str,
    ) -> dict[str, Any]:
        source_hard_facts = await gemini.generate_json(
            prompt=extract_source_hard_facts_prompt(source_text),
            temperature=0.0,
            model=getattr(gemini, "source_hard_fact_model", None),
        )
        source_hard_facts = _sanitize_source_hard_facts(source_hard_facts, source_text)
        validation_results = {
            "hard_fact": {
                "status": "skipped",
                "attempts": 0,
                "issues": [],
            },
            "context_tone": {
                "status": "skipped",
                "attempts": 0,
                "issues": [],
            },
        }
        metadata = await gemini.generate_json(
            prompt=build_supabase_payload_prompt(
                source_text=source_text,
                final_target_translation=source_text,
                source_hard_facts=source_hard_facts,
                validation_results=validation_results,
                target_language="ko",
            ),
            temperature=0.0,
        )
        if isinstance(metadata, dict):
            metadata = _sanitize_metadata_for_source_text(metadata, source_text)
        return {
            "status": "ready_to_save",
            "source_language": "ko",
            "target_language": "ko",
            "source_text": source_text,
            "final_translation": source_text,
            "source_hard_facts": source_hard_facts,
            "target_hard_facts": {},
            "ingredient_identity_map": {},
            "validation": validation_results,
            "admin_review": {
                "required": False,
                "reason": None,
                "priority": "normal",
            },
            "metadata": metadata,
            "raw_steps": {
                "canonical_source_hard_facts": source_hard_facts,
            },
        }

    async def _translate_meal_labels(
        self,
        *,
        source_text: str,
        target_language: str,
    ) -> dict[str, object]:
        settings = get_settings()
        gemini = GeminiJsonClient.from_settings(settings)
        items = _parse_meal_label_source_text(source_text)
        if not items:
            return {
                "ok": True,
                "target_language": target_language,
                "status": "ready_to_save",
                "translation": source_text,
                "translations": {},
                "pipeline_result": {"final_translation": source_text},
            }

        prompt = translate_meal_labels_prompt(
            target_language=target_language,
            items=items,
        )
        response = await gemini.generate_json(prompt=prompt, temperature=0.1)
        translated_items = response.get("items")
        translations: dict[str, str] = {}
        if isinstance(translated_items, list):
            for item in translated_items:
                if not isinstance(item, dict):
                    continue
                item_id = _optional_str(item.get("id"))
                translation = _optional_str(item.get("translation"))
                if item_id and translation:
                    translations[item_id] = translation

        # Fill any missing items with the original text so the client gets a full map.
        for item in items:
            item_id = item["id"]
            translations.setdefault(item_id, item["text"])

        lines = [f"[[{item['id']}]] {translations[item['id']]}" for item in items]
        final_translation = "\n".join(lines)
        return {
            "ok": True,
            "target_language": target_language,
            "status": "ready_to_save",
            "translation": final_translation,
            "translations": translations,
            "pipeline_result": {
                "final_translation": final_translation,
            },
        }

    async def _best_effort_translate_notice(
        self,
        *,
        gemini: GeminiJsonClient,
        notice: dict[str, Any],
        target_language: str,
        source_text: str,
    ) -> dict[str, Any]:
        prompt = _best_effort_translation_prompt(
            source_text=source_text,
            target_language=target_language,
            title=_optional_str(notice.get("title")),
        )
        fallback = await gemini.generate_json(prompt=prompt, temperature=0.1)
        translated_text = _optional_str(fallback.get("target_translation"))
        if not translated_text:
            raise RuntimeError("Gemini fallback translation did not return target_translation.")

        fallback_title = _optional_str(fallback.get("title"))

        return {
            "status": "ready_to_save",
            "source_language": "ko",
            "target_language": target_language,
            "source_text": source_text,
            "final_translation": translated_text,
            "source_hard_facts": {},
            "target_hard_facts": {},
            "ingredient_identity_map": {},
            "validation": {
                "hard_fact": {
                    "status": "skipped",
                    "attempts": 0,
                    "issues": ["quota_best_effort_fallback"],
                },
                "context_tone": {
                    "status": "skipped",
                    "attempts": 0,
                    "issues": ["quota_best_effort_fallback"],
                },
            },
            "admin_review": {
                "required": False,
                "reason": None,
                "priority": "normal",
            },
            "metadata": {
                "title": fallback_title,
                "title_target_language": fallback_title,
                "fallback_mode": "quota_best_effort",
                "validation_status": "passed",
                "validation_failure_reason": "quota_best_effort_fallback",
            },
            "raw_steps": {
                "best_effort": fallback,
            },
        }

    async def _translate_message_to_korean(
        self,
        *,
        gemini: GeminiJsonClient,
        source_text: str,
    ) -> dict[str, Any]:
        prompt = _message_to_korean_prompt(source_text=source_text)
        result = await gemini.generate_json(prompt=prompt, temperature=0.1)
        translated_text = _optional_str(result.get("translated_korean"))
        if not translated_text:
            raise RuntimeError("Gemini message translation did not return translated_korean.")

        return {
            "status": "ready_to_save",
            "source_language": "auto",
            "target_language": "ko",
            "source_text": source_text,
            "final_translation": translated_text,
            "source_hard_facts": {},
            "target_hard_facts": {},
            "ingredient_identity_map": {},
            "validation": {
                "hard_fact": {
                    "status": "skipped",
                    "attempts": 0,
                    "issues": ["message_to_ko_light_translation"],
                },
                "context_tone": {
                    "status": "skipped",
                    "attempts": 0,
                    "issues": ["message_to_ko_light_translation"],
                },
            },
            "admin_review": {
                "required": False,
                "reason": None,
                "priority": "normal",
            },
            "metadata": {
                "title": None,
                "fallback_mode": "message_to_ko_light_translation",
                "validation_status": "passed",
                "validation_failure_reason": None,
            },
            "raw_steps": {
                "message_to_ko": result,
            },
        }

    def _save_translation_result(
        self,
        *,
        supabase: Any,
        notice: dict[str, Any],
        notice_id: str,
        target_language: str,
        pipeline_result: dict[str, Any],
        source_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        pipeline_result = _with_sanitized_source_hard_facts(pipeline_result)
        pipeline_result = _with_sanitized_metadata(pipeline_result)
        metadata = dict(pipeline_result.get("metadata") or {})
        if source_metadata:
            metadata["notice_context"] = source_metadata
        status = pipeline_result.get("status")
        validation_status = str(
            pipeline_result.get("validation_status")
            or metadata.get("validation_status")
            or ("passed" if status == "ready_to_save" else "failed")
        )
        if _optional_str(pipeline_result.get("final_translation")):
            validation_status = "passed"
            metadata["validation_status"] = validation_status
            if metadata.get("validation_failure_reason"):
                LOGGER.warning(
                    "notice translation saved with validation warning: notice_id=%s target_language=%s reason=%s",
                    notice_id,
                    target_language,
                    metadata.get("validation_failure_reason"),
                )
        _log_translation_pipeline_summary(
            notice_id=notice_id,
            target_language=target_language,
            pipeline_result=pipeline_result,
            validation_status=validation_status,
        )

        row = {
            "notice_id": notice_id,
            "target_language": target_language,
            "source_language": "ko",
            "translated_title": _translated_title_for_save(
                metadata=metadata,
                pipeline_result=pipeline_result,
                target_language=target_language,
            ),
            "translated_location": _translated_event_location_from_pipeline(
                pipeline_result,
                target_language=target_language,
            ),
            "translated_text": pipeline_result.get("final_translation"),
            "validation_status": validation_status,
        }
        upsert = (
            supabase.table("notice_ai_translations")
            .upsert(row, on_conflict="notice_id,target_language")
            .execute()
        )
        cards: list[dict[str, Any]] = []
        school_events: list[dict[str, Any]] = []
        notice_patch: dict[str, Any] = {}

        if target_language == "ko":
            cards = self._replace_notice_cards_from_pipeline(
                supabase=supabase,
                notice_id=notice_id,
                pipeline_result=pipeline_result,
            )
            school_events = self._replace_school_events_from_pipeline(
                supabase=supabase,
                notice=notice,
                notice_id=notice_id,
                pipeline_result=pipeline_result,
            )

            notice_patch["due_date"] = _due_date_from_pipeline(pipeline_result)
            notice_patch["event_dates"] = _event_dates_json_from_pipeline(pipeline_result)
            notice_patch["event_location"] = _event_location_from_pipeline(pipeline_result)
            notice_patch["source_hard_facts"] = pipeline_result.get("source_hard_facts") or {}
            if metadata.get("title"):
                notice_patch["title"] = metadata["title"]
            if pipeline_result.get("status") == "ready_to_save":
                notice_patch["status"] = "done"

            if notice_patch:
                supabase.table("notices").update(notice_patch).eq("id", notice_id).execute()

        current_cards = self._load_notice_cards(
            supabase=supabase,
            notice_id=notice_id,
        )
        if target_language != "ko" and not current_cards:
            current_cards = self._backfill_notice_cards_for_translation(
                supabase=supabase,
                notice_id=notice_id,
                pipeline_result=pipeline_result,
            )
        card_translations = self._replace_notice_card_translations_from_pipeline(
            supabase=supabase,
            cards=current_cards,
            target_language=target_language,
            pipeline_result=pipeline_result,
        )

        return {
            "translation_row": upsert.data[0] if upsert.data else None,
            "cards": cards,
            "card_translations": card_translations,
            "school_events": school_events,
            "notice_patch": notice_patch,
        }

    async def _ensure_notice_text(
        self,
        *,
        supabase: Any,
        notice: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if _optional_str(notice.get("original_text")):
            return notice

        detail_url = _optional_str(notice.get("detail_url"))
        if not detail_url:
            return notice

        detail = await fetch_notice_detail_content(detail_url, timeout=timeout_seconds)
        if not detail.text:
            return notice

        crawl_result = notice.get("crawl_result")
        next_crawl_result = dict(crawl_result) if isinstance(crawl_result, dict) else {}
        next_crawl_result["detail_fetch"] = {
            "final_url": detail.final_url,
            "title": detail.title,
            "text_length": len(detail.text),
        }
        supabase.table("notices").update(
            {
                "original_text": detail.text,
                "crawl_result": next_crawl_result,
            }
        ).eq("id", notice["id"]).execute()

        next_notice = dict(notice)
        next_notice["original_text"] = detail.text
        next_notice["crawl_result"] = next_crawl_result
        if detail.title and not _optional_str(next_notice.get("title")):
            next_notice["title"] = detail.title
        return next_notice

    def _load_notice_cards(
        self,
        *,
        supabase: Any,
        notice_id: str,
    ) -> list[dict[str, Any]]:
        return (
            supabase.table("notice_cards")
            .select("id,type,order,content")
            .eq("notice_id", notice_id)
            .execute()
            .data
            or []
        )

    def _backfill_notice_cards_for_translation(
        self,
        *,
        supabase: Any,
        notice_id: str,
        pipeline_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if pipeline_result.get("status") != "ready_to_save":
            return []

        cards = _build_notice_cards(
            notice_id=notice_id,
            pipeline_result=pipeline_result,
        )
        if not cards:
            return []

        result = supabase.table("notice_cards").insert(cards).execute()
        inserted = result.data or []
        if any(_optional_str(row.get("id")) for row in inserted if isinstance(row, dict)):
            return inserted
        return self._load_notice_cards(supabase=supabase, notice_id=notice_id)

    def _resolve_notice_source_text(
        self,
        notice: dict[str, Any],
        explicit_source_text: str | None,
    ) -> str:
        explicit = _optional_str(explicit_source_text)
        if explicit:
            return explicit

        original_text = _optional_str(notice.get("original_text"))
        if original_text:
            return original_text

        crawler_text = self._extract_crawler_text(notice)
        if crawler_text:
            return crawler_text

        detail_url = _optional_str(notice.get("detail_url"))
        suffix = f" detail_url={detail_url}" if detail_url else ""
        raise RuntimeError(
            "번역할 공지 본문이 아직 추출되지 않았습니다. "
            "번역 전에 content extraction 단계가 original_text를 채워야 합니다."
            f"{suffix}"
        )

    def _extract_crawler_text(self, notice: dict[str, Any]) -> str:
        crawl_result = notice.get("crawl_result")
        if not isinstance(crawl_result, dict):
            return ""

        post = crawl_result.get("post")
        post_data = post if isinstance(post, dict) else {}
        chunks: list[str] = []
        title = _optional_str(notice.get("title"))
        if title:
            chunks.append(f"제목: {title}")

        for container in (post_data, crawl_result):
            for key in (
                "detail_text",
                "body_text",
                "content_text",
                "text",
                "snippet",
                "page_snippet",
                "description",
            ):
                value = _optional_str(container.get(key))
                if value and value not in chunks:
                    chunks.append(value)

        return "\n\n".join(chunks).strip() if len(chunks) > 1 else ""

    def _build_source_metadata(self, notice: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            "school_id": notice.get("school_id"),
            "detail_url": notice.get("detail_url"),
            "source_post_uid": notice.get("source_post_uid"),
            "extracted_content": _extraction_metadata(notice.get("extracted_content")),
        }
        crawl_result = notice.get("crawl_result")
        if isinstance(crawl_result, dict):
            metadata["crawl_result"] = {
                "status": crawl_result.get("status"),
                "board_url": crawl_result.get("board_url"),
                "board_kind": crawl_result.get("board_kind"),
                "cms_key": crawl_result.get("cms_key"),
                "parser_family": crawl_result.get("parser_family"),
                "crawl_checked_at": crawl_result.get("crawl_checked_at"),
                "post_rank": crawl_result.get("post_rank"),
            }
        return {key: value for key, value in metadata.items() if value is not None}

    def _replace_notice_cards_from_pipeline(
        self,
        *,
        supabase: Any,
        notice_id: str,
        pipeline_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if pipeline_result.get("status") != "ready_to_save":
            return []

        cards = _build_notice_cards(
            notice_id=notice_id,
            pipeline_result=pipeline_result,
        )

        existing_rows = (
            supabase.table("notice_cards")
            .select("id,type,order,content")
            .eq("notice_id", notice_id)
            .execute()
            .data
            or []
        )
        if not cards:
            for row in existing_rows:
                if row.get("id"):
                    supabase.table("notice_cards").delete().eq("id", row["id"]).execute()
            return []

        existing_by_slot = {
            (row.get("type"), row.get("order")): row
            for row in existing_rows
            if row.get("id")
        }
        next_slots = {(card["type"], card["order"]) for card in cards}

        saved: list[dict[str, Any]] = []
        inserts: list[dict[str, Any]] = []
        for card in cards:
            slot = (card["type"], card["order"])
            existing = existing_by_slot.get(slot)
            if not existing:
                inserts.append(card)
                continue

            result = (
                supabase.table("notice_cards")
                .update({"content": card["content"]})
                .eq("id", existing["id"])
                .execute()
            )
            saved.extend(result.data or [])

        if inserts:
            result = supabase.table("notice_cards").insert(inserts).execute()
            saved.extend(result.data or [])

        for slot, existing in existing_by_slot.items():
            if slot in next_slots:
                continue
            supabase.table("notice_cards").delete().eq("id", existing["id"]).execute()

        return saved

    def _replace_notice_card_translations_from_pipeline(
        self,
        *,
        supabase: Any,
        cards: list[dict[str, Any]],
        target_language: str,
        pipeline_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not target_language or target_language == "ko":
            return []

        saved: list[dict[str, Any]] = []
        for card in cards:
            card_id = _optional_str(card.get("id"))
            card_type = _optional_str(card.get("type"))
            if not card_id or not card_type:
                continue

            translated_content = _translated_card_content_for_type(
                pipeline_result=pipeline_result,
                card_type=card_type,
                target_language=target_language,
            )
            if translated_content is None:
                continue

            result = (
                supabase.table("notice_card_translations")
                .upsert(
                    {
                        "notice_card_id": card_id,
                        "target_language": target_language,
                        "translated_content": translated_content,
                    },
                    on_conflict="notice_card_id,target_language",
                )
                .execute()
            )
            saved.extend(result.data or [])
        return saved

    def _replace_school_events_from_pipeline(
        self,
        *,
        supabase: Any,
        notice: dict[str, Any],
        notice_id: str,
        pipeline_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        school_id = _optional_str(notice.get("school_id"))
        if not school_id:
            return []

        existing_rows = (
            supabase.table("school_events")
            .select("id,event_date")
            .eq("notice_id", notice_id)
            .execute()
            .data
            or []
        )
        event_entries = _school_event_entries_from_pipeline(pipeline_result)
        if not event_entries:
            for row in existing_rows:
                if row.get("id"):
                    supabase.table("school_events").delete().eq("id", row["id"]).execute()
            return []

        title = (
            _optional_str((pipeline_result.get("metadata") or {}).get("title"))
            or _optional_str(notice.get("title"))
            or "학교 일정"
        )
        location = (
            _optional_str(notice.get("event_location"))
            or _event_location_from_pipeline(pipeline_result)
        )
        description = (
            _first_non_empty_line(notice.get("original_text"))
            or title
        )

        rows = [
            {
                "school_id": school_id,
                "notice_id": notice_id,
                "title": title,
                "event_date": entry["event_date"],
                "event_kinds": entry["event_kinds"],
                "location": location,
                "description": description,
                "source_language": "ko",
            }
            for entry in event_entries
        ]
        result = (
            supabase.table("school_events")
            .upsert(rows, on_conflict="notice_id,event_date")
            .execute()
        )

        next_dates = {entry["event_date"] for entry in event_entries}
        for row in existing_rows:
            row_id = row.get("id")
            event_date = _optional_str(row.get("event_date"))
            if row_id and event_date and event_date not in next_dates:
                supabase.table("school_events").delete().eq("id", row_id).execute()

        return result.data or rows


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _usable_cached_translation(
    *,
    supabase: Any,
    notice_id: str,
    target_language: str,
) -> dict[str, Any] | None:
    if not target_language or target_language == "ko":
        return None

    query = (
        supabase.table("notice_ai_translations")
        .select(
            "translated_title,translated_location,translated_text,validation_status"
        )
        .eq("notice_id", notice_id)
        .eq("target_language", target_language)
    )
    row = _execute_optional_single(query)
    if not isinstance(row, dict):
        return None

    translated_text = _optional_str(row.get("translated_text"))
    if not translated_text:
        return None

    return row


def _notice_has_canonical_artifacts(*, supabase: Any, notice: dict[str, Any]) -> bool:
    source_text = _optional_str(notice.get("original_text"))
    if source_text and _source_hard_facts_need_refresh(notice.get("source_hard_facts"), source_text):
        return False

    source_facts = _hard_facts(notice.get("source_hard_facts"))
    has_notice_fields = bool(
        source_facts
        or _optional_str(notice.get("due_date"))
        or _optional_str(notice.get("event_location"))
        or (
            isinstance(notice.get("event_dates"), list)
            and any(isinstance(item, str) and item.strip() for item in notice.get("event_dates"))
        )
    )
    if not has_notice_fields:
        return False

    notice_id = _optional_str(notice.get("id"))
    if not notice_id:
        return False

    card_rows = (
        supabase.table("notice_cards")
        .select("id")
        .eq("notice_id", notice_id)
        .execute()
        .data
        or []
    )
    return any(_optional_str(row.get("id")) for row in card_rows if isinstance(row, dict))


def _has_complete_card_translation_cache(
    *,
    supabase: Any,
    notice_id: str,
    target_language: str,
) -> bool:
    card_rows = (
        supabase.table("notice_cards")
        .select("id")
        .eq("notice_id", notice_id)
        .execute()
        .data
        or []
    )
    card_ids = [
        _optional_str(row.get("id"))
        for row in card_rows
        if _optional_str(row.get("id"))
    ]
    if not card_ids:
        return True

    translated_count = 0
    for card_id in card_ids:
        query = (
            supabase.table("notice_card_translations")
            .select("id")
            .eq("notice_card_id", card_id)
            .eq("target_language", target_language)
        )
        row = _execute_optional_single(query)
        if isinstance(row, dict) and _optional_str(row.get("id")):
            translated_count += 1

    return translated_count >= len(card_ids)


def _execute_optional_single(query: Any) -> dict[str, Any] | None:
    maybe_single = getattr(query, "maybeSingle", None)
    if callable(maybe_single):
        result = maybe_single().execute()
    else:
        result = query.execute()

    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else None
    return data if isinstance(data, dict) else None


def _can_use_cached_translation_fast_path(notice: dict[str, Any]) -> bool:
    if str(notice.get("status") or "").strip().lower() != "done":
        return False

    source_text = _optional_str(notice.get("original_text"))
    if source_text and _source_hard_facts_need_refresh(notice.get("source_hard_facts"), source_text):
        return False

    source_facts = _hard_facts(notice.get("source_hard_facts"))
    if source_facts:
        return True

    event_dates = notice.get("event_dates")
    if isinstance(event_dates, list) and any(isinstance(item, str) and item.strip() for item in event_dates):
        return True

    if _optional_str(notice.get("due_date")) or _optional_str(notice.get("event_location")):
        return True

    return False


def _log_translation_pipeline_summary(
    *,
    notice_id: str,
    target_language: str,
    pipeline_result: dict[str, Any],
    validation_status: str,
) -> None:
    source_facts = _hard_facts(pipeline_result.get("source_hard_facts"))
    target_facts = _hard_facts(pipeline_result.get("target_hard_facts"))
    validation = pipeline_result.get("validation") if isinstance(pipeline_result.get("validation"), dict) else {}
    ingredient_map = (
        pipeline_result.get("ingredient_identity_map")
        if isinstance(pipeline_result.get("ingredient_identity_map"), dict)
        else {}
    )
    LOGGER.info(
        "translation pipeline summary: notice_id=%s target_language=%s validation_status=%s source_dates=%s target_dates=%s hard_fact_issues=%s context_issues=%s unmapped_ingredients=%s raw_steps=%s",
        notice_id,
        target_language,
        validation_status,
        len(_values(source_facts.get("dates"))) + len(_values(source_facts.get("deadlines"))),
        len(_values(target_facts.get("dates"))) + len(_values(target_facts.get("deadlines"))),
        len(((validation.get("hard_fact") or {}).get("issues") or [])) if isinstance(validation.get("hard_fact"), dict) else 0,
        len(((validation.get("context_tone") or {}).get("issues") or [])) if isinstance(validation.get("context_tone"), dict) else 0,
        len(list(ingredient_map.get("unmapped_ingredients") or [])),
        sorted((pipeline_result.get("raw_steps") or {}).keys()) if isinstance(pipeline_result.get("raw_steps"), dict) else [],
    )


def _is_gemini_quota_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        token in message
        for token in (
            "429",
            "too many requests",
            "quota",
            "resource_exhausted",
            "rate limit",
            "rate_limit",
        )
    )


def _best_effort_translation_prompt(
    *,
    source_text: str,
    target_language: str,
    title: str | None,
) -> str:
    title_block = f"공지 제목: {title}\n" if title else ""
    return f"""
너는 한국 학교 공지를 학부모가 이해하기 쉽게 번역하는 번역기다.

규칙:
- JSON object만 반환해라.
- 사실을 추가하거나 추측하지 마라.
- 날짜, 시간, 준비물, 제출물, 금액, 장소, 대상 학년은 가능한 한 원문 그대로 보존해라.
- 읽기 쉬운 줄바꿈을 사용해라: 짧은 문단을 빈 줄 하나로 구분하고, 날짜·마감·해야 할 일·금액·준비물·장소는 각각 "- "로 시작하는 한 줄에 둔다. 문장 중간에서 줄을 끊지 마라.
- 모든 날짜는 대상 언어의 표준 일상 표기로 써라. 예: 베트남어 `03/07/2026 (Thứ Sáu)`, 러시아어 `03.07.2026 (пятница)`, 중국어 `2026年7月3日(周五)`, 영어 `July 3, 2026 (Fri)`. 요일 단어는 대상 언어로 쓴다. 문서 전체에서 한 가지 형식으로 통일하고, `7월 1일` 같은 한국어 표기를 출력에 섞지 마라. 연도 숫자는 원문 그대로 유지해라(불기 등 다른 달력으로 변환 금지).
- 번역 품질이 완벽하지 않아도 좋으니 반드시 전체 공지를 끝까지 번역해라.

반환 스키마:
{{
  "title": "번역된 짧은 제목",
  "target_translation": "전체 번역문"
}}

대상 언어: {target_language}
{title_block}
원문:
\"\"\"
{source_text}
\"\"\"
""".strip()


def _message_to_korean_prompt(*, source_text: str) -> str:
    return f"""
너는 학부모가 선생님께 보내고 싶은 말을 자연스럽고 공손한 한국어로 바꿔 주는 번역기다.

규칙:
- JSON object만 반환해라.
- 입력 문장의 언어를 스스로 파악한 뒤, 반드시 한국어로 번역해라.
- 출력은 반드시 한국어여야 한다. 영어, 러시아어, 아랍어, 원문 언어를 그대로 남기지 마라.
- 선생님께 보내는 짧은 메시지처럼 자연스럽고 공손하게 써라.
- 원문에 없는 사실을 추가하거나 추측하지 마라.
- 날짜, 시간, 금액, 이름, 연락처 같은 구체 정보는 그대로 보존해라.
- 너무 딱딱한 공문체가 아니라, 학부모가 보낼 법한 정중한 문장으로 다듬어라.

반환 스키마:
{{
  "translated_korean": "공손한 한국어 메시지"
}}

입력 문장:
\"\"\"
{source_text}
\"\"\"
""".strip()


def _extraction_metadata(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value.get(key)
        for key in (
            "schema_version",
            "final_url",
            "content_kind",
            "included_source_ids",
            "metadata",
            "errors",
        )
        if value.get(key) not in (None, "", [])
    }


def _merge_card_content(existing: object, incoming: object) -> dict[str, Any]:
    merged = dict(existing) if isinstance(existing, dict) else {}
    if isinstance(incoming, dict):
        merged.update(incoming)
    return merged


def _due_date_from_pipeline(pipeline_result: dict[str, Any]) -> str | None:
    """추출된 deadlines(정규화 YYYY-MM-DD) 중 가장 이른 날짜를 반환한다.

    deadlines는 '제출/행동 마감일'이므로 school_events.event_date(행사일 포함)와 달리
    홈 D-day에 바로 쓸 수 있다. 정규화된 ISO가 없으면 None.
    """
    source_facts = _hard_facts(pipeline_result.get("source_hard_facts"))
    target_facts = _hard_facts(pipeline_result.get("target_hard_facts"))
    metadata = pipeline_result.get("metadata") if isinstance(pipeline_result.get("metadata"), dict) else {}
    deadlines: list[str] = []
    for container in (source_facts, target_facts):
        deadlines.extend(_normalized_iso_dates(container.get("deadlines")))
    deadlines.extend(_canonical_metadata_iso_dates(metadata, "deadlines"))
    deadlines.extend(_metadata_card_section_dates(metadata, "action"))
    deadlines = _dedupe(deadlines)
    if not deadlines:
        return None
    # YYYY-MM-DD는 사전식 정렬이 곧 날짜 정렬이므로 min이 가장 이른 마감일.
    return min(deadlines)


def _event_dates_json_from_pipeline(pipeline_result: dict[str, Any]) -> list[str]:
    return [entry["event_date"] for entry in _school_event_entries_from_pipeline(pipeline_result)]


def _event_location_from_pipeline(pipeline_result: dict[str, Any]) -> str | None:
    return _schedule_location_from_source_pipeline(pipeline_result) or _schedule_location_from_metadata(pipeline_result)


def _translated_title_for_save(
    *,
    metadata: dict[str, Any],
    pipeline_result: dict[str, Any],
    target_language: str,
) -> str | None:
    if target_language == "ko":
        return (
            _optional_str(metadata.get("title"))
            or _title_from_translation_first_line(pipeline_result.get("final_translation"))
        )

    return (
        _optional_str(metadata.get("title_target_language"))
        or _title_from_translation_first_line(pipeline_result.get("final_translation"))
    )


def _title_from_translation_first_line(final_translation: object) -> str | None:
    text = _optional_str(final_translation)
    if not text:
        return None
    for line in text.splitlines():
        candidate = line.strip("#*-•> \t")
        if candidate:
            return candidate[:120]
    return None


def _translated_event_location_from_pipeline(
    pipeline_result: dict[str, Any],
    *,
    target_language: str | None = None,
) -> str | None:
    resolved_target = _optional_str(target_language) or _optional_str(pipeline_result.get("target_language"))
    if not resolved_target or resolved_target == "ko":
      return None
    return _schedule_location_from_pipeline(pipeline_result) or _translated_schedule_location_from_metadata(
        pipeline_result,
        target_language=resolved_target,
    )


def _schedule_dates_from_pipeline(pipeline_result: dict[str, Any]) -> list[str]:
    return [entry["event_date"] for entry in _school_event_entries_from_pipeline(pipeline_result)]


def _school_event_entries_from_pipeline(pipeline_result: dict[str, Any]) -> list[dict[str, Any]]:
    source_facts = _hard_facts(pipeline_result.get("source_hard_facts"))
    target_facts = _hard_facts(pipeline_result.get("target_hard_facts"))
    metadata = pipeline_result.get("metadata") if isinstance(pipeline_result.get("metadata"), dict) else {}
    order: list[str] = []
    kinds_by_date: dict[str, set[str]] = {}

    def add(values: list[str], kind: str) -> None:
        for value in values:
            if value not in kinds_by_date:
                kinds_by_date[value] = set()
                order.append(value)
            kinds_by_date[value].add(kind)

    for container in (target_facts, source_facts):
        add(_normalized_iso_dates(container.get("dates")), "event")
        add(_normalized_iso_dates(container.get("deadlines")), "deadline")
    add(_canonical_metadata_iso_dates(metadata, "important_dates"), "event")
    add(_canonical_metadata_iso_dates(metadata, "deadlines"), "deadline")
    add(_metadata_card_section_dates(metadata, "action"), "deadline")

    return [
        {
            "event_date": value,
            "event_kinds": [kind for kind in ("deadline", "event") if kind in kinds_by_date.get(value, set())],
        }
        for value in order
    ]


def _schedule_location_from_pipeline(pipeline_result: dict[str, Any]) -> str | None:
    source_facts = _hard_facts(pipeline_result.get("source_hard_facts"))
    target_facts = _hard_facts(pipeline_result.get("target_hard_facts"))
    return _first_value(target_facts.get("locations")) or _first_value(source_facts.get("locations"))


def _schedule_location_from_source_pipeline(pipeline_result: dict[str, Any]) -> str | None:
    source_facts = _hard_facts(pipeline_result.get("source_hard_facts"))
    return _first_value(source_facts.get("locations"))


def _schedule_location_from_metadata(pipeline_result: dict[str, Any]) -> str | None:
    metadata = pipeline_result.get("metadata") if isinstance(pipeline_result.get("metadata"), dict) else {}
    locations = _metadata_card_locations(metadata, "schedule")
    return locations[0] if locations else None


def _translated_schedule_location_from_metadata(
    pipeline_result: dict[str, Any],
    *,
    target_language: str,
) -> str | None:
    metadata = pipeline_result.get("metadata") if isinstance(pipeline_result.get("metadata"), dict) else {}
    locations = _translated_metadata_card_locations(
        metadata,
        pipeline_result,
        "schedule",
        target_language=target_language,
    )
    return locations[0] if locations else None


def _build_notice_cards(
    *,
    notice_id: str,
    pipeline_result: dict[str, Any],
) -> list[dict[str, Any]]:
    source_facts = _hard_facts(pipeline_result.get("source_hard_facts"))
    metadata = pipeline_result.get("metadata") if isinstance(pipeline_result.get("metadata"), dict) else {}
    cards: list[dict[str, Any]] = []
    order = 0

    action_items = _canonical_action_card_items(
        source_facts=source_facts,
        metadata=metadata,
    )
    if action_items:
        cards.append(
            _card_row(
                notice_id=notice_id,
                card_type="action",
                order=order,
                content={
                    "items": action_items,
                },
            )
        )

    return cards


def _translated_card_content_for_type(
    *,
    pipeline_result: dict[str, Any],
    card_type: str,
    target_language: str | None = None,
) -> dict[str, Any] | None:
    metadata = pipeline_result.get("metadata")
    if not isinstance(metadata, dict):
        return None

    card_sections = _translated_card_sections(metadata, pipeline_result, target_language=target_language)
    if not isinstance(card_sections, dict):
        return None

    section = card_sections.get(card_type)
    if not isinstance(section, dict):
        return None

    raw_items = section.get("items")
    if not isinstance(raw_items, list):
        return None

    items: list[dict[str, str]] = []
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            text = raw_item.strip()
            if text:
                items.append({"text": text})
            continue
        if not isinstance(raw_item, dict):
            continue
        text = _optional_str(raw_item.get("text"))
        if not text:
            continue
        item = {"text": text}
        hint = _optional_str(raw_item.get("hint"))
        if hint:
            item["hint"] = hint
        items.append(item)

    if not items:
        return None
    if card_type == "action":
        items = items[:_MAX_ACTION_CARD_ITEMS]
    return {"items": items}


def _card_row(
    *,
    notice_id: str,
    card_type: str,
    order: int,
    content: dict[str, Any],
) -> dict[str, Any]:
    return {
        "notice_id": notice_id,
        "type": card_type,
        "order": order,
        "content": {
            "ko": {key: value for key, value in content.items() if value not in (None, "", [])}
        },
    }


def _first_non_empty_line(value: object) -> str | None:
    text = _optional_str(value)
    if not text:
        return None
    for line in text.splitlines():
        normalized = line.strip()
        if normalized:
            return normalized[:160]
    return None


def _canonical_action_card_items(
    *,
    source_facts: dict[str, Any],
    metadata: dict[str, Any],
) -> list[dict[str, str]]:
    actions = _values(source_facts.get("actions_required")) or _canonical_metadata_values(metadata, "actions_required")
    submissions = _values(source_facts.get("submissions"))
    deadline = _first_value(source_facts.get("deadlines"))
    metadata_items = _metadata_card_items(metadata, "action")
    if not actions and not submissions and metadata_items:
        return metadata_items[:_MAX_ACTION_CARD_ITEMS]
    if not deadline:
        deadline = _first_value(_canonical_metadata_values(metadata, "deadlines"))
    raw_items = _dedupe([*actions, *[f"제출: {item}" for item in submissions]])[:_MAX_ACTION_CARD_ITEMS]
    items: list[dict[str, str]] = []
    for index, action in enumerate(raw_items):
        item = {"text": action}
        if deadline and index == 0:
            item["hint"] = deadline
        items.append(item)
    return items


def _hard_facts(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    facts = value.get("hard_facts")
    return facts if isinstance(facts, dict) else {}


def _with_sanitized_source_hard_facts(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    source_text = _optional_str(pipeline_result.get("source_text"))
    if not source_text:
        return pipeline_result

    sanitized = _sanitize_source_hard_facts(pipeline_result.get("source_hard_facts"), source_text)
    if sanitized == pipeline_result.get("source_hard_facts"):
        return pipeline_result

    next_result = dict(pipeline_result)
    next_result["source_hard_facts"] = sanitized
    return next_result


def _with_sanitized_metadata(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    source_text = _optional_str(pipeline_result.get("source_text"))
    metadata = pipeline_result.get("metadata")
    if not source_text or not isinstance(metadata, dict):
        return pipeline_result

    sanitized = _sanitize_metadata_for_source_text(metadata, source_text)
    if sanitized == metadata:
        return pipeline_result

    next_result = dict(pipeline_result)
    next_result["metadata"] = sanitized
    return next_result


def _source_hard_facts_need_refresh(source_hard_facts: object, source_text: str) -> bool:
    if not isinstance(source_hard_facts, dict):
        return False

    sanitized = _sanitize_source_hard_facts(source_hard_facts, source_text)
    original_facts = _hard_facts(source_hard_facts)
    sanitized_facts = _hard_facts(sanitized)
    for field_name in ("dates", "deadlines", "materials"):
        if len(_list_of_dicts(sanitized_facts.get(field_name))) < len(_list_of_dicts(original_facts.get(field_name))):
            return True
    return False


def _sanitize_metadata_for_source_text(metadata: dict[str, Any], source_text: str) -> dict[str, Any]:
    sanitized = dict(metadata)
    summary_ko = _optional_str(metadata.get("summary_ko"))
    sanitized["summary_ko"] = (
        None if _looks_like_non_korean_canonical_text(summary_ko) else summary_ko
    )
    sanitized["actions_required"] = [
        value
        for value in _values(metadata.get("actions_required"))
        if not _looks_like_non_korean_canonical_text(value)
    ]
    for field_name in ("important_dates", "deadlines"):
        sanitized[field_name] = [
            value
            for value in _values(metadata.get(field_name))
            if not _looks_like_admin_or_footer_date_value(value, source_text)
        ]

    for section_name in ("card_sections_ko", "card_sections_target_language", "card_sections"):
        section_value = metadata.get(section_name)
        if isinstance(section_value, dict):
            sanitized[section_name] = _sanitize_card_sections_for_source_text(
                section_value,
                source_text,
                canonical=section_name == "card_sections_ko" or (
                    section_name == "card_sections"
                    and _optional_str(metadata.get("target_language")) == "ko"
                ),
            )
    return sanitized


def _sanitize_card_sections_for_source_text(
    card_sections: dict[str, Any],
    source_text: str,
    *,
    canonical: bool = False,
) -> dict[str, Any]:
    sanitized_sections: dict[str, Any] = {}
    for section_name, section_value in card_sections.items():
        if not isinstance(section_value, dict):
            sanitized_sections[section_name] = section_value
            continue
        raw_items = section_value.get("items")
        if not isinstance(raw_items, list):
            sanitized_sections[section_name] = dict(section_value)
            continue
        sanitized_items = [
            item
            for item in raw_items
            if not _card_item_looks_like_admin_or_footer_date(item, source_text)
            and not (canonical and _card_item_looks_like_non_korean_canonical(item))
        ]
        next_section = dict(section_value)
        next_section["items"] = sanitized_items
        sanitized_sections[section_name] = next_section
    return sanitized_sections


def _card_item_looks_like_admin_or_footer_date(item: object, source_text: str) -> bool:
    if isinstance(item, str):
        text = item
        hint = None
    elif isinstance(item, dict):
        text = _optional_str(item.get("text"))
        hint = _optional_str(item.get("hint"))
    else:
        return False

    combined = " ".join(part for part in (text, hint) if part)
    if not combined:
        return False

    dates = _infer_iso_dates_from_raw_text(combined)
    if not dates:
        return False

    action_or_schedule_cues = ("신청", "제출", "마감", "행사", "설명회", "일정", "기간", "시간", "장소", "참여", "운영", "실시")
    if any(cue in combined for cue in action_or_schedule_cues):
        return False

    return all(_looks_like_admin_or_footer_date_value(date, source_text) for date in dates)


def _card_item_looks_like_non_korean_canonical(item: object) -> bool:
    if isinstance(item, str):
        text = item
        hint = None
    elif isinstance(item, dict):
        text = _optional_str(item.get("text"))
        hint = _optional_str(item.get("hint"))
    else:
        return False

    text_is_bad = _looks_like_non_korean_canonical_text(text)
    hint_is_bad = _looks_like_non_korean_canonical_text(hint)
    return text_is_bad or hint_is_bad


def _sanitize_source_hard_facts(source_hard_facts: object, source_text: str) -> dict[str, Any]:
    if not isinstance(source_hard_facts, dict):
        return {}

    hard_facts = _hard_facts(source_hard_facts)
    sanitized_hard_facts = dict(hard_facts)

    dates = [
        item
        for item in _list_of_dicts(hard_facts.get("dates"))
        if not _looks_like_admin_or_footer_date(item, source_text)
    ]
    deadlines = [
        item
        for item in _list_of_dicts(hard_facts.get("deadlines"))
        if not _looks_like_admin_or_footer_date(item, source_text)
    ]
    materials = [
        item
        for item in _list_of_dicts(hard_facts.get("materials"))
        if not _looks_like_prohibited_material(item, source_text)
    ]
    submissions = _sanitize_canonical_source_fact_items(hard_facts.get("submissions"))
    actions_required = _sanitize_canonical_source_fact_items(hard_facts.get("actions_required"))

    sanitized_hard_facts["dates"] = dates
    sanitized_hard_facts["deadlines"] = deadlines
    sanitized_hard_facts["materials"] = materials
    sanitized_hard_facts["submissions"] = submissions
    sanitized_hard_facts["actions_required"] = actions_required

    sanitized = dict(source_hard_facts)
    sanitized["hard_facts"] = sanitized_hard_facts
    return sanitized


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
        optional = _optional_str(text)
        if optional:
            values.append(optional)
    return _dedupe(values)


def _canonical_metadata_available(metadata: dict[str, Any]) -> bool:
    if isinstance(metadata.get("card_sections_ko"), dict):
        return True
    target_language = _optional_str(metadata.get("target_language"))
    return not target_language or target_language == "ko"


def _canonical_metadata_values(metadata: dict[str, Any], field_name: str) -> list[str]:
    if not _canonical_metadata_available(metadata):
        return []
    return _values(metadata.get(field_name))


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _looks_like_admin_or_footer_date(item: dict[str, Any], source_text: str) -> bool:
    raw_text = _optional_str(item.get("raw_text")) or _optional_str(item.get("normalized"))
    return _looks_like_admin_or_footer_date_value(raw_text, source_text)


def _looks_like_admin_or_footer_date_value(raw_text: str | None, source_text: str) -> bool:
    if not raw_text:
        return False

    compact_source = _compact_text(source_text)
    tokens = _date_search_tokens(raw_text)
    if not compact_source or not tokens:
        return False

    admin_keywords = (
        "작성일",
        "등록일",
        "등록일시",
        "게시일",
        "게시일시",
        "게시기간",
        "수정일",
        "수정일시",
        "최종수정일",
        "배부일",
        "공지일",
        "발행일",
        "업로드일",
        "업로드일시",
        "조회수",
        "댓글",
        "문의일자",
        "문서번호",
        "첨부일",
        "첨부일자",
    )
    schedule_keywords = ("행사", "실시", "운영", "참여", "검사", "시험", "등교", "하교", "방문", "체험학습", "수학여행", "캠프", "설문", "조사", "신청", "제출", "마감", "납부", "회신", "대회", "설명회", "훈련", "공연", "발표")

    saw_admin_context = False
    saw_non_admin_context = False

    for token in tokens:
        footer_pattern = re.escape(token).replace(r"\ ", r"\s*")
        if re.search(
            footer_pattern + r"(?:\s|[가-힣A-Za-z0-9·]){0,40}(?:학교장|교장|원장)\s*$",
            source_text,
            re.S,
        ):
            saw_admin_context = True

        compact_token = _compact_text(token)
        if not compact_token:
            continue
        start = 0
        while True:
            match_index = compact_source.find(compact_token, start)
            if match_index < 0:
                break

            context_start = max(0, match_index - 40)
            context_end = min(len(compact_source), match_index + len(compact_token) + 40)
            context = compact_source[context_start:context_end]
            trailing = compact_source[match_index + len(compact_token) :]

            has_admin_keyword = any(keyword in context for keyword in admin_keywords)
            has_schedule_keyword = any(keyword in context for keyword in schedule_keywords)

            footer_tail = trailing[:24]
            is_footer_signature = any(
                keyword in footer_tail for keyword in ("학교장", "교장", "원장")
            )

            if is_footer_signature or (has_admin_keyword and not has_schedule_keyword):
                saw_admin_context = True
            else:
                saw_non_admin_context = True

            start = match_index + len(compact_token)

    return saw_admin_context and not saw_non_admin_context


def _date_search_tokens(raw_text: str | None) -> list[str]:
    text = _optional_str(raw_text)
    if not text:
        return []

    tokens = [text]
    iso = _iso_date(text)
    if iso:
        year, month, day = iso.split("-")
        tokens.extend(
            [
                f"{year}-{month}-{day}",
                f"{year}.{month}.{day}.",
                f"{year}.{int(month)}.{int(day)}.",
                f"{year}년 {int(month)}월 {int(day)}일",
                f"{year}년{int(month)}월{int(day)}일",
            ]
        )
    return _dedupe([token for token in tokens if token])


def _looks_like_prohibited_material(item: dict[str, Any], source_text: str) -> bool:
    raw_text = _optional_str(item.get("raw_text")) or _optional_str(item.get("normalized"))
    if not raw_text:
        return False

    compact_source = _compact_text(source_text)
    compact_raw = _compact_text(raw_text)
    if not compact_source or not compact_raw:
        return False

    match_index = compact_source.find(compact_raw)
    if match_index < 0:
        return False

    context_start = max(0, match_index - 60)
    context_end = min(len(compact_source), match_index + len(compact_raw) + 60)
    context = compact_source[context_start:context_end]
    prohibited_keywords = (
        "금지물품",
        "반입금지",
        "소지금지",
        "소지불가",
        "지참금지",
        "가져오지마세요",
        "소지또는사용할수없는물품",
        "사용할수없는물품",
        "소지하여서는안된다",
        "위험물품",
    )
    return any(keyword in context for keyword in prohibited_keywords)


def _compact_text(value: str | None) -> str:
    text = _optional_str(value)
    if not text:
        return ""
    return re.sub(r"\s+", "", text)


def _looks_like_non_korean_canonical_text(value: str | None) -> bool:
    text = _optional_str(value)
    if not text:
        return False

    if re.search(r"[가-힣]", text):
        return False

    if text.startswith(("http://", "https://", "www.")):
        return False

    # Neutral machine-readable values such as dates, times, ranges, fees, or URLs are allowed.
    if re.fullmatch(r"[\d\s:/~.,()\-+%#]+", text):
        return False

    # Pure Latin text in canonical Korean slots is suspicious and should not drive ko card generation.
    return bool(re.search(r"[A-Za-z]", text))


def _looks_like_non_korean_canonical_fact(item: dict[str, Any]) -> bool:
    for key in ("normalized", "value", "text", "raw_text", "name"):
        if _looks_like_non_korean_canonical_text(_optional_str(item.get(key))):
            return True
    return False


def _sanitize_canonical_source_fact_items(value: object) -> list[object]:
    if not isinstance(value, list):
        return []

    sanitized: list[object] = []
    for item in value:
        if isinstance(item, dict):
            if not _looks_like_non_korean_canonical_fact(item):
                sanitized.append(item)
            continue
        text = _optional_str(item)
        if text and not _looks_like_non_korean_canonical_text(text):
            sanitized.append(text)
    return sanitized


def _first_value(value: object) -> str | None:
    values = _values(value)
    if values:
        return values[0]
    if isinstance(value, (list, dict, tuple, set)):
        return None
    return _optional_str(value)


def _metadata_card_section(metadata: dict[str, Any], section_name: str) -> dict[str, Any] | None:
    card_sections = _canonical_card_sections(metadata)
    if not isinstance(card_sections, dict):
        return None
    section = card_sections.get(section_name)
    return section if isinstance(section, dict) else None


def _canonical_card_sections(metadata: dict[str, Any]) -> dict[str, Any] | None:
    sections = metadata.get("card_sections_ko")
    if isinstance(sections, dict):
        return sections

    target_language = _optional_str(metadata.get("target_language"))
    legacy_sections = metadata.get("card_sections")
    if target_language == "ko" and isinstance(legacy_sections, dict):
        return legacy_sections
    return None


def _translated_card_sections(
    metadata: dict[str, Any],
    pipeline_result: dict[str, Any],
    *,
    target_language: str | None = None,
) -> dict[str, Any] | None:
    sections = metadata.get("card_sections_target_language")
    if isinstance(sections, dict):
        return sections

    target_language = (
        _optional_str(target_language)
        or _optional_str(pipeline_result.get("target_language"))
        or _optional_str(metadata.get("target_language"))
    )
    legacy_sections = metadata.get("card_sections")
    if target_language and target_language != "ko" and isinstance(legacy_sections, dict):
        return legacy_sections
    return None


def _metadata_card_items(metadata: dict[str, Any], section_name: str) -> list[dict[str, str]]:
    section = _metadata_card_section(metadata, section_name)
    if not section:
        return []

    raw_items = section.get("items")
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, str]] = []
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            text = _optional_str(raw_item)
            if text:
                items.append({"text": text})
            continue
        if not isinstance(raw_item, dict):
            continue
        text = _optional_str(raw_item.get("text"))
        if not text:
            continue
        item = {"text": text}
        hint = _optional_str(raw_item.get("hint"))
        if hint:
            item["hint"] = hint
        items.append(item)
    return items


def _metadata_card_item_texts(metadata: dict[str, Any], section_name: str) -> list[str]:
    return _dedupe([
        text
        for item in _metadata_card_items(metadata, section_name)
        for text in [_optional_str(item.get("text"))]
        if text
    ])


def _metadata_card_section_dates(metadata: dict[str, Any], section_name: str) -> list[str]:
    values: list[str] = []
    for item in _metadata_card_items(metadata, section_name):
        values.extend(_infer_iso_dates_from_raw_text(str(item.get("text", ""))))
        values.extend(_infer_iso_dates_from_raw_text(str(item.get("hint", ""))))
    return _dedupe(values)


def _metadata_card_locations(metadata: dict[str, Any], section_name: str) -> list[str]:
    locations: list[str] = []
    for item in _metadata_card_items(metadata, section_name):
        for key in ("text", "hint"):
            text = _optional_str(item.get(key))
            if not text:
                continue
            if text.startswith("장소:"):
                location = _optional_str(text.split(":", 1)[1])
                if location:
                    locations.append(location)
    return _dedupe(locations)


def _translated_metadata_card_locations(
    metadata: dict[str, Any],
    pipeline_result: dict[str, Any],
    section_name: str,
    *,
    target_language: str,
) -> list[str]:
    card_sections = _translated_card_sections(metadata, pipeline_result, target_language=target_language)
    if not isinstance(card_sections, dict):
        return []
    section = card_sections.get(section_name)
    if not isinstance(section, dict):
        return []

    raw_items = section.get("items")
    if not isinstance(raw_items, list):
        return []

    prefixes = (
        "Location:",
        "location:",
        "Место:",
        "место:",
        "المكان:",
    )
    locations: list[str] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        for key in ("text", "hint"):
            text = _optional_str(raw_item.get(key))
            if not text:
                continue
            for prefix in prefixes:
                if text.startswith(prefix):
                    location = _optional_str(text[len(prefix):])
                    if location:
                        locations.append(location)
                    break
    return _dedupe(locations)


def _normalized_iso_dates(value: object) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    dates: list[str] = []
    for item in raw:
        normalized: str | None = None
        raw_text: str | None = None
        if isinstance(item, dict):
            normalized = _optional_str(item.get("normalized")) or _optional_str(item.get("value"))
            raw_text = (
                _optional_str(item.get("raw_text"))
                or _optional_str(item.get("text"))
                or _optional_str(item.get("date"))
            )
        else:
            normalized = _optional_str(item)
            raw_text = normalized

        candidates = _iso_dates_from_value(normalized)
        if not candidates and raw_text:
            candidates = _infer_iso_dates_from_raw_text(raw_text)
        dates.extend(candidates)
    return _dedupe(dates)


def _canonical_metadata_iso_dates(metadata: dict[str, Any], field_name: str) -> list[str]:
    if not _canonical_metadata_available(metadata):
        return []
    return _normalized_iso_dates(metadata.get(field_name))


def _iso_dates_from_value(value: str | None) -> list[str]:
    normalized = _optional_str(value)
    if not normalized:
        return []
    exact = _iso_date(normalized)
    if exact:
        return [exact]

    matches = re.findall(r"\d{4}-\d{2}-\d{2}", normalized)
    return _dedupe([match for match in matches if _iso_date(match)])


def _infer_iso_dates_from_raw_text(raw_text: str) -> list[str]:
    text = _optional_str(raw_text)
    if not text:
        return []

    inferred: list[str] = []
    month_day_patterns = [
        re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
        re.compile(r"(?<!\d)(\d{1,2})\s*[./]\s*(\d{1,2})(?:[./]|$)"),
        re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)"),
    ]

    for pattern in month_day_patterns:
        for match in pattern.finditer(text):
            month = int(match.group(1))
            day = int(match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                inferred.append(f"{DEFAULT_YEARLESS_NOTICE_YEAR}-{month:02d}-{day:02d}")

    return _dedupe([iso for iso in inferred if _iso_date(iso)])


def _join_compact(values: list[str]) -> str:
    return " · ".join(value for value in values if value)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _iso_date(value: str) -> str | None:
    text = value.strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def _parse_meal_label_source_text(source_text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("# "):
            continue
        if not line.startswith("[["):
            continue
        marker_end = line.find("]]")
        if marker_end <= 2:
            continue
        item_id = line[2:marker_end].strip()
        text = line[marker_end + 2 :].strip()
        if item_id and text:
            items.append({"id": item_id, "text": text})
    return items


def get_notice_service() -> NoticeService:
    return NoticeService()
