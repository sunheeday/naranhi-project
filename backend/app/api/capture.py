from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from app.services.capture_ocr_service import CaptureOcrService, get_capture_ocr_service
from app.services.notice_service import NoticeService, get_notice_service

router = APIRouter()


@router.post("/ocr")
async def extract_camera_notice_text(
    request: Request,
    file: Annotated[UploadFile | None, File(description="Camera notice image upload.")] = None,
    target_language: Annotated[
        str | None,
        Query(min_length=2, max_length=16, description="Optional translation target language."),
    ] = None,
    service: CaptureOcrService = Depends(get_capture_ocr_service),
    notice_service: NoticeService = Depends(get_notice_service),
) -> dict[str, object]:
    """Extract notice text from either multipart image upload or raw image bytes."""
    if file is not None:
        data = await file.read()
        mime_type = file.content_type
        source_name = file.filename or "camera_notice"
    else:
        data = await request.body()
        mime_type = request.headers.get("content-type")
        source_name = "camera_notice"

    try:
        ocr = await service.extract_text(
            data=data,
            mime_type=mime_type,
            source_name=source_name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    response: dict[str, object] = {
        "ok": True,
        "extracted_text": ocr.extracted_text,
        "mime_type": ocr.mime_type,
        "ocr": {
            "confidence": ocr.confidence,
            "is_readable": ocr.is_readable,
            "warnings": ocr.warnings,
            "detected_layout": ocr.detected_layout,
        },
    }

    if target_language:
        try:
            response["translation"] = await notice_service.translate_text(
                source_text=ocr.extracted_text,
                target_language=target_language,
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    return response
