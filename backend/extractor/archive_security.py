from __future__ import annotations

import os
import zipfile
from pathlib import Path


def validate_zip_limits(
    path: Path,
    *,
    max_uncompressed_bytes: int | None = None,
    max_entry_bytes: int | None = None,
    max_compression_ratio: float | None = None,
) -> None:
    max_total = max_uncompressed_bytes or _int_env("MAX_HWPX_UNCOMPRESSED_BYTES", 104_857_600)
    max_entry = max_entry_bytes or _int_env("MAX_HWPX_ENTRY_BYTES", 52_428_800)
    max_ratio = max_compression_ratio or _float_env("MAX_HWPX_COMPRESSION_RATIO", 100.0)

    total_uncompressed = 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            total_uncompressed += info.file_size
            if info.file_size > max_entry:
                raise RuntimeError(f"zip_entry_too_large: {info.filename} {info.file_size} > {max_entry}")
            if total_uncompressed > max_total:
                raise RuntimeError(f"zip_uncompressed_too_large: {total_uncompressed} > {max_total}")
            if info.compress_size > 0 and info.file_size / info.compress_size > max_ratio:
                raise RuntimeError(
                    f"zip_compression_ratio_too_high: {info.filename} "
                    f"{info.file_size / info.compress_size:.1f} > {max_ratio:.1f}"
                )
            if info.compress_size == 0 and info.file_size > 0:
                raise RuntimeError(f"zip_invalid_zero_compressed_entry: {info.filename}")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
