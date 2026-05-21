import os
from typing import Literal, cast

from dotenv import load_dotenv

load_dotenv()

SameSitePolicy = Literal["lax", "strict", "none"]
_ALLOWED_SAMESITE: tuple[SameSitePolicy, ...] = ("lax", "strict", "none")


def _parse_csv_env(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default

    return [item.strip() for item in value.split(",") if item.strip()]


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/bar_exam_study",
)

CORS_ORIGINS = _parse_csv_env(
    os.getenv("CORS_ORIGINS"),
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)

AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-secret-change-me")
AUTH_ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
AUTH_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("AUTH_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "refresh_token")
REFRESH_COOKIE_PATH = os.getenv("REFRESH_COOKIE_PATH", "/api/v1/auth")
REFRESH_COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "false").lower() == "true"


def _samesite_policy(value: str) -> SameSitePolicy:
    lower = value.lower()
    if lower in _ALLOWED_SAMESITE:
        return cast(SameSitePolicy, lower)
    return "lax"


REFRESH_COOKIE_SAMESITE: SameSitePolicy = _samesite_policy(os.getenv("REFRESH_COOKIE_SAMESITE", "lax"))

PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "30"))
FRONTEND_PASSWORD_RESET_URL = os.getenv("FRONTEND_PASSWORD_RESET_URL", "http://localhost:5173/reset-password")
PASSWORD_RESET_DEV_LOG = os.getenv("PASSWORD_RESET_DEV_LOG", "false").lower() == "true"

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "matan1391@gmail.com")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "איפוס סיסמה - בר עורכי דין")
BREVO_TEMPLATE_PASSWORD_RESET = int(os.getenv("BREVO_TEMPLATE_PASSWORD_RESET", "4"))
