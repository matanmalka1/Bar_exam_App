from collections.abc import Callable
from contextlib import AbstractContextManager

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, hash_password
from app.models.user import User

ClientBuilder = Callable[[Callable[[Session], None]], AbstractContextManager[TestClient]]

EMAIL = "alice@example.com"
PASSWORD = "correct-horse-battery"


def _seed_user(*, is_active: bool = True) -> Callable[[Session], None]:
    def seed(session: Session) -> None:
        session.add(
            User(
                full_name="Alice",
                email=EMAIL,
                password_hash=hash_password(PASSWORD),
                is_active=is_active,
            )
        )

    return seed


def test_login_success_returns_token_and_user(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["user"]["email"] == EMAIL
        assert body["user"]["full_name"] == "Alice"
        assert "password_hash" not in body["user"]


def test_login_wrong_password_returns_401(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "nope"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password"


def test_login_unknown_email_returns_401(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
        assert r.status_code == 401


def test_login_inactive_user_returns_401(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user(is_active=False)) as client:
        r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 401


def test_me_returns_user_with_valid_token(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        token = client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        ).json()["access_token"]
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == EMAIL


def test_me_rejects_missing_token(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401


def test_me_rejects_invalid_token(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert r.status_code == 401


def test_logout_invalidates_previous_token(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        token = client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

        logout = client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 204

        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_token_with_stale_token_version_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        # Forge a token with wrong token_version for user id=1
        bad = create_access_token(user_id=1, token_version=999)
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401


def test_token_for_unknown_user_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        bad = create_access_token(user_id=9999, token_version=0)
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401


