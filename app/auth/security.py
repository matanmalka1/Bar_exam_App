from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import (
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_ALGORITHM,
    AUTH_REFRESH_TOKEN_EXPIRE_DAYS,
    AUTH_SECRET_KEY,
)

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not password_hash or password_hash == "!":
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def create_access_token(*, user_id: int, token_version: int) -> str:
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "token_version": token_version,
            "type": ACCESS_TOKEN_TYPE,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=AUTH_ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        }
    )


def create_refresh_token(*, user_id: int, token_version: int) -> str:
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "token_version": token_version,
            "type": REFRESH_TOKEN_TYPE,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=AUTH_REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
        }
    )


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise jwt.InvalidTokenError("wrong token type")
    return payload
