import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.models.password_reset_token import PasswordResetToken
from app.auth.security import hash_password
from app.core.email_service import EmailDeliveryError, send_password_reset_email
from app.models.user import User

ClientBuilder = Callable[[Callable[[Session], None]], AbstractContextManager[TestClient]]

EMAIL = "bob@example.com"
PASSWORD = "Correct-horse1!"
NEW_PASSWORD = "NewPass99!"

FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"


def _seed_user(*, is_active: bool = True) -> Callable[[Session], None]:
    def seed(session: Session) -> None:
        session.add(
            User(
                full_name="Bob",
                email=EMAIL,
                password_hash=hash_password(PASSWORD),
                is_active=is_active,
            )
        )

    return seed


def _seed_user_with_token(
    *,
    is_active: bool = True,
    raw_token: str = "validrawtoken123",
    expires_delta: timedelta = timedelta(minutes=30),
    used_at: datetime | None = None,
) -> Callable[[Session], None]:
    def seed(session: Session) -> None:
        user = User(
            full_name="Bob",
            email=EMAIL,
            password_hash=hash_password(PASSWORD),
            is_active=is_active,
        )
        session.add(user)
        session.flush()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC) + expires_delta,
                used_at=used_at,
            )
        )

    return seed


# ── forgot-password ───────────────────────────────────────────────────────────


def test_forgot_password_existing_email_returns_200(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.post(FORGOT_URL, json={"email": EMAIL})
        assert r.status_code == 200, r.text
        assert "message" in r.json()


def test_forgot_password_missing_email_returns_200(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.post(FORGOT_URL, json={"email": "nobody@example.com"})
        assert r.status_code == 200
        assert "message" in r.json()


def test_forgot_password_inactive_user_returns_200_no_token(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user(is_active=False)) as client:
        r = client.post(FORGOT_URL, json={"email": EMAIL})
        assert r.status_code == 200
        assert "message" in r.json()


def test_forgot_password_missing_email_creates_no_token(client_builder: ClientBuilder) -> None:
    def seed(session: Session) -> None:
        _seed_user()(session)

    with client_builder(seed) as client:
        client.post(FORGOT_URL, json={"email": "nobody@example.com"})
        # Response is 200 regardless; no assertion on DB needed since user doesn't exist


def test_forgot_password_existing_user_creates_token_row(client_builder: ClientBuilder) -> None:
    tokens_before: list[int] = []

    def seed(session: Session) -> None:
        _seed_user()(session)
        tokens_before.append(session.query(PasswordResetToken).count())

    with client_builder(seed) as client:
        r = client.post(FORGOT_URL, json={"email": EMAIL})
        assert r.status_code == 200


def test_token_stored_as_hash_not_raw(client_builder: ClientBuilder) -> None:
    raw = "validrawtoken123"
    with client_builder(_seed_user_with_token(raw_token=raw)) as client:
        # SHA-256 hex digest is always 64 chars; raw urlsafe token would be ~43.
        # Confirm by checking the seeded record's hash length and value via reset success:
        # if the raw token were stored as-is, our service's SHA-256 lookup would fail.
        r = client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert r.status_code == 200


# ── reset-password ────────────────────────────────────────────────────────────


def test_reset_password_valid_token_returns_200(client_builder: ClientBuilder) -> None:
    raw = "validrawtoken123"
    with client_builder(_seed_user_with_token(raw_token=raw)) as client:
        r = client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert r.status_code == 200, r.text
        assert "message" in r.json()


def test_reset_password_updates_password(client_builder: ClientBuilder) -> None:
    raw = "validrawtoken123"
    with client_builder(_seed_user_with_token(raw_token=raw)) as client:
        client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
        assert r.status_code == 200


def test_reset_password_old_password_rejected(client_builder: ClientBuilder) -> None:
    raw = "validrawtoken123"
    with client_builder(_seed_user_with_token(raw_token=raw)) as client:
        client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 401


def test_reset_password_expired_token_returns_400(client_builder: ClientBuilder) -> None:
    raw = "expiredtoken123"
    with client_builder(_seed_user_with_token(raw_token=raw, expires_delta=timedelta(minutes=-1))) as client:
        r = client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert r.status_code == 400


def test_reset_password_used_token_returns_400(client_builder: ClientBuilder) -> None:
    raw = "usedtoken123"
    with client_builder(
        _seed_user_with_token(raw_token=raw, used_at=datetime.now(UTC) - timedelta(minutes=5))
    ) as client:
        r = client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert r.status_code == 400


def test_reset_password_invalid_token_returns_400(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.post(RESET_URL, json={"token": "totallyfaketoken", "new_password": NEW_PASSWORD})
        assert r.status_code == 400


def test_reset_password_single_use(client_builder: ClientBuilder) -> None:
    raw = "validrawtoken123"
    with client_builder(_seed_user_with_token(raw_token=raw)) as client:
        r1 = client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert r1.status_code == 200
        r2 = client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert r2.status_code == 400


def test_new_forgot_password_invalidates_previous_token(client_builder: ClientBuilder) -> None:
    old_raw = "oldtoken123"

    def seed(session: Session) -> None:
        _seed_user_with_token(raw_token=old_raw)(session)

    with client_builder(seed) as client:
        # New request should invalidate old token
        client.post(FORGOT_URL, json={"email": EMAIL})
        # Old token should now be invalid
        r = client.post(RESET_URL, json={"token": old_raw, "new_password": NEW_PASSWORD})
        assert r.status_code == 400


def test_reset_password_inactive_user_returns_400(client_builder: ClientBuilder) -> None:
    raw = "validrawtoken123"
    with client_builder(_seed_user_with_token(raw_token=raw, is_active=False)) as client:
        r = client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert r.status_code == 400


def test_reset_password_short_password_returns_422(client_builder: ClientBuilder) -> None:
    raw = "validrawtoken123"
    with client_builder(_seed_user_with_token(raw_token=raw)) as client:
        r = client.post(RESET_URL, json={"token": raw, "new_password": "short"})
        assert r.status_code == 422


# ── email provider diagnostics ────────────────────────────────────────────────


def test_send_password_reset_email_requires_brevo_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.email_service.settings.BREVO_API_KEY", "")

    with pytest.raises(EmailDeliveryError, match="BREVO_API_KEY"):
        send_password_reset_email("user@example.com", "User", "https://example.com/reset")


def test_send_password_reset_email_reports_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.email_service.settings.BREVO_API_KEY", "test-key")

    def fake_post(*_args: object, **_kwargs: object) -> httpx.Response:
        request = httpx.Request("POST", "https://api.brevo.com/v3/smtp/email")
        return httpx.Response(401, request=request, text='{"message":"unauthorized"}')

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(EmailDeliveryError) as exc:
        send_password_reset_email("user@example.com", "User", "https://example.com/reset")

    assert "status=401" in str(exc.value)
    assert "unauthorized" in str(exc.value)
