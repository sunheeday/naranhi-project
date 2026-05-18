from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse

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
    "downfile.do",
    "nttfiledownload.do",
    "csdownload.do",
    "filedown.do",
    "boardfile",
)
TEXT_ATTACHMENT_TERMS = (
    "첨부",
    "첨부파일",
    "파일첨부",
    "다운로드",
)
ATTACHMENT_ID_TERMS = ("atchfileid", "filesn", "fileseq", "file_seq", "fileid", "file_id")
NON_DOWNLOAD_PATH_TERMS = (
    "preview.do",
    "cnvrfiledown.do",
    "synapdocviewserver",
    "apple/urlfilemgt/",
    "list.do",
    "main.do",
    "info.do",
    "view.asp",
    "selectnttlist.do",
)
NON_NOTICE_ATTACHMENT_NAME_TERMS = (
    "학교통합홈페이지",
    "운영지침",
)
WEAK_FILENAME_KEYS = {
    "attachment",
    "download",
    "filedown",
    "filedown.do",
    "filedownload.do",
    "nttfiledownload.do",
}


class _SeenTracker:
    def __init__(self) -> None:
        self._urls: set[str] = set()
        self._filename_keys: set[str] = set()

    def accept(self, ref: AttachmentRef) -> bool:
        if ref.url in self._urls:
            return False
        if _ignore_attachment_filename(ref.filename):
            return False

        filename_key = _dedupe_filename_key(ref.filename)
        if filename_key and filename_key in self._filename_keys:
            return False

        self._urls.add(ref.url)
        if filename_key:
            self._filename_keys.add(filename_key)
        return True


def find_attachments(base_url: str, html: str) -> list[AttachmentRef]:
    soup = BeautifulSoup(html, "html.parser")
    refs: list[AttachmentRef] = []
    seen = _SeenTracker()

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
            if _external_non_file_download(base_url, url, raw_url, haystack):
                continue
            ref = AttachmentRef(
                url=url,
                filename=_filename_from_link(url, text),
                source_text=context[:250],
            )
            if seen.accept(ref):
                refs.append(ref)

    for match in _dext5_uploaded_files(html):
        url = urljoin(base_url, match["url"])
        ref = AttachmentRef(
            url=url,
            filename=_safe_filename(match["filename"]),
            source_text=match["filename"][:250],
        )
        if seen.accept(ref):
            refs.append(ref)

    for match in _server_file_objects(base_url, html):
        if seen.accept(match):
            refs.append(match)

    return refs


def _looks_like_attachment(raw_url: str, haystack: str) -> bool:
    if raw_url.startswith("#") or raw_url.lower().startswith(("javascript:", "mailto:", "tel:")):
        return False
    lowered = raw_url.lower()
    if _looks_like_navigation_or_preview(lowered):
        return False
    if FILE_EXT_RE.search(lowered):
        return True
    if any(term in lowered for term in DOWNLOAD_TERMS):
        return True
    has_attachment_text = any(term in haystack for term in TEXT_ATTACHMENT_TERMS)
    has_attachment_id = any(term in lowered or term in haystack for term in ATTACHMENT_ID_TERMS)
    return (has_attachment_text or FILE_EXT_RE.search(haystack)) and has_attachment_id


def _looks_like_navigation_or_preview(lowered_url: str) -> bool:
    if any(term in lowered_url for term in NON_DOWNLOAD_PATH_TERMS):
        return True
    path = urlparse(lowered_url).path
    return Path(path).name.lower() in {"download", "preview", "view", "list", "main", "info"}


def _external_non_file_download(base_url: str, url: str, raw_url: str, haystack: str) -> bool:
    base_host = urlparse(base_url).netloc.lower()
    target_host = urlparse(url).netloc.lower()
    if not target_host or target_host == base_host:
        return False
    lowered = raw_url.lower()
    if FILE_EXT_RE.search(lowered) or FILE_EXT_RE.search(haystack):
        return False
    if any(term in lowered or term in haystack for term in ATTACHMENT_ID_TERMS):
        return False
    return True


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
    for match in re.finditer(
        r"""(?:fn_egov_downFile|downFile|fileDown|fileDownload)\s*\(\s*['"]([^'"]+)['"]\s*,\s*['"]?([^'")]+)['"]?\s*\)""",
        onclick,
        re.IGNORECASE,
    ):
        atch_file_id = match.group(1).strip()
        file_sn = match.group(2).strip()
        if atch_file_id and file_sn:
            urls.append(_default_board_file_download_url(atch_file_id, file_sn))
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


def _server_file_objects(base_url: str, html: str) -> list[AttachmentRef]:
    refs: list[AttachmentRef] = []
    download_base = _download_base_from_functions(html) or _default_board_file_download_url("", "").split("?")[0]
    for fields in _iter_server_file_fields(html):
        filename = fields.get("name", "").strip()
        atch_file_id = fields.get("atchFileId", "").strip()
        file_sn = fields.get("fileSn", "0").strip() or "0"
        if not filename or not atch_file_id:
            continue
        url = _build_file_download_url(base_url, download_base, atch_file_id, file_sn)
        refs.append(
            AttachmentRef(
                url=url,
                filename=_safe_filename(filename),
                source_text=filename[:250],
            )
        )
    return refs


def _iter_server_file_fields(html: str) -> list[dict[str, str]]:
    objects: list[dict[str, str]] = []
    for match in re.finditer(
        r"""(?P<body>(?:\w+\s*\[\s*["'](?:name|size|atchFileId|fileSn|fileCn)["']\s*\]\s*=\s*["'][^"']*["']\s*;\s*)+)""",
        html,
        re.IGNORECASE,
    ):
        fields: dict[str, str] = {}
        for assignment in re.finditer(
            r"""\w+\s*\[\s*["'](?P<key>name|size|atchFileId|fileSn|fileCn)["']\s*\]\s*=\s*["'](?P<value>[^"']*)["']""",
            match.group("body"),
            re.IGNORECASE,
        ):
            fields[assignment.group("key")] = assignment.group("value")
        if fields.get("name") and fields.get("atchFileId"):
            objects.append(fields)
    return objects


def _download_base_from_functions(html: str) -> str:
    for match in re.finditer(r"""["']([^"']*downFile\.do(?:;jsessionid=[^"'?]+)?)[^"']*["']""", html, re.IGNORECASE):
        value = match.group(1)
        if "cnvrFileDown" in value:
            continue
        return value.split("?")[0]
    return ""


def _build_file_download_url(base_url: str, download_base: str, atch_file_id: str, file_sn: str) -> str:
    if not download_base:
        download_base = _default_board_file_download_url("", "").split("?")[0]
    return urljoin(
        base_url,
        f"{download_base}?atchFileId={quote(atch_file_id, safe='')}&fileSn={quote(file_sn, safe='')}",
    )


def _default_board_file_download_url(atch_file_id: str, file_sn: str) -> str:
    return f"/dggb/board/boardFile/downFile.do?atchFileId={quote(atch_file_id, safe='')}&fileSn={quote(file_sn, safe='')}"


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


def _ignore_attachment_filename(filename: str) -> bool:
    normalized = re.sub(r"\s+", "", filename).lower()
    return all(term in normalized for term in NON_NOTICE_ATTACHMENT_NAME_TERMS)


def _dedupe_filename_key(filename: str) -> str:
    normalized = re.sub(r"\s+", "", filename).lower()
    if normalized in WEAK_FILENAME_KEYS:
        return ""
    return normalized


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
