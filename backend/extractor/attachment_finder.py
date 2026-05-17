from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from extractor.models import AttachmentRef


FILE_EXT_RE = re.compile(r"\.(pdf|hwp|hwpx|png|jpe?g)(?:[?#].*)?$", re.IGNORECASE)
DOWNLOAD_TERMS = (
    "download",
    "filedown",
    "file_down",
    "filedownload",
    "atchfileid",
    "filesn",
    "homn_filedown",
    "downpost",
    "첨부",
    "다운로드",
)


def find_attachments(base_url: str, html: str) -> list[AttachmentRef]:
    soup = BeautifulSoup(html, "html.parser")
    refs: list[AttachmentRef] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a"):
        raw_candidates = []
        href = (anchor.get("href") or "").strip()
        onclick = (anchor.get("onclick") or "").strip()
        if href:
            raw_candidates.extend(_urls_from_javascript(href))
            raw_candidates.append(href)
        raw_candidates.extend(_urls_from_javascript(onclick))

        text = _clean_text(anchor.get_text(" ", strip=True))
        context = _clean_text(anchor.parent.get_text(" ", strip=True) if anchor.parent else text)
        haystack = f"{href} {onclick} {text} {context}".lower()

        for raw_url in raw_candidates:
            if not _looks_like_attachment(raw_url, haystack):
                continue
            url = urljoin(base_url, raw_url)
            if url in seen:
                continue
            seen.add(url)
            refs.append(
                AttachmentRef(
                    url=url,
                    filename=_filename_from_link(url, text),
                    source_text=context[:250],
                )
            )

    for match in _dext5_uploaded_files(html):
        url = urljoin(base_url, match["url"])
        if url in seen:
            continue
        seen.add(url)
        refs.append(
            AttachmentRef(
                url=url,
                filename=_safe_filename(match["filename"]),
                source_text=match["filename"][:250],
            )
        )

    return refs


def _looks_like_attachment(raw_url: str, haystack: str) -> bool:
    if raw_url.startswith("#") or raw_url.lower().startswith(("javascript:", "mailto:", "tel:")):
        return False
    lowered = raw_url.lower()
    if FILE_EXT_RE.search(lowered):
        return True
    return any(term in lowered or term in haystack for term in DOWNLOAD_TERMS)


def _urls_from_javascript(onclick: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"""goFileDown\s*\(\s*['"]([^'"]+)['"]\s*\)""", onclick, re.IGNORECASE):
        file_seq = match.group(1).strip()
        if file_seq:
            urls.append(f"/boardCnts/fileDown.do?fileSeq={file_seq}")

    for pattern in (
        r"""location\.href\s*=\s*['"]([^'"]+)['"]""",
        r"""(?:fileDown|fileDownload|download|fn_down|goDown)\s*\(([^)]*)\)""",
    ):
        for match in re.finditer(pattern, onclick, re.IGNORECASE):
            value = match.group(1).strip()
            if "/" in value or "?" in value:
                urls.append(value.strip("'\""))
    return urls


def _dext5_uploaded_files(html: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for match in re.finditer(r"DEXT5UPLOAD\.AddUploadedFile\((.*?)\);", html, re.DOTALL):
        args = re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1))
        if len(args) < 3:
            continue
        filename = args[1]
        url = args[2]
        if not _looks_like_attachment(url, f"{filename} {url}".lower()):
            continue
        refs.append({"filename": filename, "url": url})
    return refs


def _filename_from_link(url: str, text: str) -> str:
    text_name = text.strip()
    if FILE_EXT_RE.search(text_name):
        return _safe_filename(text_name)
    path_name = unquote(Path(urlparse(url).path).name)
    if path_name:
        return _safe_filename(path_name)
    return "attachment"


def _safe_filename(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", value).strip() or "attachment"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
