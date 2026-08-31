"""정기 크롤 실행 요약을 crawl_run_history 에 1행 남긴다.

지금은 요약이 stdout JSON 한 줄로만 나가고 사라진다(scheduled_school_crawler.py:48).
이 테이블이 "성공률 추이" 화면의 유일한 데이터 소스다.

outcome 은 exit code 로 구별할 수 없는 네 가지를 나눈다:
  idle     processed_count == 0. 아무 학교도 안 돌았는데 success_rate 는 1.0,
           alarm 은 False 로 나온다(scheduled_crawler_service.py:340-341).
  alarm    성공률이 임계치 미만. exit 1.
  crashed  잡 자체가 예외로 죽음. exit 1 — alarm 과 exit code 가 겹친다.
           ScheduledCrawlerSummary 자체가 없는 경로라 outcome_for() 를 안 거치고
           호출부(scheduled_school_crawler.py main())가 직접 outcome="crashed" 로 넘긴다.
  ok       그 외.

적재는 best-effort 다: insert 실패(0041 미적용으로 테이블이 없는 경우 포함)가
정기 크롤 자체의 성공/실패를 바꾸면 안 된다. 실패해도 크롤은 이미 끝난 뒤이므로
여기서 예외를 삼켜도 잃는 것은 "이번 실행의 이력 한 줄"뿐이다 — 대신 왜 못
쌓였는지는 구조화 로그(logging_setup.CloudLoggingFormatter)에 남겨 나중에
"화면이 왜 비어있는지" 추적 가능하게 한다.

targets/results 는 ScheduledSchoolTarget.to_dict() / ScheduledSchoolResult.to_dict()
가 만드는 그대로 넘어온다 — school_id/school_name/상태 코드/개수/시스템 예외
메시지뿐이고 공지 제목·본문은 애초에 이 dataclass 에 없다. 이 서비스는 그 값을
그대로 옮겨 적재할 뿐 새 필드를 추가하지 않는다 — 절대 title/content 류 키를
row 에 넣지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.supabase import get_supabase_client

LOGGER = logging.getLogger(__name__)


def outcome_for(summary: dict[str, Any]) -> str:
    if int(summary.get("processed_count") or 0) == 0:
        return "idle"
    if bool(summary.get("alarm")):
        return "alarm"
    return "ok"


def record_crawl_run(
    summary: dict[str, Any],
    *,
    outcome: str,
    error_message: str | None = None,
) -> bool:
    """실행 이력 1행 적재. best-effort — 실패해도 크롤 결과를 바꾸지 않는다."""
    row = {
        "started_at": summary.get("started_at"),
        "finished_at": summary.get("finished_at"),
        "outcome": outcome,
        "dry_run": bool(summary.get("dry_run")),
        "force": bool(summary.get("force")),
        "total_registered": int(summary.get("total_registered") or 0),
        "selected_count": int(summary.get("selected_count") or 0),
        "skipped_count": int(summary.get("skipped_count") or 0),
        "processed_count": int(summary.get("processed_count") or 0),
        "success_count": int(summary.get("success_count") or 0),
        "failure_count": int(summary.get("failure_count") or 0),
        # scheduled_crawler_service.py:61-76 실측 결과 15개 필드 중 하나 — 브리프
        # 스니펫에서 빠져 있었다(사업 C Task 8 이 나중에 추가해 브리프가 몰랐음,
        # 0041 마이그레이션 주석에서 같은 문제가 지적됨). 빠뜨리면 이 신호가
        # 화면에서 영구히 안 보인다.
        "fallback_count": int(summary.get("fallback_count") or 0),
        "success_rate": float(summary.get("success_rate") or 0.0),
        "alarm": bool(summary.get("alarm")),
        "targets": summary.get("targets") or [],
        "results": summary.get("results") or [],
        "error_message": error_message,
    }
    try:
        get_supabase_client().table("crawl_run_history").insert(row).execute()
        return True
    except Exception as exc:  # noqa: BLE001 - 이력 적재 실패가 크롤 결과를 바꾸면 안 된다.
        # 0041 이 운영에 아직 적용되지 않았으면 여기로 떨어진다(테이블 없음).
        # 그 경우도 조용히 넘어가되 흔적은 남긴다 — 안 그러면 화면이 계속 비어
        # 있는 이유를 나중에 알 수 없다. extra 는 outcome/예외 타입뿐이라 개인정보가
        # 없다(logging_setup.CloudLoggingFormatter 가 message 도 sanitize_error 로 거른다).
        LOGGER.warning(
            "crawl run history insert failed, continuing without history row: outcome=%s error=%s",
            outcome,
            exc,
            extra={"outcome": outcome, "insert_error_type": type(exc).__name__},
        )
        return False
