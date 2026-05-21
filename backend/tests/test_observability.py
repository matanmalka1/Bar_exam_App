import json
import logging
import sys
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.exception_handlers import register_exception_handlers
from app.core.logging_config import JsonFormatter
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware


def _obs_client() -> TestClient:
    _app = FastAPI()
    register_exception_handlers(_app)
    _app.add_middleware(RequestLoggingMiddleware)
    _app.add_middleware(RequestIDMiddleware)

    @_app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    @_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("test error")

    return TestClient(_app, raise_server_exceptions=False)


def test_response_has_x_request_id() -> None:
    response = _obs_client().get("/ok")
    assert response.status_code == 200
    assert "x-request-id" in response.headers


def test_client_request_id_is_preserved() -> None:
    response = _obs_client().get("/ok", headers={"X-Request-ID": "my-test-id"})
    assert response.headers.get("x-request-id") == "my-test-id"


def test_missing_request_id_is_generated() -> None:
    response = _obs_client().get("/ok")
    rid = response.headers.get("x-request-id", "")
    assert rid != ""
    UUID(rid)  # raises ValueError if not valid UUID format


def test_500_error_response_includes_request_id() -> None:
    response = _obs_client().get("/boom")
    assert response.status_code == 500
    body = response.json()
    request_id = body.get("error", {}).get("request_id")
    assert request_id is not None
    assert request_id != ""


def test_request_timing_does_not_break_success() -> None:
    response = _obs_client().get("/ok")
    assert response.status_code == 200


def test_health_endpoint_still_works() -> None:
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers


def test_json_formatter_outputs_valid_json() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello world",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "request_id" in parsed
    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert "timestamp" in parsed
