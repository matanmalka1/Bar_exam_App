from __future__ import annotations

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SameSitePolicy = Literal["lax", "strict", "none"]

_UNSAFE_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── environment ──────────────────────────────────────────────────────────
    ENV: Literal["development", "production", "test"] = "development"

    # ── database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/bar_exam_study"
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Accepts CSV string ("http://a,http://b") or JSON array in .env / env vars.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    def cors_origins_list(self) -> list[str]:
        raw = self.CORS_ORIGINS.strip()
        if raw.startswith("["):
            import json
            return json.loads(raw)
        return [item.strip() for item in raw.split(",") if item.strip()]

    # ── auth ─────────────────────────────────────────────────────────────────
    AUTH_SECRET_KEY: str = _UNSAFE_SECRET
    AUTH_ALGORITHM: str = "HS256"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    AUTH_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── refresh cookie ────────────────────────────────────────────────────────
    REFRESH_COOKIE_NAME: str = "refresh_token"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    REFRESH_COOKIE_SECURE: bool = False
    REFRESH_COOKIE_SAMESITE: SameSitePolicy = "lax"

    # ── password reset ────────────────────────────────────────────────────────
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    FRONTEND_PASSWORD_RESET_URL: str = "http://localhost:5173/reset-password"
    PASSWORD_RESET_DEV_LOG: bool = False

    # ── observability ─────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    OBSERVABILITY_JSON_LOGS: bool = True
    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    # ── Brevo ─────────────────────────────────────────────────────────────────
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = "matan1391@gmail.com"
    BREVO_SENDER_NAME: str = "איפוס סיסמה - בר עורכי דין"
    BREVO_TEMPLATE_PASSWORD_RESET: int = 4

    # ── production guard ──────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.ENV != "production":
            return self

        errors: list[str] = []

        if self.AUTH_SECRET_KEY == _UNSAFE_SECRET:
            errors.append("AUTH_SECRET_KEY must be changed from the default in production")

        if not self.REFRESH_COOKIE_SECURE:
            errors.append("REFRESH_COOKIE_SECURE must be true in production")

        if self.REFRESH_COOKIE_SAMESITE == "none" and not self.REFRESH_COOKIE_SECURE:
            errors.append("SameSite=none requires Secure=true")

        if not self.BREVO_API_KEY:
            errors.append("BREVO_API_KEY must be set in production")

        if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
            errors.append("DATABASE_URL points to localhost in production")

        if errors:
            bullet = "\n  - ".join(errors)
            raise ValueError(f"Invalid production config:\n  - {bullet}")

        return self


settings = Settings()

# ── module-level aliases (keep existing imports working) ──────────────────────
DATABASE_URL = settings.DATABASE_URL
CORS_ORIGINS: list[str] = settings.cors_origins_list()

AUTH_SECRET_KEY = settings.AUTH_SECRET_KEY
AUTH_ALGORITHM = settings.AUTH_ALGORITHM
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES = settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES
AUTH_REFRESH_TOKEN_EXPIRE_DAYS = settings.AUTH_REFRESH_TOKEN_EXPIRE_DAYS

REFRESH_COOKIE_NAME = settings.REFRESH_COOKIE_NAME
REFRESH_COOKIE_PATH = settings.REFRESH_COOKIE_PATH
REFRESH_COOKIE_SECURE = settings.REFRESH_COOKIE_SECURE
REFRESH_COOKIE_SAMESITE = settings.REFRESH_COOKIE_SAMESITE

PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
FRONTEND_PASSWORD_RESET_URL = settings.FRONTEND_PASSWORD_RESET_URL
PASSWORD_RESET_DEV_LOG = settings.PASSWORD_RESET_DEV_LOG

BREVO_API_KEY = settings.BREVO_API_KEY
BREVO_SENDER_EMAIL = settings.BREVO_SENDER_EMAIL
BREVO_SENDER_NAME = settings.BREVO_SENDER_NAME
BREVO_TEMPLATE_PASSWORD_RESET = settings.BREVO_TEMPLATE_PASSWORD_RESET

LOG_LEVEL = settings.LOG_LEVEL
OBSERVABILITY_JSON_LOGS = settings.OBSERVABILITY_JSON_LOGS
SENTRY_ENABLED = settings.SENTRY_ENABLED
SENTRY_DSN = settings.SENTRY_DSN
SENTRY_ENVIRONMENT = settings.SENTRY_ENVIRONMENT
SENTRY_TRACES_SAMPLE_RATE = settings.SENTRY_TRACES_SAMPLE_RATE
