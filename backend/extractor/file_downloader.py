from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import httpx

from extractor.detail_fetcher import DEFAULT_HEADERS
from extractor.file_type_detector import detect_file_type
from extractor.http_security import assert_public_url, tls_metadata, tls_verify_for_url
from extractor.models import AttachmentRef, DownloadedFile, InlineImageRef


REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


async def download_attachment(
    ref: AttachmentRef | InlineImageRef,
    *,
    output_dir: Path,
    max_file_size_mb: int,
    referer: str | None = None,
) -> DownloadedFile:
    output_dir.mkdir(parents=True, exist_ok=True)
    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer

    max_bytes = max_file_size_mb * 1024 * 1024
    current_url = ref.url
    redirect_count = 0

    while True:
        assert_public_url(current_url)
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=False,
            headers=headers,
            verify=tls_verify_for_url(current_url),
        ) as client:
            async with client.stream("GET", current_url) as response:
                if response.status_code in REDIRECT_STATUS_CODES and response.headers.get("location"):
                    redirect_count += 1
                    if redirect_count > 8:
                        raise RuntimeError("download_redirect_loop")
                    current_url = urljoin(str(response.url), response.headers["location"])
                    continue

                response.raise_for_status()
                final_url = str(response.url)
                assert_public_url(final_url)
                content_length = _content_length(response.headers)
                if content_length is not None and content_length > max_bytes:
                    raise RuntimeError(f"file too large by content-length: {content_length} bytes > {max_bytes} bytes")

                filename = _filename_from_response(response, getattr(ref, "filename", "") or getattr(ref, "alt", ""))
                path = _ensure_within_directory(_unique_path(output_dir / filename), output_dir)
                size_bytes = 0
                try:
                    with path.open("wb") as fp:
                        async for chunk in response.aiter_bytes():
                            size_bytes += len(chunk)
                            if size_bytes > max_bytes:
                                raise RuntimeError(f"file too large while streaming: {size_bytes} bytes > {max_bytes} bytes")
                            fp.write(chunk)
                except Exception:
                    if path.exists():
                        path.unlink()
                    raise

                content_type = response.headers.get("content-type", "")
                sniffed_file_type = detect_file_type(path, filename, content_type)
                return DownloadedFile(
                    url=final_url,
                    path=path,
                    filename=filename,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    kind_hint="inline_image" if isinstance(ref, InlineImageRef) else "attachment",
                    metadata={
                        **tls_metadata(final_url),
                        "final_url": final_url,
                        "content_length": content_length,
                        "sniffed_file_type": sniffed_file_type,
                        "redirect_count": redirect_count,
                    },
                )


def _filename_from_response(response: httpx.Response, fallback: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    filename = _parse_content_disposition_filename(disposition)
    if filename:
        return _safe_filename(filename)
    if fallback:
        return _safe_filename(fallback)
    path_name = Path(str(response.url.path)).name
    return _safe_filename(unquote(path_name) or "attachment")


def _parse_content_disposition_filename(value: str) -> str:
    star = re.search(r"""filename\*\s*=\s*([^']*)''([^;]+)""", value, re.IGNORECASE)
    if star:
        encoding = star.group(1) or "utf-8"
        try:
            return unquote(star.group(2), encoding=encoding)
        except LookupError:
            return unquote(star.group(2))
    normal = re.search(r"""filename\s*=\s*"?([^";]+)"?""", value, re.IGNORECASE)
    if normal:
        return _decode_header_filename(normal.group(1).strip())
    return ""


def _decode_header_filename(value: str) -> str:
    decoded = unquote(value)
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            candidate = decoded.encode("latin-1").decode(encoding)
        except UnicodeError:
            continue
        if any("가" <= char <= "힣" for char in candidate):
            return candidate
    return decoded


def _content_length(headers: httpx.Headers) -> int | None:
    value = headers.get("content-length")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 1000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"cannot allocate output path for {path}")


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[\x00-\x1f\\/:*?"<>|\u2044\u2215]+', "_", value)
    cleaned = cleaned.replace("..", "_").strip(" .")
    return cleaned[:200] or "attachment"


def _ensure_within_directory(path: Path, directory: Path) -> Path:
    resolved_directory = directory.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_directory and resolved_directory not in resolved_path.parents:
        raise RuntimeError(f"unsafe download path outside output directory: {path}")
    return resolved_path
