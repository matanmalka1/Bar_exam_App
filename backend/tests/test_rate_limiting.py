"""Rate limiting tests for auth endpoints.

All TestClient requests share the same synthetic IP (request.client.host).
Each test resets limiter storage for a clean slate.

IP-limit tests: exhaust the IP limit by sending enough requests from the
shared test IP.

Email-limit tests: exhaust the per-email limit by sending enough requests
with the same email address, using different IP-style headers so IP limit
does not trigger first (note: slowapi uses request.client.host, not
X-Forwarded-For, so all TestClient requests are the same IP — email-limit
tests therefore exhaust IP limit first; they verify the 429 fires correctly
regardless of which limit triggers).
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.rate_limit import limiter
from app.models.user import User

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def rate_client(client_builder: Callable[..., Iterator[TestClient]]) -> Iterator[TestClient]:
    def seed(session: Session) -> None:
        session.add(
            User(
                full_name="RL User",
                email="rl@example.com",
                password_hash=hash_password("ValidPass1!"),
                is_active=True,
            )
        )

    with client_builder(seed) as client:  # type: ignore[arg-type]
        yield client


# ── constants ─────────────────────────────────────────────────────────────────

LOGIN_URL = "/api/v1/auth/login"
REGISTER_URL = "/api/v1/auth/register"
FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"

_VALID_LOGIN = {"email": "rl@example.com", "password": "ValidPass1!"}
_WRONG_LOGIN = {"email": "rl@example.com", "password": "WrongPass9!"}
_REG_PAYLOAD = {"full_name": "New User", "email": "newuser@example.com", "password": "ValidPass1!"}


def _repeat(client: TestClient, url: str, json: dict, n: int) -> list[int]:
    return [client.post(url, json=json).status_code for _ in range(n)]


# ── login: valid request before limit ─────────────────────────────────────────


def test_login_valid_request_before_limit_succeeds(rate_client: TestClient) -> None:
    r = rate_client.post(LOGIN_URL, json=_VALID_LOGIN)
    assert r.status_code == 200
    assert r.json()["access_token"]


# ── login: IP limit (10/minute) ───────────────────────────────────────────────


def test_login_ip_limit_triggers_429(rate_client: TestClient) -> None:
    _repeat(rate_client, LOGIN_URL, _WRONG_LOGIN, 10)
    r = rate_client.post(LOGIN_URL, json=_WRONG_LOGIN)
    assert r.status_code == 429


# ── login: email limit (5/minute) ─────────────────────────────────────────────


def test_login_email_limit_triggers_429(rate_client: TestClient) -> None:
    # 5 requests exhaust the email limit; 6th must be 429
    _repeat(rate_client, LOGIN_URL, _WRONG_LOGIN, 5)
    r = rate_client.post(LOGIN_URL, json=_WRONG_LOGIN)
    assert r.status_code == 429


# ── register: valid request before limit ──────────────────────────────────────


def test_register_valid_request_before_limit_succeeds(rate_client: TestClient) -> None:
    r = rate_client.post(REGISTER_URL, json=_REG_PAYLOAD)
    assert r.status_code == 201


# ── register: IP limit (5/minute) ─────────────────────────────────────────────


def test_register_ip_limit_triggers_429(rate_client: TestClient) -> None:
    for i in range(5):
        rate_client.post(REGISTER_URL, json={**_REG_PAYLOAD, "email": f"reg{i}@example.com"})
    r = rate_client.post(REGISTER_URL, json={**_REG_PAYLOAD, "email": "reg_final@example.com"})
    assert r.status_code == 429


# ── forgot-password: valid request before limit ───────────────────────────────


def test_forgot_password_valid_before_limit_is_generic(rate_client: TestClient) -> None:
    r = rate_client.post(FORGOT_URL, json={"email": "rl@example.com"})
    assert r.status_code == 200


# ── forgot-password: IP limit (5/minute) ──────────────────────────────────────


def test_forgot_password_ip_limit_triggers_429(rate_client: TestClient) -> None:
    _repeat(rate_client, FORGOT_URL, {"email": "rl@example.com"}, 5)
    r = rate_client.post(FORGOT_URL, json={"email": "rl@example.com"})
    assert r.status_code == 429


# ── forgot-password: no user enumeration ──────────────────────────────────────


def test_forgot_password_response_identical_for_existing_and_ghost(rate_client: TestClient) -> None:
    # Reset between the two calls to avoid hitting the IP limit
    r_existing = rate_client.post(FORGOT_URL, json={"email": "rl@example.com"})
    limiter._storage.reset()
    r_ghost = rate_client.post(FORGOT_URL, json={"email": "ghost@example.com"})
    assert r_existing.status_code == r_ghost.status_code == 200
    assert r_existing.json() == r_ghost.json()


# ── reset-password: valid request before limit ────────────────────────────────


def test_reset_password_valid_before_limit_returns_non_429(rate_client: TestClient) -> None:
    r = rate_client.post(RESET_URL, json={"token": "invalid", "new_password": "ValidPass1!"})
    assert r.status_code != 429


# ── reset-password: IP limit (10/minute) ──────────────────────────────────────


def test_reset_password_ip_limit_triggers_429(rate_client: TestClient) -> None:
    _repeat(rate_client, RESET_URL, {"token": "bad", "new_password": "ValidPass1!"}, 10)
    r = rate_client.post(RESET_URL, json={"token": "bad", "new_password": "ValidPass1!"})
    assert r.status_code == 429


def test_reset_password_invalid_token_counts_toward_limit(rate_client: TestClient) -> None:
    statuses = _repeat(rate_client, RESET_URL, {"token": "bad", "new_password": "ValidPass1!"}, 10)
    # All 10 hit business logic (not 429), confirming they were counted
    assert all(s != 429 for s in statuses)
    r = rate_client.post(RESET_URL, json={"token": "bad", "new_password": "ValidPass1!"})
    assert r.status_code == 429


# ── 429 error shape ───────────────────────────────────────────────────────────


def test_429_response_has_standard_error_shape(rate_client: TestClient) -> None:
    _repeat(rate_client, LOGIN_URL, _WRONG_LOGIN, 10)
    r = rate_client.post(LOGIN_URL, json=_WRONG_LOGIN)
    assert r.status_code == 429
    body = r.json()
    assert "error" in body
    error = body["error"]
    assert error["code"] == "rate_limit_exceeded"
    assert isinstance(error["message"], str) and error["message"]
    assert "details" in error
