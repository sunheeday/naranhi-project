from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.notice_service import NoticeService, get_notice_service

router = APIRouter()


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
    pass


class TextTranslateRequest(BaseModel):
    source_text: str = Field(min_length=1)
    target_language: str = Field(default="en", min_length=2, max_length=16)
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
    try:
        return await service.translate_notice(
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
