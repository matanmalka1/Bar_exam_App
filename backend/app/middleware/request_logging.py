import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_SKIP_PATHS = frozenset({"/health", "/ready", "/docs", "/openapi.json", "/favicon.ico"})

CallNext = Callable[[Request], Awaitable[Response]]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: CallNext) -> Response:  # type: ignore[override]
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            # Use error (not exception) to avoid duplicate stack trace —
            # the global exception handler is the stack-trace source.
            logger.error(
                "request_failed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                },
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        logger.log(
            level,
            "request_completed",
            extra={
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "user_agent": user_agent,
            },
        )
        return response
