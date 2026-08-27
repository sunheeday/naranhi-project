"""판독 환각 negative control. 운영 DB 를 건드리지 않는다 — 로컬 파일만 읽는다.

negative control 은 '읽을 수 없는 입력' 이다. 올바른 동작은 '못 읽겠다' 또는 빈 결과이고,
가정통신문 형태의 문장이 나오면 그건 환각이다. positive control 을 함께 돌리는 이유는
'항상 빈 결과를 내서 통과' 하는 가짜 합격을 배제하기 위해서다.
"""
import argparse
import asyncio
import json
import pathlib
import re
import sys

from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor
from extractor.extractors.image_gemini_extractor import extract_image_text

# 지어냈을 때만 나오는 것들. 판독 불가 입력에서 이게 나오면 환각이다.
FABRICATION_MARKERS = (
    "학교", "교장", "학부모", "가정통신문", "안내", "학년", "반",
    "일시", "장소", "신청", "제출", "담임", "교육청",
)
REFUSAL_MARKERS = ("읽을 수 없", "판독", "인식할 수 없", "QR", "알 수 없", "unreadable")


def verdict(text: str) -> tuple[str, list[str]]:
    stripped = text.strip()
    if not stripped:
        return "PASS(empty)", []
    if any(m in stripped for m in REFUSAL_MARKERS) and len(stripped) < 200:
        return "PASS(refused)", []
    hits = [m for m in FABRICATION_MARKERS if m in stripped]
    if hits:
        return "FAIL(fabricated)", hits
    return "PASS(no-markers)", []


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--negative", nargs="+", required=True, help="판독 불가 입력 (QR/백지/노이즈)")
    ap.add_argument("--positive", nargs="+", default=[], help="내용이 확실한 입력")
    args = ap.parse_args()

    gem = GeminiDocumentExtractor()
    report: list[dict] = []

    for kind, paths in (("negative", args.negative), ("positive", args.positive)):
        for raw in paths:
            path = pathlib.Path(raw)
            result = await extract_image_text(
                path, source_name=path.name, gemini=gem, source_id=f"probe:{path.name}"
            )
            text = result.text or ""
            if kind == "negative":
                mark, hits = verdict(text)
            else:
                mark = "PASS(read)" if len(text.strip()) >= 40 else "FAIL(empty-positive)"
                hits = []
            report.append(
                {
                    "kind": kind,
                    "file": path.name,
                    "method": result.method,
                    "chars": len(text.strip()),
                    "verdict": mark,
                    "markers": hits,
                    "head": re.sub(r"\s+", " ", text.strip())[:200],
                }
            )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = [r for r in report if r["verdict"].startswith("FAIL")]
    print(f"\n판정: {'H-FAIL' if failed else 'H-PASS'} (negative {len(args.negative)}건 / positive {len(args.positive)}건)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
