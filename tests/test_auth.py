from collections.abc import Callable
from contextlib import AbstractContextManager

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, create_refresh_token, hash_password
from app.core.config import REFRESH_COOKIE_NAME
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
        assert r.json()["error"]["code"] == "unauthorized"


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
        token = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["access_token"]
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
        token = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["access_token"]
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


def _empty_seed(_session: Session) -> None:
    return None


REG_PAYLOAD = {"full_name": "  New Person  ", "email": "NEW@Mail.com", "password": "Longenough1!"}


def test_register_creates_user_and_returns_token_and_cookie(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        r = client.post("/api/v1/auth/register", json=REG_PAYLOAD)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "new@mail.com"
        assert body["user"]["full_name"] == "New Person"
        assert "password_hash" not in body["user"]
        assert REFRESH_COOKIE_NAME in r.cookies


def test_register_then_login_works(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        client.post("/api/v1/auth/register", json=REG_PAYLOAD)
        client.cookies.clear()
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "new@mail.com", "password": "Longenough1!"},
        )
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "new@mail.com"


def test_register_duplicate_email_returns_409(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        assert client.post("/api/v1/auth/register", json=REG_PAYLOAD).status_code == 201
        r = client.post(
            "/api/v1/auth/register",
            json={**REG_PAYLOAD, "email": "new@mail.com"},
        )
        assert r.status_code == 409


def test_register_email_normalization_collides(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        client.post(
            "/api/v1/auth/register",
            json={"full_name": "A", "email": "test@mail.com", "password": "Longenough1!"},
        )
        r = client.post(
            "/api/v1/auth/register",
            json={"full_name": "B", "email": "TEST@MAIL.COM", "password": "Longenough1!"},
        )
        assert r.status_code == 409


def test_register_invalid_email_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        r = client.post(
            "/api/v1/auth/register",
            json={"full_name": "X", "email": "not-an-email", "password": "Longenough1!"},
        )
        assert r.status_code == 422


def test_register_short_password_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        r = client.post(
            "/api/v1/auth/register",
            json={"full_name": "X", "email": "ok@mail.com", "password": "short"},
        )
        assert r.status_code == 422


def test_register_weak_password_no_upper_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        r = client.post(
            "/api/v1/auth/register",
            json={"full_name": "X", "email": "ok@mail.com", "password": "nouppercase1!"},
        )
        assert r.status_code == 422


def test_register_weak_password_no_lower_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        r = client.post(
            "/api/v1/auth/register",
            json={"full_name": "X", "email": "ok@mail.com", "password": "NOLOWERCASE1!"},
        )
        assert r.status_code == 422


def test_register_weak_password_no_special_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        r = client.post(
            "/api/v1/auth/register",
            json={"full_name": "X", "email": "ok@mail.com", "password": "NoSpecial1234"},
        )
        assert r.status_code == 422


def test_register_blank_name_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        r = client.post(
            "/api/v1/auth/register",
            json={"full_name": "    ", "email": "ok@mail.com", "password": "Longenough1!"},
        )
        assert r.status_code == 422


def test_login_sets_refresh_cookie(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200
        assert REFRESH_COOKIE_NAME in r.cookies


def test_refresh_with_valid_cookie_returns_new_access(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert REFRESH_COOKIE_NAME in login.cookies
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"


def test_refresh_without_cookie_returns_401(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        client.cookies.clear()
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 401


def test_refresh_invalid_token_returns_401(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        client.cookies.set(REFRESH_COOKIE_NAME, "garbage")
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 401


def test_refresh_rejects_access_token_as_refresh(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        token = create_access_token(user_id=1, token_version=0)
        client.cookies.set(REFRESH_COOKIE_NAME, token)
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 401


def test_refresh_after_logout_fails(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        access = login.json()["access_token"]
        client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"})
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 401


def test_logout_without_auth_but_with_cookie_clears_and_revokes(
    client_builder: ClientBuilder,
) -> None:
    with client_builder(_seed_user()) as client:
        login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        access = login.json()["access_token"]
        assert REFRESH_COOKIE_NAME in client.cookies

        r = client.post("/api/v1/auth/logout")
        assert r.status_code == 204
        # token_version bumped → previous access invalid
        assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code == 401
        # refresh cookie cleared → cannot refresh
        assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_with_no_cookie_returns_204(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        client.cookies.clear()
        r = client.post("/api/v1/auth/logout")
        assert r.status_code == 204


def test_access_token_without_type_is_rejected(client_builder: ClientBuilder) -> None:
    import jwt as _jwt

    from app.core.config import AUTH_ALGORITHM, AUTH_SECRET_KEY

    with client_builder(_seed_user()) as client:
        token = _jwt.encode(
            {"sub": "1", "token_version": 0, "exp": 9999999999},
            AUTH_SECRET_KEY,
            algorithm=AUTH_ALGORITHM,
        )
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


def test_register_trims_and_lowercases_email_with_whitespace(client_builder: ClientBuilder) -> None:
    with client_builder(_empty_seed) as client:
        r = client.post(
            "/api/v1/auth/register",
            json={"full_name": "X", "email": "  MiXed@MAIL.com  ", "password": "Longenough1!"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["user"]["email"] == "mixed@mail.com"
        # Duplicate via the trimmed form
        dup = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Y", "email": "mixed@mail.com", "password": "Longenough1!"},
        )
        assert dup.status_code == 409


def test_refresh_stale_token_version_rejected(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_user()) as client:
        bad = create_refresh_token(user_id=1, token_version=999)
        client.cookies.set(REFRESH_COOKIE_NAME, bad)
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 401
