"""Cloud Logging 이 읽는 구조화 JSON 한 줄 로깅.

평문 포맷(%(asctime)s %(levelname)s …)은 severity 매핑과 구조화 필드를 못 태운다.
그래서 지금은 로그 기반 지표를 만들 수 없고 심각도 필터도 걸리지 않는다.
새 의존성 없이 Formatter 하나로 해결한다.

두 가지를 반드시 지킨다:
- 개인정보 금지: 이 모듈은 어떤 필드도 알아서 채우지 않는다. 호출부가
  extra= 로 무엇을 붙이느냐가 전부다 — 공지 본문·제목·이름·연락처를
  extra 에 넣지 않는 것은 호출부 책임이다.
- 크롤/번역을 죽이지 않음: format() 은 어떤 입력에도 예외를 밖으로
  던지지 않는다. 표준 logging.StreamHandler.emit() 자체가 format() 예외를
  잡아 handleError() 로 넘기긴 하지만(그러면 이 프로세스는 안 죽는다),
  그 경로는 한 줄 JSON 계약을 깨고 보기 흉한 다중 라인 트레이스백을
  stdout에 남긴다. 그래서 format() 내부에서 한 번 더 방어해 항상 유효한
  JSON 한 줄을 낸다.
"""

from __future__ import annotations

import json
import logging
import os

from extractor.http_security import sanitize_error

# LogRecord 가 기본으로 갖는 속성들. 이 밖의 속성만 구조화 필드로 내보낸다
# (LOGGER.info(..., extra={"school_id": ...}) 로 붙인 것들).
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return repr(value)
    except Exception:  # noqa: BLE001 - a broken __repr__ must not break logging.
        return "<unrepresentable>"


class CloudLoggingFormatter(logging.Formatter):
    def __init__(self, *, job_type: str | None = None) -> None:
        super().__init__()
        self._job_type = job_type

    def format(self, record: logging.LogRecord) -> str:
        try:
            return self._format(record)
        except Exception:  # noqa: BLE001 - logging must never break the caller's job.
            # 최소한의 안전한 한 줄은 낸다. severity/logger 는 record 에서 바로
            # 뽑을 수 있으니 여기서도 실패할 일이 거의 없다.
            fallback = {
                "severity": getattr(record, "levelname", "ERROR"),
                "message": "<log formatting failed>",
                "logger": getattr(record, "name", "unknown"),
            }
            if self._job_type:
                fallback["job_type"] = self._job_type
            return json.dumps(fallback, ensure_ascii=False)

    def _format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "severity": record.levelname,
            "message": sanitize_error(record.getMessage()),
            "logger": record.name,
        }
        if self._job_type:
            payload["job_type"] = self._job_type
        if record.exc_info:
            # 여러 줄 traceback 을 한 필드에 담는다. json.dumps 가 \n 을 이스케이프하므로
            # 출력은 여전히 한 줄이다. sanitize_error 로 재사용 — 예외 문자열에 열쇠가
            # 섞여 있어도(예: 인증 실패 응답에 토큰이 에코) 여기서 걸러진다.
            payload["exception"] = sanitize_error(self.formatException(record.exc_info))
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = _jsonable(value)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(*, job_type: str | None = None, level: str | None = None) -> None:
    """진입점에서 한 번 부른다. basicConfig 를 대체한다.

    실패해도 크롤/번역 Job 을 막지 않는다 — 여기서 예외가 나면 구식 평문
    포맷으로 폴백한다. 로깅 설정 자체가 Job 시작을 막는 것이 이 함수가
    막아야 할 가장 나쁜 결과다.
    """
    try:
        resolved = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
        resolved_level = getattr(logging, resolved, logging.INFO)
        if not isinstance(resolved_level, int):
            resolved_level = logging.INFO
        handler = logging.StreamHandler()
        handler.setFormatter(CloudLoggingFormatter(job_type=job_type))
        logging.basicConfig(
            level=resolved_level,
            handlers=[handler],
            force=True,
        )
    except Exception:  # noqa: BLE001 - never let logging setup take the job down.
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            force=True,
        )
        logging.getLogger(__name__).exception(
            "structured logging setup failed, fell back to plain text format"
        )
