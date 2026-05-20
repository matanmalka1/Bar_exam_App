from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models.user import User

DEFAULT_EMAIL = "test@example.com"
DEFAULT_PASSWORD = "test-password"
DEFAULT_FULL_NAME = "Test User"


def seed_default_user(session: Session) -> User:
    user = User(
        full_name=DEFAULT_FULL_NAME,
        email=DEFAULT_EMAIL,
        password_hash=hash_password(DEFAULT_PASSWORD),
        is_active=True,
        token_version=0,
    )
    session.add(user)
    session.flush()
    return user


def login(client: TestClient, *, email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def dev_user(client: TestClient) -> int:
    token = login(client)
    client.headers["Authorization"] = f"Bearer {token}"
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    return me.json()["id"]


def seed_mistakes(client: TestClient, user_id: int, wrong_ids: list[str]) -> None:
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    for stable_id in wrong_ids:
        client.post(
            f"/api/v1/practice-sessions/{sid}/answers",
            json={"stable_id": stable_id, "selected_answer": "ב"},
        )
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
