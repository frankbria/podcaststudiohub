"""
Configuration management for Podcastfy API
Loads environment variables and provides application settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "Podcastfy API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Database
    DATABASE_URL: str
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

    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # Spotify OAuth
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None
    SPOTIFY_REDIRECT_URI: Optional[str] = None

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN_REQUESTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_MINUTES: int = 5
    RATE_LIMIT_REGISTER_REQUESTS: int = 3
    RATE_LIMIT_REGISTER_WINDOW_MINUTES: int = 60
    RATE_LIMIT_RESEND_REQUESTS: int = 5
    RATE_LIMIT_RESEND_WINDOW_MINUTES: int = 60
    RATE_LIMIT_TRUST_PROXY: bool = True
    RATE_LIMIT_PROXY_COUNT: int = 1

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

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key_length(cls, v: str) -> str:
        """Enforce minimum 32-character length for AES-256 encryption key."""
        if len(v) < 32:
            raise ValueError(
                "ENCRYPTION_KEY must be at least 32 characters for secure AES encryption"
            )
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

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
