from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from extractor.extractors.image_gemini_extractor import extract_image_text


class _FakeResult:
    text = "조각 텍스트"
    confidence = 0.9
    warnings: list[str] = []
    detected_layout = "single"
    source_pages: list[int] = []


class _FakeGemini:
    """gemini.extract_path 만 흉내내는 가짜(실제 Vertex 호출 없음)."""

    def __init__(self) -> None:
        self.calls = 0

    async def extract_path(self, path: Path, *, mime_type: str, prompt: str) -> _FakeResult:
        self.calls += 1
        return _FakeResult()


def _make_image(width: int, height: int) -> Path:
    path = Path(tempfile.mkdtemp(prefix="img-test-")) / "x.png"
    Image.new("RGB", (width, height), "white").save(path)
    return path


class ImageTilingTests(unittest.TestCase):
    def test_tall_poster_is_tiled_into_multiple_ocr_calls(self) -> None:
        path = _make_image(100, 5000)  # 세로 5000 > 가로 100*2.5 -> 타일링
        gem = _FakeGemini()

        result = asyncio.run(extract_image_text(path, source_name="tall.png", gemini=gem, source_id="s1"))

        self.assertTrue(result.method.startswith("gemini_vision_tiled"))
        self.assertGreaterEqual(gem.calls, 3)  # 5000px / 2000step ≈ 3 조각
        self.assertIn("조각 텍스트", result.text)

    def test_normal_image_is_single_ocr_call(self) -> None:
        path = _make_image(800, 600)  # 일반 비율·크기 -> 단일
        gem = _FakeGemini()

        result = asyncio.run(extract_image_text(path, source_name="normal.png", gemini=gem, source_id="s1"))

        self.assertEqual(result.method, "gemini_vision")
        self.assertEqual(gem.calls, 1)


if __name__ == "__main__":
    unittest.main()
