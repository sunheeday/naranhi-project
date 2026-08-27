from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins_raw: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_service_role_key: str | None = Field(
        default=None,
        alias="SUPABASE_SERVICE_ROLE_KEY",
    )

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_api_keys: str | None = Field(default=None, alias="GEMINI_API_KEYS")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_translation_model: str | None = Field(
        default=None,
        alias="GEMINI_TRANSLATION_MODEL",
    )
    gemini_source_hard_fact_model: str | None = Field(
        default=None,
        alias="GEMINI_SOURCE_HARD_FACT_MODEL",
    )
    gemini_ocr_model_primary: str = Field(
        default="gemini-2.5-flash-lite",
        alias="GEMINI_OCR_MODEL_PRIMARY",
    )
    gemini_ocr_model_fallback: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_OCR_MODEL_FALLBACK",
    )
    gemini_timeout_seconds: float = Field(default=60.0, alias="GEMINI_TIMEOUT_SECONDS")
    # 전역 동시 Gemini 호출 상한(DSQ guard). 워커가 공지를 동시 처리할 때 Vertex로 가는
    # 동시 콜을 이 수로 묶어 self-inflicted 429를 막는다. 공지 동시성(WORKER_BATCH_SIZE)과
    # 무관하게 콜 동시수만 캡한다.
    gemini_max_concurrency: int = Field(
        default=12,
        ge=1,
        le=64,
        alias="GEMINI_MAX_CONCURRENCY",
    )
    # 번역 파이프라인의 비기계 단계(피벗·타겟·검증·자동수정·카드)에 적용할 thinking 예산.
    # None = 모델 기본값(Gemini 2.5 Flash 는 Auto, 최대 8,192). 0 = 끔.
    # 실측상 파이프라인 지연의 75~78% 가 thinking 토큰이다. 0 으로 두면 134.7s → 33.5s.
    # 기계적 추출·역번역 5콜은 이 값과 무관하게 항상 0이다(MECHANICAL_THINKING_BUDGET).
    translation_thinking_budget: int | None = Field(
        default=None,
        ge=0,
        alias="TRANSLATION_THINKING_BUDGET",
    )
    # 문맥·어조 검증 단계만 thinking을 기본(동적)으로 되돌리는 부분 적용 스위치(arm-b2,
    # 계획서 §6.2). thinking 전면 off(arm-b) 실측에서 hard_fact 보존이 무너졌다
    # (학년 오기재·없는 날짜 생성·이메일을 전화번호로 지어냄). True면 검증 단계만
    # thinking_budget=None, 나머지 비기계 단계는 translation_thinking_budget 그대로.
    translation_context_tone_thinking_override: bool = Field(
        default=False,
        alias="TRANSLATION_CONTEXT_TONE_THINKING_OVERRIDE",
    )
    vertex_ai_project_id: str | None = Field(default=None, alias="VERTEX_AI_PROJECT_ID")
    vertex_ai_location: str = Field(default="global", alias="VERTEX_AI_LOCATION")
    # 번역 파이프라인이 쓸 JSON 모델 백엔드. gemini | bedrock.
    # 문서판독(GeminiDocumentExtractor)과 크롤러는 이 값과 무관하게 Gemini 를 계속 쓴다.
    # 되돌리기는 이 한 줄이다 — 코드 revert 가 필요 없다.
    translation_backend: str = Field(default="gemini", alias="TRANSLATION_BACKEND")
    # global. 라우팅은 사용자 승인됨(스펙 §16 해결됨 Q1). 다만 학교 공지에는
    # 학생 이름·학년반·보호자 연락처가 섞이므로 호출한 프로필을 로그에 남긴다.
    bedrock_region: str = Field(default="ap-northeast-2", alias="BEDROCK_REGION")
    # 기본은 Haiku 다(스펙 §5.10.1). 2026-08-27 실측에서 PDF·이미지 판독 정확도가
    # Sonnet 과 동급이고 텍스트 지연은 더 짧았다(920ms vs 1,303ms).
    # 게이트를 못 넘을 때만 Sonnet 으로 승급한다 — env 한 줄이다.
    # Opus 는 쓰지 않는다(비용, 사용자 지시). Nova 는 한국어 본문 생성 경로에서 제외한다
    # (읽지 못한 문서의 본문을 지어냈다 — 스펙 §5.9.2).
    bedrock_translation_model: str = Field(
        default="global.anthropic.claude-haiku-4-5-20251001-v1:0",
        alias="BEDROCK_TRANSLATION_MODEL",
    )
    # 원문 하드팩트 추출 단계만 다른 모델로 돌리고 싶을 때 쓴다.
    # None 이면 bedrock_translation_model 을 그대로 쓴다.
    # 여기에도 Nova 를 넣지 않는다 — 하드팩트는 «지어내면 코드가 못 잡는» 자리다.
    bedrock_mechanical_model: str | None = Field(default=None, alias="BEDROCK_MECHANICAL_MODEL")
    # Bedrock Converse 는 boto3 동기 호출이라 전용 스레드풀에서 돈다.
    # asyncio 기본 executor 는 min(32, cpu+4) = 워커(--cpu=1)에서 5라 조용히 직렬화된다.
    bedrock_max_workers: int = Field(
        default=32,
        ge=1,
        le=64,
        alias="BEDROCK_MAX_WORKERS",
    )
    google_calendar_credentials_json: str | None = Field(
        default=None,
        alias="GOOGLE_CALENDAR_CREDENTIALS_JSON",
    )
    neis_api_key: str | None = Field(default=None, alias="NEIS_API_KEY")
    crawler_timeout_seconds: float = Field(default=30.0, alias="CRAWLER_TIMEOUT_SECONDS")
    crawler_school_timeout_seconds: float = Field(
        default=180.0,
        alias="CRAWLER_SCHOOL_TIMEOUT_SECONDS",
    )
    crawler_internal_token: str | None = Field(
        default=None,
        alias="CRAWLER_INTERNAL_TOKEN",
    )
    crawler_initial_notice_count: int = Field(
        default=5,
        ge=1,
        le=20,
        alias="CRAWLER_INITIAL_NOTICE_COUNT",
    )
    crawler_notice_cache_limit_per_school: int = Field(
        default=50,
        ge=1,
        le=500,
        alias="CRAWLER_NOTICE_CACHE_LIMIT_PER_SCHOOL",
    )
    crawler_max_posts: int = Field(default=5, alias="CRAWLER_MAX_POSTS")
    crawler_enable_gemini: bool = Field(default=False, alias="CRAWLER_ENABLE_GEMINI")
    # 증분수집(watermark): 게시판별 마지막 최대 글번호보다 큰 글만 신규 처리(트림된 옛 글 재추출 방지).
    # 신뢰 가능한 숫자 일련번호에만 적용되고 그 외는 기존 중복제거로 폴백. 문제 시 false로 즉시 비활성.
    crawler_watermark_enabled: bool = Field(
        default=True,
        alias="CRAWLER_WATERMARK_ENABLED",
    )
    crawler_schedule_concurrency: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="CRAWLER_SCHEDULE_CONCURRENCY",
    )
    crawler_schedule_notice_count: int = Field(
        default=5,
        ge=1,
        le=50,
        alias="CRAWLER_SCHEDULE_NOTICE_COUNT",
    )
    crawler_unsupported_recheck_hours: int = Field(
        default=168,
        ge=1,
        alias="CRAWLER_UNSUPPORTED_RECHECK_HOURS",
    )
    crawler_schedule_fail_rate_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        alias="CRAWLER_SCHEDULE_FAIL_RATE_THRESHOLD",
    )
    extractor_max_notices_per_run: int = Field(
        default=5,
        ge=1,
        alias="EXTRACTOR_MAX_NOTICES_PER_RUN",
    )
    extractor_notice_concurrency: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="EXTRACTOR_NOTICE_CONCURRENCY",
    )
    extractor_notice_timeout_seconds: float = Field(
        default=600.0,
        ge=1.0,
        alias="EXTRACTOR_NOTICE_TIMEOUT_SECONDS",
    )
    extractor_stale_minutes: int = Field(
        default=180,
        ge=1,
        alias="EXTRACTOR_STALE_MINUTES",
    )
    extractor_max_gemini_calls_per_run: int = Field(
        default=80,
        ge=0,
        alias="EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN",
    )
    auto_translation_locale_concurrency: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="AUTO_TRANSLATION_LOCALE_CONCURRENCY",
    )
    source_translation_concurrency: int = Field(
        default=4,
        ge=1,
        le=20,
        alias="SOURCE_TRANSLATION_CONCURRENCY",
    )
    worker_poll_interval_seconds: float = Field(
        default=2.0,
        ge=0.1,
        alias="WORKER_POLL_INTERVAL_SECONDS",
    )
    worker_batch_size: int = Field(
        default=3,
        ge=1,
        le=20,
        alias="WORKER_BATCH_SIZE",
    )
    worker_retry_delay_seconds: int = Field(
        default=120,
        ge=1,
        alias="WORKER_RETRY_DELAY_SECONDS",
    )
    worker_job_stale_minutes: int = Field(
        default=180,
        ge=1,
        alias="WORKER_JOB_STALE_MINUTES",
    )
    worker_job_groups_raw: str = Field(
        default="translation",
        alias="WORKER_JOB_GROUPS",
    )
    # 큐에 잡을 넣은 직후 해당 Cloud Run Job을 깨우는 트리거. 기본 off라
    # 로컬·테스트·트리거 미설정 환경에서는 아무 동작도 하지 않는다.
    worker_trigger_enabled: bool = Field(
        default=False,
        alias="WORKER_TRIGGER_ENABLED",
    )
    worker_trigger_debounce_seconds: float = Field(
        default=10.0,
        ge=0.0,
        alias="WORKER_TRIGGER_DEBOUNCE_SECONDS",
    )
    gcp_project_id: str = Field(default="", alias="GCP_PROJECT_ID")
    gcp_region: str = Field(default="", alias="GCP_REGION")
    translation_worker_job_name: str = Field(default="", alias="TRANSLATION_WORKER_JOB_NAME")
    crawler_worker_job_name: str = Field(default="", alias="CRAWLER_WORKER_JOB_NAME")

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins_raw.split(",")
            if origin.strip()
        ]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def ai_configured(self) -> bool:
        return self.gemini_configured

    @property
    def use_vertex(self) -> bool:
        return bool(self.vertex_ai_project_id)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.use_vertex or self.gemini_api_key or self.gemini_api_keys)

    @property
    def gemini_key_material(self) -> str | None:
        values = [
            (self.gemini_api_keys or "").strip(),
            (self.gemini_api_key or "").strip(),
        ]
        merged = ",".join(value for value in values if value)
        return merged or None

    @property
    def worker_job_groups(self) -> list[str]:
        return [
            value.strip().lower()
            for value in self.worker_job_groups_raw.split(",")
            if value.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
