from __future__ import annotations

import json
import logging
from datetime import datetime, timezone  # type: ignore[attr-defined]
from typing import TYPE_CHECKING, Any

from app.core.logging_context import get_request_id

if TYPE_CHECKING:
    from app.core.config import Settings

_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "taskName",
    }
)

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(  # noqa: UP017
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
            "request_id": get_request_id(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Merge safe custom extra fields only
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = value

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["exception"] = record.exc_text

        if record.stack_info:
            entry["stack_info"] = self.formatStack(record.stack_info)

        try:
            return json.dumps(entry, default=str, ensure_ascii=False)
        except Exception:
            return json.dumps(
                {"level": "ERROR", "message": "log serialization failed", "logger": record.name},
            )


def configure_logging(settings: Settings, *, force: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    _CONFIGURED = True

    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any pre-existing handlers to avoid duplicate output
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setLevel(level)

    if settings.OBSERVABILITY_JSON_LOGS:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root.addHandler(handler)

    # Silence noisy third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
