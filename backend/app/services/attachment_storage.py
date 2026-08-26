"""공지 첨부파일을 Supabase Storage(비공개 버킷)에 업로드한다.

추출 파이프라인이 첨부를 다운로드한 '그 바이트 그대로'를 우리 버킷에 올려, 프론트가 학교 서버가
아니라 우리 사본을 미리보기/다운로드하게 한다. 업로드 실패는 공지 처리를 막지 않는다(None 반환).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any

from app.core.supabase import get_supabase_client
from extractor.http_security import sanitize_error
from extractor.quality import file_sha256

LOGGER = logging.getLogger(__name__)

BUCKET = "notice-attachments"
BUCKET_PUBLIC = False
UPLOAD_RESULT_KEYS = ("storage_path",)
_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def _object_key(notice_id: str, path_on_disk: Any, filename: str) -> str:
    """Storage 오브젝트 키(ASCII 전용 — Supabase 는 키에 비ASCII 불가).

    파일 내용 해시 기반이라 같은 파일(중복 첨부)은 같은 키 → 1번만 저장(업서트). 표시용
    한글 파일명은 sources[].filename 으로 따로 보존하고 다운로드 시 ?download= 로 전달한다.
    """
    match = _EXT_RE.search((filename or "").strip())
    ext = match.group(0).lower() if match else ""
    digest = file_sha256(path_on_disk)[:16] or "file"
    return f"{notice_id}/{digest}{ext}"


def ensure_bucket() -> None:
    """버킷이 없으면 비공개로 만든다(로컬/마이그레이션 미적용 환경 대비, 멱등)."""
    client = get_supabase_client()
    try:
        existing = {b.name if hasattr(b, "name") else b.get("name") for b in client.storage.list_buckets()}
    except Exception:  # noqa: BLE001
        existing = set()
    if BUCKET in existing:
        return
    try:
        client.storage.create_bucket(BUCKET, options={"public": BUCKET_PUBLIC})
    except Exception as exc:  # noqa: BLE001 - 이미 있으면(409) 무시.
        LOGGER.info("create_bucket skipped: %s", sanitize_error(exc))


def _upload_sync(*, notice_id: str, path_on_disk: Any, filename: str, content_type: str) -> dict[str, str]:
    client = get_supabase_client()
    data = path_on_disk.read_bytes()
    object_path = _object_key(notice_id, path_on_disk, filename)
    storage = client.storage.from_(BUCKET)
    storage.upload(
        object_path,
        data,
        {"content-type": content_type or "application/octet-stream", "upsert": "true"},
    )
    # public_url 은 저장하지 않는다. 읽는 시점에 서명 URL 로 발급한다(Task 7).
    return {"storage_path": object_path}


def _upload_bytes_sync(*, notice_id: str, name: str, data: bytes, content_type: str, ext: str) -> dict[str, str]:
    client = get_supabase_client()
    digest = hashlib.sha256(data).hexdigest()[:16]
    object_path = f"{notice_id}/{name}-{digest}{ext}"
    storage = client.storage.from_(BUCKET)
    storage.upload(
        object_path,
        data,
        {"content-type": content_type or "application/octet-stream", "upsert": "true"},
    )
    return {"storage_path": object_path}


async def upload_bytes(
    *, notice_id: str, name: str, data: bytes, content_type: str = "image/png", ext: str = ".png"
) -> dict[str, str] | None:
    """생성한 바이트(예: 본문 사진들을 합친 PNG)를 비공개 버킷에 업로드. 실패 시 None."""
    global _bucket_ready
    try:
        if not _bucket_ready:
            await asyncio.to_thread(ensure_bucket)
            _bucket_ready = True
        return await asyncio.to_thread(
            _upload_bytes_sync, notice_id=notice_id, name=name, data=data, content_type=content_type, ext=ext
        )
    except Exception as exc:  # noqa: BLE001 - 업로드 실패가 공지 처리를 막지 않게.
        LOGGER.warning("bytes upload failed: notice_id=%s name=%s error=%s", notice_id, name, sanitize_error(exc))
        return None


_bucket_ready = False


async def upload_attachment(
    *, notice_id: str, source_id: str, path_on_disk: Any, filename: str, content_type: str
) -> dict[str, str] | None:
    """첨부 파일을 비공개 버킷에 업로드하고 {storage_path} 반환(실패 시 None).

    Supabase 클라이언트는 동기라 to_thread 로 이벤트루프를 막지 않는다.
    """
    global _bucket_ready
    try:
        if not _bucket_ready:  # 마이그레이션 미적용 환경(로컬)에서도 동작하도록 1회 보장.
            await asyncio.to_thread(ensure_bucket)
            _bucket_ready = True
        return await asyncio.to_thread(
            _upload_sync,
            notice_id=notice_id,
            path_on_disk=path_on_disk,
            filename=filename,
            content_type=content_type,
        )
    except Exception as exc:  # noqa: BLE001 - 업로드 실패가 공지 처리를 막지 않게.
        LOGGER.warning(
            "attachment upload failed: notice_id=%s source_id=%s error=%s",
            notice_id,
            source_id,
            sanitize_error(exc),
        )
        return None
