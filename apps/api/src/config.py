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
        # Lets a cross-origin client supply its own correlation id so its trace
        # and ours share one. Without it the browser's preflight rejects the
        # header outright (issue #320).
        "X-Request-ID",
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
    STORAGE_GC_INTERVAL_SECONDS: int = 300  # storage-deletion-outbox drain cadence (issue #366)

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
    # Spotify/Apple ingest episodes via the project's RSS feed; their direct
    # publish endpoints are unverified (issue #315). Off = distribution returns
    # the RSS feed URL; on = experimental direct API publish.
    ENABLE_DIRECT_PLATFORM_PUBLISH: bool = False

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
    # Public origin of this API, used to build externally fetchable URLs
    # (e.g. RSSFeed.public_url -> {API_PUBLIC_BASE_URL}/feeds/{id}/podcast.xml).
    # The raw S3 URL is AccessDenied — the bucket has no public-read policy (#385).
    API_PUBLIC_BASE_URL: str = "http://localhost:8000"
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24

    # Logging
    LOG_LEVEL: str = "INFO"
    # "json" emits one structured record per line (request_id/tenant_id bound),
    # shared by uvicorn and Celery so an incident can be stitched across both.
    # "text" is the human-readable escape hatch for local dev (issue #320).
    LOG_FORMAT: str = "json"

    # Observability (issue #320)
    # Error tracking. Unset -> Sentry is never initialised, so dev/CI/tests stay
    # offline with no opt-out ceremony. Same Optional-override convention as
    # CELERY_BROKER_URL above.
    SENTRY_DSN: Optional[str] = None
    # Fraction of requests traced for performance monitoring. 0.0 = errors only:
    # this issue asks for error tracking, not APM.
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    # Per-dependency ceiling for the /ready probe. A hung DB or Redis must fail
    # the probe fast rather than hang it until the client's own timeout.
    READINESS_CHECK_TIMEOUT_SECONDS: float = 2.0

    # In-repo generation engine (issue #541). The live task still calls
    # podcastfy until #543 cuts it over, so these only drive src/engine today.
    # Provider defaults were checked against the live model catalogues on
    # 2026-09-21; podcastfy's own default, gemini-1.5-pro-latest, is a
    # deprecated alias. Both are settings so #543 can retune without a deploy.
    # Sources, because these names post-date most training data and read as
    # typos otherwise: ai.google.dev/gemini-api/docs/models lists
    # "gemini-3.5-flash" (GA, no -preview suffix), and
    # developers.openai.com/api/docs/models lists "GPT-5.6 Terra" as the
    # "balances intelligence and cost" tier, model id "gpt-5.6-terra".
    # No test can catch a wrong id here — every test fakes the SDK boundary —
    # so changing one needs a live smoke test, not just a green suite.
    ENGINE_LLM_PROVIDER: str = "gemini"  # gemini | openai
    ENGINE_GEMINI_MODEL: str = "gemini-3.5-flash"
    ENGINE_OPENAI_MODEL: str = "gpt-5.6-terra"
    ENGINE_MAX_OUTPUT_TOKENS: int = 8192
    # Chunk bounds for long-form generation. Same defaults podcastfy used, but
    # ENGINE_MAX_CHUNKS is a hard cap here: it bounds the number of paid calls
    # a single episode can make.
    ENGINE_MAX_CHUNKS: int = 8
    ENGINE_MIN_CHUNK_CHARS: int = 600
    OPENAI_API_TIMEOUT: int = 120  # Timeout in seconds for OpenAI API calls

    # In-repo TTS layer (src/engine/tts, issue #542). Not on the live path
    # until #543. Provider model ids were read off each vendor's current docs
    # on 2026-09-21; as with the LLM ids above, no test can catch a wrong one
    # because every test fakes the SDK boundary.
    #   - gpt-4o-mini-tts is OpenAI's current TTS model and the only one that
    #     honours `instructions`; podcastfy used the legacy tts-1-hd.
    #   - gemini-2.5-flash-tts is GA multi-speaker Gemini-TTS. podcastfy pinned
    #     en-US-Studio-MultiSpeaker and *enforced* it in validate_parameters;
    #     that Studio voice is now restricted.
    #   - eleven_v3 is the only ElevenLabs model family supporting
    #     Text-to-Dialogue and audio tags.
    ENGINE_OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    ENGINE_GEMINI_TTS_MODEL: str = "gemini-2.5-flash-tts"
    # Google is the one provider whose stored config need not carry voices:
    # GEMINI_REQUIRED_KEYS in src/schemas/tts_configuration.py is only
    # {model, language_code}, so a perfectly valid row has none. These are the
    # fallback prebuilt Gemini-TTS speakers for that case.
    ENGINE_GEMINI_HOST_VOICE: str = "Kore"
    ENGINE_GEMINI_GUEST_VOICE: str = "Charon"
    ENGINE_ELEVENLABS_MODEL: str = "eleven_v3"
    ENGINE_ELEVENLABS_OUTPUT_FORMAT: str = "mp3_44100_128"
    # Characters per Text-to-Dialogue request, summed across every input.
    # Deliberately 2000, not the 5000 that applies to plain single-voice
    # text-to-speech on the same model -- exceeding it returns a validation
    # error or truncates a streaming response part-way.
    ENGINE_ELEVENLABS_CHAR_LIMIT: int = 2000
    # Bytes of MultiSpeakerMarkup per synthesize_speech request. Google
    # documents the markup field at 4,000 bytes (and markup + prompt combined
    # at 8,000), so this is the stricter of the documented figures. Bytes, not
    # characters: for a non-ASCII script the two differ several times over.
    ENGINE_GEMINI_MARKUP_BYTE_LIMIT: int = 4000
    # Concurrent per-turn synthesis requests. Bounded because providers
    # rate-limit and because Celery runs prefork, so this multiplies by the
    # worker count.
    ENGINE_TTS_MAX_CONCURRENCY: int = 4
    # Matches src/tasks/audio_composition.py. podcastfy was inconsistent:
    # 320k on its multi-speaker path, pydub's default on the per-turn one.
    ENGINE_AUDIO_BITRATE: str = "192k"

    # Transcript Validation Settings
    MIN_TRANSCRIPT_WORDS: int = 100
    MAX_SPEAKER_IMBALANCE_PERCENT: float = 80.0
    TRANSCRIPT_VALIDATION_MAX_RETRIES: int = 3
    MIN_CONVERSATION_TURNS: int = 3
    # Phrases that mean the model broke character and answered as an assistant.
    # Comma-separated, matched as plain case-insensitive substrings against the
    # spoken text, so every entry must be a phrase that cannot occur in ordinary
    # dialogue and cannot itself contain a comma. The list this replaced
    # contained "based on the", "according to my" and "should clarify", which
    # occur constantly in real conversation and would have rejected good
    # scripts; it was never exercised, because its only consumer was the dead
    # service deleted in #539.
    AI_ARTIFACT_PATTERNS: str = (
        "as an ai,as a language model,i cannot fulfill,"
        "i can't assist with,i am unable to provide"
    )

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
