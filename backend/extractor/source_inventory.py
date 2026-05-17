from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from extractor.attachment_finder import find_attachments
from extractor.html_text_extractor import extract_html_text, extract_inline_images
from extractor.models import DownloadedFile, FetchedDetail, SourceCandidate


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def build_source_inventory(fetched: FetchedDetail) -> list[SourceCandidate]:
    if not fetched.is_html:
        filename = _filename_from_url(fetched.final_url)
        return [
            SourceCandidate(
                source_id="direct_file_1",
                source_type="direct_file",
                origin_url=fetched.final_url,
                filename=filename,
                kind_hint=_kind_from_filename(filename),
                order_index=1,
            )
        ]

    html = fetched.text
    sources: list[SourceCandidate] = []
    html_text = extract_html_text(html)
    sources.append(
        SourceCandidate(
            source_id="html_body_1",
            source_type="html_body",
            origin_url=fetched.final_url,
            filename="",
            kind_hint="html",
            order_index=0,
            source_text=html_text,
        )
    )

    counters: dict[str, int] = {}
    for image_ref in extract_inline_images(fetched.final_url, html):
        source_type = "inline_image"
        source_id = _next_source_id(counters, source_type)
        sources.append(
            SourceCandidate(
                source_id=source_id,
                source_type=source_type,
                origin_url=image_ref.url,
                filename=_filename_from_url(image_ref.url),
                kind_hint="image",
                order_index=len(sources),
                source_text=image_ref.source_text,
                inline_ref=image_ref,
            )
        )

    for attachment_ref in find_attachments(fetched.final_url, html):
        source_type = _attachment_source_type(attachment_ref.filename, attachment_ref.url)
        source_id = _next_source_id(counters, source_type)
        sources.append(
            SourceCandidate(
                source_id=source_id,
                source_type=source_type,
                origin_url=attachment_ref.url,
                filename=attachment_ref.filename,
                kind_hint=attachment_ref.kind_hint,
                order_index=len(sources),
                source_text=attachment_ref.source_text,
                attachment_ref=attachment_ref,
            )
        )

    return _dedupe_sources(sources)


def attach_direct_file(candidate: SourceCandidate, downloaded: DownloadedFile) -> SourceCandidate:
    candidate.direct_file = downloaded
    candidate.filename = downloaded.filename
    candidate.kind_hint = _kind_from_filename(downloaded.filename)
    return candidate


def _attachment_source_type(filename: str, url: str) -> str:
    suffix = Path(filename or _filename_from_url(url)).suffix.lower()
    if suffix == ".pdf":
        return "attachment_pdf"
    if suffix == ".hwp":
        return "attachment_hwp"
    if suffix == ".hwpx":
        return "attachment_hwpx"
    if suffix in IMAGE_EXTS:
        return "attachment_image"
    return "attachment"


def _kind_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".hwp":
        return "hwp"
    if suffix == ".hwpx":
        return "hwpx"
    if suffix in IMAGE_EXTS:
        return "image"
    if suffix in {".html", ".htm"}:
        return "html"
    return "attachment"


def _filename_from_url(url: str) -> str:
    name = unquote(Path(urlparse(url).path).name)
    return name or "direct-file"


def _next_source_id(counters: dict[str, int], source_type: str) -> str:
    counters[source_type] = counters.get(source_type, 0) + 1
    return f"{source_type}_{counters[source_type]}"


def _dedupe_sources(sources: list[SourceCandidate]) -> list[SourceCandidate]:
    seen: set[tuple[str, str]] = set()
    deduped: list[SourceCandidate] = []
    for source in sources:
        key = (source.source_type, source.origin_url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped
