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
    vertex_ai_project_id: str | None = Field(default=None, alias="VERTEX_AI_PROJECT_ID")
    vertex_ai_location: str = Field(default="global", alias="VERTEX_AI_LOCATION")
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
    worker_job_groups_raw: str = Field(
        default="translation",
        alias="WORKER_JOB_GROUPS",
    )

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
