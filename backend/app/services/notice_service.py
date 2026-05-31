from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.crawler.detail_content_extractor import fetch_notice_detail_content
from app.translation.gemini_client import GeminiJsonClient
from app.translation.orchestrator import TranslationPipeline, TranslationPipelineInput


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
        settings = get_settings()
        if not settings.supabase_configured:
            raise RuntimeError("Supabase is not configured.")
        if not settings.gemini_configured or not settings.gemini_key_material:
            raise RuntimeError("GEMINI_API_KEY 또는 GEMINI_API_KEYS가 필요합니다.")

        supabase = get_supabase_client()
        notice_result = (
            supabase.table("notices")
            .select(
                "id,school_id,title,original_text,extracted_content,status,"
                "detail_url,source_post_uid,crawl_result"
            )
            .eq("id", notice_id)
            .single()
            .execute()
        )
        notice = notice_result.data
        if not notice:
            raise RuntimeError("Notice was not found.")

        try:
            notice = await self._ensure_notice_text(
                supabase=supabase,
                notice=notice,
                timeout_seconds=settings.crawler_timeout_seconds,
            )
            resolved_source_text = self._resolve_notice_source_text(notice, source_text)
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
            "status": "admin_review_required",
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
                "required": True,
                "reason": "quota_best_effort_fallback",
                "priority": "high",
            },
            "metadata": {
                "title": fallback_title,
                "fallback_mode": "quota_best_effort",
            },
            "raw_steps": {
                "best_effort": fallback,
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
        metadata = dict(pipeline_result.get("metadata") or {})
        if source_metadata:
            metadata["notice_context"] = source_metadata
        admin_review = pipeline_result.get("admin_review") or {}
        validation = pipeline_result.get("validation") or {}
        status = pipeline_result.get("status")
        validation_status = (
            "human_review_required"
            if admin_review.get("required")
            else "passed"
            if status == "ready_to_save"
            else "failed"
        )

        row = {
            "notice_id": notice_id,
            "target_language": target_language,
            "source_language": "ko",
            "source_text": pipeline_result.get("source_text"),
            "translated_text": pipeline_result.get("final_translation"),
            "source_hard_facts": pipeline_result.get("source_hard_facts") or {},
            "target_hard_facts": pipeline_result.get("target_hard_facts") or {},
            "ingredient_identity_map": pipeline_result.get("ingredient_identity_map") or {},
            "validation": validation,
            "metadata": metadata,
            "raw_pipeline": pipeline_result.get("raw_steps") or {},
            "validation_status": validation_status,
            "requires_admin_review": bool(admin_review.get("required")),
            "admin_review_reason": admin_review.get("reason") or metadata.get("admin_review_reason"),
        }
        upsert = (
            supabase.table("notice_ai_translations")
            .upsert(row, on_conflict="notice_id,target_language")
            .execute()
        )
        cards = self._replace_notice_cards_from_pipeline(
            supabase=supabase,
            notice_id=notice_id,
            target_language=target_language,
            pipeline_result=pipeline_result,
        )
        schedules: list[dict[str, Any]] = []

        notice_patch: dict[str, Any] = {}
        if metadata.get("title"):
            notice_patch["title"] = metadata["title"]

        if notice_patch:
            supabase.table("notices").update(notice_patch).eq("id", notice_id).execute()

        return {
            "translation_row": upsert.data[0] if upsert.data else None,
            "cards": cards,
            "schedules": schedules,
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
        target_language: str,
        pipeline_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if pipeline_result.get("status") != "ready_to_save":
            return []

        cards = _build_notice_cards(
            notice_id=notice_id,
            target_language=target_language,
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
        existing_rows = _remove_target_language_from_existing_cards(
            supabase=supabase,
            rows=existing_rows,
            target_language=target_language,
        )
        if not cards:
            return []

        existing_by_slot = {
            (row.get("type"), row.get("order")): row
            for row in existing_rows
            if row.get("id")
        }

        saved: list[dict[str, Any]] = []
        inserts: list[dict[str, Any]] = []
        for card in cards:
            slot = (card["type"], card["order"])
            existing = existing_by_slot.get(slot)
            if not existing:
                inserts.append(card)
                continue

            merged_content = _merge_card_content(
                existing.get("content"),
                card["content"],
            )
            result = (
                supabase.table("notice_cards")
                .update({"content": merged_content})
                .eq("id", existing["id"])
                .execute()
            )
            saved.extend(result.data or [])

        if inserts:
            result = supabase.table("notice_cards").insert(inserts).execute()
            saved.extend(result.data or [])

        return saved


def _remove_target_language_from_existing_cards(
    *,
    supabase: Any,
    rows: list[dict[str, Any]],
    target_language: str,
) -> list[dict[str, Any]]:
    remaining: list[dict[str, Any]] = []
    for row in rows:
        content = row.get("content")
        if not isinstance(content, dict) or target_language not in content:
            remaining.append(row)
            continue

        next_content = dict(content)
        next_content.pop(target_language, None)
        if next_content:
            supabase.table("notice_cards").update({"content": next_content}).eq(
                "id",
                row["id"],
            ).execute()
            next_row = dict(row)
            next_row["content"] = next_content
            remaining.append(next_row)
        else:
            supabase.table("notice_cards").delete().eq("id", row["id"]).execute()

    return remaining


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
- 문단 구조를 유지해라.
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


def _build_notice_cards(
    *,
    notice_id: str,
    target_language: str,
    pipeline_result: dict[str, Any],
) -> list[dict[str, Any]]:
    source_facts = _hard_facts(pipeline_result.get("source_hard_facts"))
    target_facts = _hard_facts(pipeline_result.get("target_hard_facts"))
    metadata = pipeline_result.get("metadata") if isinstance(pipeline_result.get("metadata"), dict) else {}
    cards: list[dict[str, Any]] = []
    order = 0

    materials = _values(target_facts.get("materials")) or _values(source_facts.get("materials"))
    if materials:
        cards.append(
            _card_row(
                notice_id=notice_id,
                card_type="supplies",
                order=order,
                target_language=target_language,
                content={
                    "title": "준비물",
                    "items": materials,
                    "deadline": _first_value(target_facts.get("deadlines")) or _first_value(source_facts.get("deadlines")),
                },
            )
        )
        order += 1

    actions = (
        _values(target_facts.get("actions_required"))
        or _values(metadata.get("actions_required"))
        or _values(source_facts.get("actions_required"))
    )
    submissions = _values(target_facts.get("submissions")) or _values(source_facts.get("submissions"))
    action_items = [*actions, *[f"제출: {item}" for item in submissions]]
    if action_items:
        cards.append(
            _card_row(
                notice_id=notice_id,
                card_type="action",
                order=order,
                target_language=target_language,
                content={
                    "title": "해야 할 일",
                    "items": _dedupe(action_items),
                    "deadline": _first_value(target_facts.get("deadlines")) or _first_value(source_facts.get("deadlines")),
                },
            )
        )
        order += 1

    dates = _values(source_facts.get("dates"))
    target_dates = _values(target_facts.get("dates"))
    locations = _values(target_facts.get("locations")) or _values(source_facts.get("locations"))
    times = _values(target_facts.get("times")) or _values(source_facts.get("times"))
    if dates or target_dates:
        date_label = _join_compact(target_dates or dates)
        if times:
            date_label = _join_compact([date_label, _join_compact(times)])
        cards.append(
            _card_row(
                notice_id=notice_id,
                card_type="schedule",
                order=order,
                target_language=target_language,
                content={
                    "title": "일정",
                    "date": date_label,
                    "location": locations[0] if locations else None,
                    "description": _first_value(metadata.get("summary_target_language"))
                    or _first_value(pipeline_result.get("final_translation")),
                },
            )
        )

    return cards


def _card_row(
    *,
    notice_id: str,
    card_type: str,
    order: int,
    target_language: str,
    content: dict[str, Any],
) -> dict[str, Any]:
    return {
        "notice_id": notice_id,
        "type": card_type,
        "order": order,
        "content": {
            target_language: {key: value for key, value in content.items() if value not in (None, "", [])}
        },
    }


def _hard_facts(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
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
        optional = _optional_str(text)
        if optional:
            values.append(optional)
    return _dedupe(values)


def _first_value(value: object) -> str | None:
    values = _values(value)
    return values[0] if values else _optional_str(value)


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


def get_notice_service() -> NoticeService:
    return NoticeService()
