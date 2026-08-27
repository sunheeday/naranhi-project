from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
import warnings

LOGGER = logging.getLogger(__name__)

from PIL import Image, ImageOps

from extractor.budget import ExtractionBudget
from extractor.models import ExtractedText
from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor, ocr_prompt


IMAGE_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}
Image.MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "50000000"))


async def extract_image_text(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor,
    budget: ExtractionBudget | None = None,
    source_id: str = "",
) -> ExtractedText:
    """이미지 OCR. 초장축/초대형 포스터는 세로로 타일링해 조각별로 OCR한다.

    886x25020 같은 스크롤형 포스터를 2400px 박스로 줄이면 폭이 ~85px로 찌부되어 글자를
    못 읽고 환각(엉뚱한 학교명)이 난다. 그래서 일반 이미지는 그대로, 초장축은 잘라서 처리한다.

    예산은 **이미지 소스 하나당 1콜**로 예약한다. 타일마다 예약하면 24조각짜리 포스터가
    공지당 8콜을 9조각째에 다 먹고 나머지 15조각이 조용히 버려진다 — 그 공지의 PDF·HWP
    첨부는 예산을 한 톨도 못 쓰게 된다. 타일 수는 MAX_TILES_PER_IMAGE 로만 제한한다.
    """
    if budget is not None:
        decision = budget.reserve_gemini_call(source_id or source_name, path.stat().st_size)
        if not decision.ok:
            return ExtractedText(
                source=source_name,
                method="gemini_vision",
                text="",
                status="budget_exhausted",
                warnings=[decision.reason],
            )

    tiles = _tile_if_oversized(path)
    if len(tiles) == 1:
        return await _ocr_image(tiles[0], source_name=source_name, gemini=gemini, source_id=source_id)

    texts: list[str] = []
    empty = 0
    failed = 0
    for index, tile_path in enumerate(tiles):
        try:  # 한 조각이 실패(빈 조각/일시 오류)해도 나머지 조각은 계속 OCR
            result = await _ocr_image(
                tile_path,
                source_name=f"{source_name}#t{index}",
                gemini=gemini,
                source_id=f"{source_id}:{index}" if source_id else "",
            )
            if result.text.strip():
                texts.append(result.text.strip())
            else:
                empty += 1
        except Exception:  # noqa: BLE001 - isolate per-tile failures.
            failed += 1
            continue
    LOGGER.info(
        "image tiles: source=%s tiles=%s ok=%s empty=%s failed=%s",
        source_name,
        len(tiles),
        len(texts),
        empty,
        failed,
    )
    combined = "\n\n".join(texts)
    return ExtractedText(
        source=source_name,
        method=f"gemini_vision_tiled[{len(tiles)}]",
        text=combined,
        status="success" if combined.strip() else "empty_or_unreadable",
    )


async def _ocr_image(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor,
    source_id: str = "",
) -> ExtractedText:
    # 예산 예약은 호출부(extract_image_text)가 이미 했다. 여기서 다시 잡으면 타일마다
    # 1콜이 나가 24조각짜리가 공지 예산을 통째로 먹는다.
    normalized_path = _normalize_image(path)
    mime_type = IMAGE_MIME_BY_SUFFIX.get(normalized_path.suffix.lower(), "image/png")
    result = await gemini.extract_path(
        normalized_path,
        mime_type=mime_type,
        prompt=ocr_prompt(source_name),
    )
    return ExtractedText(
        source=source_name,
        method="gemini_vision",
        text=result.text,
        status="success" if result.text.strip() else "empty_or_unreadable",
        confidence=result.confidence,
        warnings=result.warnings,
        metadata={"detected_layout": result.detected_layout, "source_pages": result.source_pages},
    )


def _tile_if_oversized(path: Path) -> list[Path]:
    """초장축/초대형 이미지면 세로 타일 경로 리스트를, 아니면 [원본 경로]를 돌려준다.

    조건: 세로가 가로의 2.5배 초과 OR 총 화소 400만 초과. (둘 다 아니면 단일 처리)
    타일은 2200px 높이·200px 겹침, 최대 MAX_TILES_PER_IMAGE(기본 24)조각.
    실패 시 단일 경로로 폴백(기존 동작 보존).

    타일 높이를 올려 개수를 줄이는 안은 실효가 없다 — _normalize_image 가 모든 타일을
    thumbnail((2400, 2400)) 으로 다시 줄이므로 2200 초과분은 어차피 버려진다.
    """
    try:
        with Image.open(path) as probe:
            width, height = probe.size
            if height <= width * 2.5 and width * height <= 4_000_000:
                return [path]
            image = ImageOps.exif_transpose(probe)
            if image.mode != "RGB":
                image = image.convert("RGB")
            tile_height, step = 2200, 2000  # 200px overlap
            limit = _max_tiles_per_image()
            temp_dir = Path(tempfile.mkdtemp(prefix="naranhi-tile-"))
            tiles: list[Path] = []
            y = 0
            while y < height and len(tiles) < limit:
                tile_path = temp_dir / f"{path.stem}-t{len(tiles)}.png"
                image.crop((0, y, width, min(height, y + tile_height))).save(tile_path)
                tiles.append(tile_path)
                y += step
            return tiles or [path]
    except Exception:  # noqa: BLE001 - tiling must never break extraction; fall back to single image.
        return [path]


def _max_tiles_per_image() -> int:
    """타일 상한. 1 로 두면 타일링이 사실상 꺼져 옛 동작에 가까워진다(롤백 수단)."""
    try:
        return max(1, int(os.getenv("MAX_TILES_PER_IMAGE", "24")))
    except ValueError:
        return 24


def _normalize_image(path: Path) -> Path:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as probe:
                probe.verify()
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image)
                image.load()
                image.thumbnail((2400, 2400))
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                output = path.with_suffix(".normalized.png")
                image.save(output, format="PNG", optimize=True)
                return output
    except Image.DecompressionBombError as exc:
        raise RuntimeError(f"image_decompression_bomb: {exc}") from exc
    except Image.DecompressionBombWarning as exc:
        raise RuntimeError(f"image_decompression_bomb_warning: {exc}") from exc
