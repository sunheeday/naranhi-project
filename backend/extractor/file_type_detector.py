from __future__ import annotations

from pathlib import Path
import zipfile

from extractor.archive_security import validate_zip_limits


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
XLSX_EXTENSIONS = {".xlsx", ".xlsm"}


def detect_file_type(path: Path, filename: str, content_type: str = "") -> str:
    suffix = Path(filename).suffix.lower() or path.suffix.lower()
    lowered_type = content_type.lower()
    with path.open("rb") as fp:
        head = fp.read(16)

    if head.startswith(b"%PDF") or suffix == ".pdf" or "pdf" in lowered_type:
        return "pdf"
    if suffix in IMAGE_EXTENSIONS or lowered_type.startswith("image/"):
        return "image"
    if suffix == ".hwpx" or _looks_like_hwpx(path):
        return "hwpx"
    if suffix == ".hwp" or head.startswith(b"\xd0\xcf\x11\xe0"):
        return "hwp"
    if suffix in XLSX_EXTENSIONS or _looks_like_xlsx(path):
        return "xlsx"
    if "html" in lowered_type or suffix in {".html", ".htm"}:
        return "html"
    return "unknown"


def _looks_like_hwpx(path: Path) -> bool:
    try:
        if not zipfile.is_zipfile(path):
            return False
        validate_zip_limits(path)
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "mimetype" in names:
                mimetype = archive.read("mimetype").decode("utf-8", errors="ignore")
                if "hwp" in mimetype.lower() or "owpml" in mimetype.lower():
                    return True
            return any(name.startswith("Contents/section") and name.endswith(".xml") for name in names)
    except Exception:
        return False


def _looks_like_xlsx(path: Path) -> bool:
    """xlsx는 zip 컨테이너이고 안에 xl/workbook.xml 이 있다."""
    try:
        if not zipfile.is_zipfile(path):
            return False
        validate_zip_limits(path)
        with zipfile.ZipFile(path) as archive:
            return "xl/workbook.xml" in archive.namelist()
    except Exception:
        return False
