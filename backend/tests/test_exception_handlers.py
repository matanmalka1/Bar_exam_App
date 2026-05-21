from typing import Annotated

from fastapi import Body, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AppError
from app.services.practice_session_service import SessionError


class ItemIn(BaseModel):
    name: int


class PayloadIn(BaseModel):
    items: list[ItemIn]


def _client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/validation")
    def validation(payload: Annotated[PayloadIn, Body()]) -> PayloadIn:
        return payload

    @app.get("/http-404")
    def http_404() -> None:
        raise HTTPException(status_code=404, detail="missing internal thing")

    @app.get("/app-error")
    def app_error() -> None:
        raise AppError(
            status_code=409,
            code="resource_conflict",
            message="הפעולה מתנגשת עם מצב קיים",
        )

    @app.get("/domain-422")
    def domain_422() -> None:
        raise SessionError(422, "question_count exceeds available question pool")

    @app.get("/database-error")
    def database_error() -> None:
        raise SQLAlchemyError("SELECT secret_table failed on postgresql://user:pass@host/db")

    @app.get("/generic-error")
    def generic_error() -> None:
        raise RuntimeError("secret traceback details")

    return TestClient(app, raise_server_exceptions=False)


def test_validation_error_returns_normalized_error_envelope() -> None:
    response = _client().post("/validation", json={"items": [{}]})

    assert response.status_code == 422
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "חלק מהשדות אינם תקינים"
    assert body["error"]["details"] == [
        {
            "field": "items.0.name",
            "message": "Field required",
            "type": "missing",
        }
    ]


def test_http_404_returns_normalized_hebrew_error() -> None:
    response = _client().get("/http-404")

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "not_found",
        "message": "המשאב המבוקש לא נמצא",
        "details": None,
    }


def test_app_error_returns_configured_error() -> None:
    response = _client().get("/app-error")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "resource_conflict",
        "message": "הפעולה מתנגשת עם מצב קיים",
        "details": None,
    }


def test_domain_422_uses_unprocessable_entity_and_preserves_business_detail() -> None:
    response = _client().get("/domain-422")

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "unprocessable_entity",
        "message": "חלק מהנתונים אינם תקינים",
        "details": {"detail": "question_count exceeds available question pool"},
    }


def test_sqlalchemy_error_does_not_expose_database_internals() -> None:
    response = _client().get("/database-error")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "database_error"
    assert body["error"]["message"] == "אירעה שגיאת מסד נתונים"
    assert body["error"]["details"] is None
    assert "secret_table" not in response.text
    assert "postgresql://" not in response.text


def test_generic_error_does_not_expose_traceback_or_internal_message() -> None:
    response = _client().get("/generic-error")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_server_error"
    assert body["error"]["message"] == "אירעה שגיאה לא צפויה"
    assert body["error"]["details"] is None
    assert "secret traceback details" not in response.text
    assert "Traceback" not in response.text
