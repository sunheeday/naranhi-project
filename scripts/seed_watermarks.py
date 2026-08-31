"""재가동 컷오프 시딩 (일회성). 기본은 dry-run — --apply 를 줘야 쓴다.

워터마크는 시각이 아니라 '글번호'다. 8개 학교의 board_watermarks 는 2026-06-15
기준값이라 그대로 스케줄러를 켜면 그 뒤에 올라온 글이 전부 신규로 잡힌다
(스캔 깊이 8 × 학교 8 = 최대 64건). 사용자 결정은 '밀린 것 우르르'가 아니라
'지금부터 새로 올라오는 것' 이다.

이 스크립트는 각 게시판을 스캔해 '현재 최상단 글번호'를 워터마크로 박는다.
notices 는 절대 건드리지 않는다 — discover_school_board() 는 저장 경로가 아니다
(discover_and_save_school_board 와 달리 _save_discovered_notice_candidates 를 안 부른다).

실행:  PYTHONPATH=backend backend/venv/Scripts/python.exe scripts/seed_watermarks.py
적용:  PYTHONPATH=backend backend/venv/Scripts/python.exe scripts/seed_watermarks.py --apply
"""
import argparse
import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from app.core.config import get_settings
from app.services.school_crawler_service import (
    POST_SUCCESS_STATUSES,
    SchoolCrawlerService,
    _read_board_watermarks,
    _write_board_watermarks,
    compute_board_watermarks,
)
from app.services.scheduled_crawler_service import select_school_targets


async def main(apply: bool) -> int:
    settings = get_settings()
    selected, _skipped, total = select_school_targets(
        school_id=None,
        limit=None,
        force=True,  # 쿨다운 무시 — 시딩은 지금 전부 해야 한다
        unsupported_recheck_hours=settings.crawler_unsupported_recheck_hours,
    )
    print(f"등록 학교 {total}곳 / 대상 {len(selected)}곳 / 스캔 깊이 {settings.crawler_schedule_notice_count}")
    print(f"모드: {'APPLY (실제로 쓴다)' if apply else 'DRY-RUN (읽기만)'}\n")

    crawler = SchoolCrawlerService()
    backup: dict[str, dict[str, int]] = {}
    unscoped_total = 0

    for target in selected:
        result = await crawler.discover_school_board(
            target.school_id,
            use_gemini=settings.crawler_enable_gemini,
            max_posts=settings.crawler_schedule_notice_count,
        )
        valid = [p for p in result.sample_posts if p.status in POST_SUCCESS_STATUSES and p.detail_url]
        computed = compute_board_watermarks(valid)
        unscoped = [p for p in valid if p.board_key not in computed]
        unscoped_total += len(unscoped)

        existing = _read_board_watermarks(target.school_id)
        backup[target.school_id] = existing
        merged = dict(existing)
        for key, value in computed.items():
            merged[key] = max(merged.get(key, 0), value)

        print(f"[{target.school_name}] status={result.status} posts={len(valid)} 워터마크 비대상={len(unscoped)}")
        for key in sorted(set(existing) | set(computed)):
            print(f"    {key}\n      기존 {existing.get(key, '-')} → 계산 {computed.get(key, '-')} → 적용 {merged.get(key, '-')}")

        if apply and merged != existing:
            _write_board_watermarks(target.school_id, merged)
            print("    → 기록함")

    print(f"\n워터마크 비대상 글 합계: {unscoped_total}건")
    print("  (비숫자 post_id·해시 생성·첨부 파일번호는 워터마크로 막을 수 없다.")
    print("   재가동 첫 런에 이만큼은 들어올 수 있다 — 수용 범위인지 눈으로 판단할 것.)")

    print("\n=== 롤백용 백업 (기존 값) ===")
    print(json.dumps(backup, ensure_ascii=False, indent=2))

    if not apply:
        print("\nDRY-RUN 이었다. 위 '적용' 값이 맞으면 --apply 를 붙여 다시 실행하라.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="실제로 board_watermarks 에 쓴다")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.apply)))
