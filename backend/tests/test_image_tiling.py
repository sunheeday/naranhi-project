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

    def test_tiled_image_consumes_exactly_one_budget_call(self) -> None:
        """타일 24조각이 공지당 8콜 예산을 먹어치우면 안 된다. 이미지 소스 1개 = 예산 1콜."""
        from extractor.budget import ExtractionBudget

        path = _make_image(100, 20000)  # 초장축 -> 10조각
        gem = _FakeGemini()
        budget = ExtractionBudget(
            max_gemini_calls=8, max_inline_images=6, max_ocr_bytes=26_214_400, max_pdf_pages_for_ocr=20
        )

        result = asyncio.run(
            extract_image_text(path, source_name="tall.png", gemini=gem, budget=budget, source_id="s1")
        )

        self.assertEqual(budget.gemini_calls_used, 1)
        self.assertFalse(budget.budget_exhausted)
        self.assertGreaterEqual(gem.calls, 9)  # 조각은 다 돌았다
        self.assertIn("조각 텍스트", result.text)

    def test_single_image_still_consumes_one_budget_call(self) -> None:
        from extractor.budget import ExtractionBudget

        path = _make_image(800, 600)
        gem = _FakeGemini()
        budget = ExtractionBudget(
            max_gemini_calls=8, max_inline_images=6, max_ocr_bytes=26_214_400, max_pdf_pages_for_ocr=20
        )

        result = asyncio.run(
            extract_image_text(path, source_name="normal.png", gemini=gem, budget=budget, source_id="s1")
        )

        self.assertEqual(result.method, "gemini_vision")
        self.assertEqual(budget.gemini_calls_used, 1)
        self.assertEqual(gem.calls, 1)

    def test_exhausted_budget_skips_ocr_entirely(self) -> None:
        from extractor.budget import ExtractionBudget

        path = _make_image(100, 20000)
        gem = _FakeGemini()
        budget = ExtractionBudget(
            max_gemini_calls=0, max_inline_images=6, max_ocr_bytes=26_214_400, max_pdf_pages_for_ocr=20
        )

        result = asyncio.run(
            extract_image_text(path, source_name="tall.png", gemini=gem, budget=budget, source_id="s1")
        )

        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(gem.calls, 0)  # 조각을 만들기도 전에 끝난다

    def test_tile_count_is_capped_by_env(self) -> None:
        import os
        from unittest.mock import patch

        path = _make_image(100, 20000)
        gem = _FakeGemini()
        with patch.dict(os.environ, {"MAX_TILES_PER_IMAGE": "3"}):
            result = asyncio.run(
                extract_image_text(path, source_name="tall.png", gemini=gem, source_id="s1")
            )

        self.assertEqual(result.method, "gemini_vision_tiled[3]")
        self.assertEqual(gem.calls, 3)


if __name__ == "__main__":
    unittest.main()
