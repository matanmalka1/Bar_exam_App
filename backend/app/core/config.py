import os


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
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
