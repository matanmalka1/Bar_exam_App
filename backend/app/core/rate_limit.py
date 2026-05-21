from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    request_id: str | None = getattr(getattr(request, "state", None), "request_id", None)
    error: dict[str, Any] = {
        "code": "rate_limit_exceeded",
        "message": "יותר מדי ניסיונות. נסה שוב בעוד כמה דקות.",
        "details": None,
    }
    if request_id:
        error["request_id"] = request_id
    return JSONResponse(status_code=429, content={"error": error})


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_email_key(prefix: str) -> Callable[[Request], str]:
    """Return a sync key_func that keys on the email in the JSON body.

    Relies on ``request._body`` being cached before this is called, which
    holds for async route handlers (FastAPI parses the Pydantic body via
    ``await request.body()`` before the handler runs).

    Falls back to IP if no valid email is found.
    Key format: ``{prefix}:{email}`` or ``{prefix}:ip:{ip}``.
    """

    def _key_func(request: Request) -> str:
        ip = get_remote_address(request)
        try:
            body_bytes: bytes = getattr(request, "_body", b"")
            if body_bytes:
                import json

                data = json.loads(body_bytes)
                raw_email = data.get("email", "")
                if isinstance(raw_email, str) and raw_email.strip():
                    return f"{prefix}:{normalize_email(raw_email)}"
        except Exception:  # noqa: BLE001
            logger.debug("rate_limit: could not parse email from body, falling back to IP")
        return f"{prefix}:ip:{ip}"

    return _key_func
