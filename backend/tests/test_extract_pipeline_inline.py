from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from extractor import extract_pipeline
from extractor.models import DownloadedFile, InlineImageRef, SourceCandidate


def _inline_candidate() -> SourceCandidate:
    return SourceCandidate(
        source_id="inline_image_1",
        source_type="inline_image",
        origin_url="https://school.kr/img/notice.png",
        filename="notice.png",
        inline_ref=InlineImageRef(url="https://school.kr/img/notice.png", alt="", source_text=""),
    )


class InlineImageCollectOnSkipTests(unittest.IsolatedAsyncioTestCase):
    """OCR 을 건너뛴 인라인 사진도 '본문 사진'으로 수집되는지 (#2 이미지-only 공지 빈 화면 방지)."""

    async def _run(self, *, reason: str) -> tuple[object, list[str]]:
        collected: list[str] = []

        async def _on_attachment(source_id: str, downloaded: object) -> None:
            collected.append(source_id)

        fake_dl = DownloadedFile(
            url="https://school.kr/img/notice.png",
            path=Path("notice.png"),
            filename="notice.png",
            content_type="image/png",
            size_bytes=1234,
        )
        decision = {"ok": False, "status": "skipped", "reason": reason}
        with patch.object(extract_pipeline, "_inline_image_ocr_decision", return_value=decision), patch.object(
            extract_pipeline, "download_attachment", new=AsyncMock(return_value=fake_dl)
        ):
            source = await extract_pipeline._extract_source(
                _inline_candidate(),
                fetched_final_url="https://school.kr/notice",
                html_text="본문처럼 보이는 긴 텍스트" * 500,  # auto-skip 을 유발하는 상황(긴 html)
                temp_dir=Path("."),
                gemini=None,
                budget=MagicMock(),
                on_attachment=_on_attachment,
            )
        return source, collected

    async def test_collects_image_when_ocr_skipped_for_no_content_signal(self) -> None:
        source, collected = await self._run(reason="inline_image_no_content_signal")
        self.assertEqual(source.status, "skipped")        # 소스 자체는 여전히 skipped(OCR 안 함)
        self.assertEqual(collected, ["inline_image_1"])    # 그래도 이미지는 수집된다(본문 사진용)

    async def test_collects_image_when_budget_exhausted(self) -> None:
        _source, collected = await self._run(reason="budget_exhausted")
        self.assertEqual(collected, ["inline_image_1"])

    async def test_does_not_collect_noise_image(self) -> None:
        source, collected = await self._run(reason="inline_image_noise_filter")
        self.assertEqual(source.status, "skipped")
        self.assertEqual(collected, [])                    # 로고/배너 등 노이즈는 수집하지 않는다


if __name__ == "__main__":
    unittest.main()
