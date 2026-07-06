"""
Configuration management for Podcastfy API
Loads environment variables and provides application settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "Podcastfy API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    # Fail-closed default: unset environments behave as production (no mock
    # billing URLs, etc.). Dev/test must opt out explicitly (issue #298).
    ENVIRONMENT: str = "production"
    # Bind loopback only: nginx reverse-proxies to 127.0.0.1 in prod and local
    # dev reaches it over localhost. Never default to 0.0.0.0 (issue #209).
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # Database
    DATABASE_URL: str
    # Privileged (superuser/BYPASSRLS owner) URL used ONLY by Alembic so RLS-affected
    # backfills apply to all rows. Falls back to DATABASE_URL when unset (issue #301).
    # Same optional-override convention as CELERY_BROKER_URL.
    MIGRATION_DATABASE_URL: Optional[str] = None
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security & Authentication
    ENCRYPTION_KEY: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"  # Changed from RS256: HS256 uses symmetric key (simple secret string)
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    CORS_ALLOW_HEADERS: list[str] = [
        "Accept",
        "Accept-Language",
        "Content-Type",
        "Authorization",
    ]

    # API Keys - LLM Providers
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # API Keys - TTS Providers
    ELEVENLABS_API_KEY: Optional[str] = None
    GOOGLE_CLOUD_CREDENTIALS: Optional[str] = None

    # AWS S3
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET: Optional[str] = None
    AWS_REGION: str = "us-east-1"

    # Local audio storage (no-S3 fallback). When AWS_S3_BUCKET is unset, generated
    # audio is persisted here and served from disk. MUST be a persistent, backed-up
    # path in production — not ephemeral /tmp (issue #292).
    LOCAL_AUDIO_STORAGE_PATH: str = "storage/audio"

    # Stripe billing (both required to enable billing; see billing_service)
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_ALWAYS_EAGER: bool = False
    # Long-form generation can run for many minutes. Ordering invariant must hold:
    # soft < hard < visibility_timeout < reaper threshold (issue #294).
    CELERY_TASK_SOFT_TIME_LIMIT: int = 1500   # 25m — in-task SoftTimeLimitExceeded fires
    CELERY_TASK_TIME_LIMIT: int = 1800        # 30m — hard kill ceiling
    CELERY_BROKER_VISIBILITY_TIMEOUT: int = 2400  # 40m — keep in-flight msgs from redelivering
    EPISODE_REAP_THRESHOLD_SECONDS: int = 2700    # 45m — reaper fails genuinely-stuck episodes
    REAP_STUCK_EPISODES_INTERVAL_SECONDS: int = 300  # reaper cadence

    # Spotify OAuth
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None
    SPOTIFY_REDIRECT_URI: Optional[str] = None

    # Billing quota ENFORCEMENT (metering always records). Off on dev/staging
    # so persistent E2E users can't 402 themselves by exhausting the free tier.
    BILLING_ENFORCEMENT_ENABLED: bool = True

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN_REQUESTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_MINUTES: int = 5
    RATE_LIMIT_REGISTER_REQUESTS: int = 10
    RATE_LIMIT_REGISTER_WINDOW_MINUTES: int = 60
    RATE_LIMIT_RESEND_REQUESTS: int = 5
    RATE_LIMIT_RESEND_WINDOW_MINUTES: int = 60
    RATE_LIMIT_TRUST_PROXY: bool = True
    RATE_LIMIT_PROXY_COUNT: int = 1

    # Email verification enforcement — set False in dev/test to allow login without verifying
    REQUIRE_EMAIL_VERIFICATION: bool = True

    # Gemini API reliability settings
    GEMINI_API_TIMEOUT: int = 120  # Timeout in seconds for Gemini API calls
    GEMINI_API_MAX_RETRIES: int = 3  # Maximum retry attempts for failed calls

    # Workflow feature flags
    ENABLE_AUDIO_COMPOSITION: bool = False
    ENABLE_PLATFORM_DISTRIBUTION: bool = False

    # Email / SMTP
    EMAIL_ENABLED: bool = False
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = "noreply@podcaststudiohub.com"
    EMAIL_FROM_NAME: str = "Podcastfy"
    FRONTEND_URL: str = "http://localhost:3000"
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24

    # Logging
    LOG_LEVEL: str = "INFO"

    # Transcript Validation Settings
    MIN_TRANSCRIPT_WORDS: int = 100
    MAX_SPEAKER_IMBALANCE_PERCENT: float = 80.0
    TRANSCRIPT_VALIDATION_MAX_RETRIES: int = 3
    MIN_CONVERSATION_TURNS: int = 3
    AI_ARTIFACT_PATTERNS: str = "i apologize,as an ai,should clarify,according to my,based on the"

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key_length(cls, v: str) -> str:
        """Enforce minimum 32-character length for AES-256 encryption key."""
        if len(v) < 32:
            raise ValueError(
                "ENCRYPTION_KEY must be at least 32 characters for secure AES encryption"
            )
        return v

    @model_validator(mode="after")
    def validate_celery_timeout_ordering(self) -> "Settings":
        """Enforce soft < hard < visibility_timeout < reaper threshold (issue #294).

        The ordering is what guarantees the in-task SoftTimeLimitExceeded handler
        fires before the hard kill, the broker does not redeliver in-flight
        messages, and the reaper only catches genuinely-stuck rows. Env overrides
        could otherwise silently break it and reintroduce stuck/duplicate episodes.
        """
        ordered = [
            ("CELERY_TASK_SOFT_TIME_LIMIT", self.CELERY_TASK_SOFT_TIME_LIMIT),
            ("CELERY_TASK_TIME_LIMIT", self.CELERY_TASK_TIME_LIMIT),
            ("CELERY_BROKER_VISIBILITY_TIMEOUT", self.CELERY_BROKER_VISIBILITY_TIMEOUT),
            ("EPISODE_REAP_THRESHOLD_SECONDS", self.EPISODE_REAP_THRESHOLD_SECONDS),
        ]
        for (lo_name, lo), (hi_name, hi) in zip(ordered, ordered[1:]):
            if not lo < hi:
                raise ValueError(
                    f"{lo_name} ({lo}) must be < {hi_name} ({hi}): "
                    "required invariant soft < hard < visibility_timeout < reaper"
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        """True when ENVIRONMENT is production (case-insensitive)."""
        return self.ENVIRONMENT.strip().lower() == "production"

    @property
    def celery_broker(self) -> str:
        """Get Celery broker URL, fallback to REDIS_URL"""
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_backend(self) -> str:
        """Get Celery result backend URL, fallback to REDIS_URL"""
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL


# Global settings instance
settings = Settings()
