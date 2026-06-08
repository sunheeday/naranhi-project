import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.job_queue_service import JobQueueService
from app.services.notice_service import NoticeService, get_notice_service

router = APIRouter()
LOGGER = logging.getLogger(__name__)


class NoticeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    school_id: str = Field(min_length=1)
    raw_text: str | None = None
    source_url: str | None = None


class NoticeAnalyzeRequest(BaseModel):
    target_language: str = Field(default="en", min_length=2, max_length=16)
    source_text: str | None = None
    approved_ingredient_dictionary: list[dict[str, object]] = Field(default_factory=list)
    approved_ingredient_dictionary_target: list[dict[str, object]] = Field(default_factory=list)


class NoticeTranslateRequest(NoticeAnalyzeRequest):
    background: bool = False


class TextTranslateRequest(BaseModel):
    source_text: str = Field(min_length=1)
    target_language: str = Field(default="en", min_length=2, max_length=16)
    translation_kind: str | None = None
    approved_ingredient_dictionary: list[dict[str, object]] = Field(default_factory=list)
    approved_ingredient_dictionary_target: list[dict[str, object]] = Field(default_factory=list)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_notice(
    payload: NoticeCreateRequest,
    service: NoticeService = Depends(get_notice_service),
) -> dict[str, object]:
    try:
        return await service.create_notice(payload.model_dump())
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/{notice_id}/analyze")
async def analyze_notice(
    notice_id: str,
    payload: NoticeAnalyzeRequest,
    service: NoticeService = Depends(get_notice_service),
) -> dict[str, object]:
    return await service.analyze_notice(
        notice_id=notice_id,
        target_language=payload.target_language,
        source_text=payload.source_text,
        approved_ingredient_dictionary=payload.approved_ingredient_dictionary,
        approved_ingredient_dictionary_target=payload.approved_ingredient_dictionary_target,
    )


@router.post("/translate-text")
async def translate_text(
    payload: TextTranslateRequest,
    service: NoticeService = Depends(get_notice_service),
) -> dict[str, object]:
    try:
        return await service.translate_text(
            source_text=payload.source_text,
            target_language=payload.target_language,
            translation_kind=payload.translation_kind,
            approved_ingredient_dictionary=payload.approved_ingredient_dictionary,
            approved_ingredient_dictionary_target=payload.approved_ingredient_dictionary_target,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/{notice_id}/translate")
async def translate_notice(
    notice_id: str,
    payload: NoticeTranslateRequest,
    service: NoticeService = Depends(get_notice_service),
) -> dict[str, object]:
    if payload.background:
        key = _background_translation_task_key(
            notice_id=notice_id,
            target_language=payload.target_language,
        )
        enqueue = JobQueueService().enqueue(
            job_type="notice_translation",
            job_key=key,
            payload={
                "notice_id": notice_id,
                "target_language": payload.target_language,
                "source_text": payload.source_text,
                "approved_ingredient_dictionary": payload.approved_ingredient_dictionary,
                "approved_ingredient_dictionary_target": payload.approved_ingredient_dictionary_target,
            },
        )
        return JSONResponse(
            {
                "ok": True,
                "accepted": True,
                "already_running": enqueue.already_running,
                "job_id": enqueue.job_id,
                "notice_id": notice_id,
                "target_language": payload.target_language,
            },
            status_code=status.HTTP_202_ACCEPTED,
        )

    try:
        result = await service.translate_notice(
            notice_id=notice_id,
            target_language=payload.target_language,
            source_text=payload.source_text,
            approved_ingredient_dictionary=payload.approved_ingredient_dictionary,
            approved_ingredient_dictionary_target=payload.approved_ingredient_dictionary_target,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    asyncio.create_task(
        _translate_sources_for_locale_background(
            service=service,
            notice_id=notice_id,
            target_language=payload.target_language,
        )
    )

    return result


def _background_translation_task_key(*, notice_id: str, target_language: str) -> str:
    return f"{notice_id}:{target_language.strip().lower()}"


async def _translate_sources_for_locale_background(
    *,
    service: NoticeService,
    notice_id: str,
    target_language: str,
) -> None:
    try:
        from app.services.content_extraction_service import translate_sources_for_locale

        await translate_sources_for_locale(service, notice_id, target_language)
    except Exception as exc:  # noqa: BLE001 - background source translation is best effort.
        LOGGER.warning(
            "background source translation failed: notice_id=%s target_language=%s error=%s",
            notice_id,
            target_language,
            exc,
        )
