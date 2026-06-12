import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.job_queue_service import JobQueueService
from app.services.notice_service import NoticeService, get_notice_service

router = APIRouter()
LOGGER = logging.getLogger(__name__)

# 같은 공지+언어 번역 잡이 완료된 직후에는 재등록을 막는다. 폴백 저장 등으로
# 카드가 비어 있으면 앱이 열릴 때마다 풀 재번역을 또 시키는 루프가 생기는데,
# 이 쿨다운이 그 반복 간격의 하한이 된다. (원문 명시 수동 호출은 예외)
TRANSLATION_RETRY_COOLDOWN_SECONDS = 600


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
    normalized_target_language = payload.target_language.strip().lower()
    if not normalized_target_language or normalized_target_language == "ko":
        try:
            return await service.translate_notice(
                notice_id=notice_id,
                target_language="ko",
                source_text=payload.source_text,
                approved_ingredient_dictionary=payload.approved_ingredient_dictionary,
                approved_ingredient_dictionary_target=payload.approved_ingredient_dictionary_target,
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    if payload.background:
        key = _background_translation_task_key(
            notice_id=notice_id,
            target_language=payload.target_language,
        )
        queue = JobQueueService()
        if payload.source_text is None and queue.completed_recently(
            job_key=key,
            within_seconds=TRANSLATION_RETRY_COOLDOWN_SECONDS,
        ):
            LOGGER.info(
                "translation re-enqueue blocked by cooldown: notice_id=%s target_language=%s",
                notice_id,
                payload.target_language,
            )
            return JSONResponse(
                {
                    "ok": True,
                    "accepted": False,
                    "cooldown": True,
                    "already_running": False,
                    "job_id": None,
                    "notice_id": notice_id,
                    "target_language": payload.target_language,
                },
                status_code=status.HTTP_202_ACCEPTED,
            )
        enqueue = queue.enqueue(
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


@router.get("/{notice_id}/translate/status")
async def translation_job_status(notice_id: str, target_language: str) -> dict[str, object]:
    """해당 공지+언어 번역 잡의 최근 상태 — 프론트가 '준비중/실패' 배너를 가르는 데 쓴다."""
    normalized = (target_language or "").strip().lower()
    if not normalized or normalized == "ko":
        return {"ok": True, "job_status": "none"}
    job = JobQueueService().latest_job(
        job_key=_background_translation_task_key(
            notice_id=notice_id,
            target_language=normalized,
        )
    )
    if not job:
        return {"ok": True, "job_status": "none"}
    return {
        "ok": True,
        "job_status": str(job.get("status") or "none"),
        "attempts": job.get("attempts"),
        "max_attempts": job.get("max_attempts"),
    }


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
