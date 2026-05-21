import logging
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AppError,
    contains_hebrew,
    http_error_code_for_status,
    http_error_message_for_status,
)

logger = logging.getLogger(__name__)

REQUEST_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )


def validation_error_details(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "field": _field_path(error.get("loc", ())),
            "message": str(error.get("msg", "Invalid value")),
            "type": str(error.get("type", "value_error")),
        }
        for error in errors
    ]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Any, exc: AppError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Any, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            status_code=422,
            code="validation_error",
            message="חלק מהשדות אינם תקינים",
            details=validation_error_details(exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Any, exc: StarletteHTTPException) -> JSONResponse:
        status_code = exc.status_code
        return error_response(
            status_code=status_code,
            code=http_error_code_for_status(status_code),
            message=_http_error_message(exc),
            details=None,
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(_request: Any, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Unhandled database error")
        return error_response(
            status_code=500,
            code="database_error",
            message="אירעה שגיאת מסד נתונים",
            details=None,
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Any, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error")
        return error_response(
            status_code=500,
            code="internal_server_error",
            message="אירעה שגיאה לא צפויה",
            details=None,
        )


def _field_path(loc: Any) -> str:
    parts = list(loc) if isinstance(loc, (list, tuple)) else [loc]
    if parts and parts[0] in REQUEST_LOC_PREFIXES:
        parts = parts[1:]
    return ".".join(str(part) for part in parts)


def _http_error_message(exc: StarletteHTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str) and contains_hebrew(detail):
        return detail
    return http_error_message_for_status(exc.status_code)
