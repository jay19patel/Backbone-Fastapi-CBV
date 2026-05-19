import secrets  # noqa: F401 — available for reference in error messages
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── JWT / Auth ────────────────────────────────────────────────────────────
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # ── Environment ────────────────────────────────────────────────────────────
    ENVIRONMENT: Literal["develop", "staging", "production"] = "develop"

    # ── Database ───────────────────────────────────────────────────────────────
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "backbone_app"

    # ── Branding ───────────────────────────────────────────────────────────────
    SITE_NAME: str = "Soul Craft Studio"
    SITE_URL: str = "http://localhost:8000"
    FRONTEND_VERIFY_URL: str = "http://localhost:3000/verify-email"
    FRONTEND_VERIFY_SUCCESS_URL: str = "http://localhost:3000/verify-success"
    FRONTEND_VERIFY_ERROR_URL: str = "http://localhost:3000/verify-error"

    # ── Admin Credentials (REQUIRED — no defaults) ────────────────────────────
    # SECURITY: No defaults. Both must be explicitly set in .env.
    ADMIN_EMAIL: str = Field(alias="ADMIN_EMAIL")
    ADMIN_PASSWORD: str = Field(alias="ADMIN_PASSWORD")

    # ── Cache / Redis ──────────────────────────────────────────────────────────
    CACHE_ENABLED: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 300
    WORKER_COUNT: int = 2
    INTERNAL_WORKER_COUNT: int = 2

    # ── Session Cache ──────────────────────────────────────────────────────────
    SESSION_CACHE_TTL: int = 60  # seconds — Redis TTL for session validation cache

    # ── Rate Limiting ──────────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_CALLS: int = 100
    RATE_LIMIT_DEFAULT_WINDOW: int = 60
    RATE_LIMIT_AUTH_CALLS: int = 10
    RATE_LIMIT_AUTH_WINDOW: int = 60
    RATE_LIMIT_RESET_CALLS: int = 5
    RATE_LIMIT_RESET_WINDOW: int = 300

    # ── CORS ───────────────────────────────────────────────────────────────────
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ── Google OAuth ───────────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # ── Cloudinary ─────────────────────────────────────────────────────────────
    CLOUDINARY_URL: str = ""

    # ── Email ──────────────────────────────────────────────────────────────────
    EMAIL_ENABLED: bool = True
    EMAIL_HOST: str = "smtp.gmail.com"
    EMAIL_PORT: int = 587
    EMAIL_USE_TLS: bool = True
    EMAIL_USE_SSL: bool = False
    EMAIL_USERNAME: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_FROM_EMAIL: str = "no-reply@example.com"
    EMAIL_FROM_NAME: str = "Backbone"
    EMAIL_TIMEOUT_SECONDS: int = 30

    # ── Validators ─────────────────────────────────────────────────────────────

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        # SECURITY: Reject known-weak placeholder values in all environments.
        _known_weak = {
            "your_super_secret_key_here_at_least_32_chars",
            "secret",
            "changeme",
            "development_secret",
        }
        if v.lower() in _known_weak or len(v) < 32:
            raise ValueError(
                "SECRET_KEY is too weak or is a known placeholder. "
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return v

    @field_validator("ADMIN_PASSWORD")
    @classmethod
    def admin_password_must_be_strong(cls, v: str) -> str:
        # SECURITY: Reject trivially guessable admin passwords.
        _known_weak = {"admin", "password", "admin123", "123456", "changeme", "test"}
        if v.lower() in _known_weak or len(v) < 8:
            raise ValueError(
                "ADMIN_PASSWORD is too weak. Use a strong password (min 8 chars) in .env."
            )
        return v

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "develop"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cookie_settings(self) -> dict:
        if self.is_development:
            return {"secure": False, "httponly": True, "samesite": "lax"}
        return {"secure": True, "httponly": True, "samesite": "strict"}

    def validate_runtime(self) -> None:
        """Called at application startup. Raises ValueError on unsafe configuration."""
        errors: list[str] = []

        if self.is_production:
            if not self.cors_origins_list:
                errors.append("CORS_ALLOWED_ORIGINS must be set explicitly in production.")

        if errors:
            raise RuntimeError(
                "Backbone startup validation failed:\n" + "\n".join(f"  • {e}" for e in errors)
            )


settings = Settings()
