from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from .helpers import auth_as, create_test_user, dev_user, seed_mistakes

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(client_builder, make_question):
    def seed_database(session: Session) -> None:
        session.add_all([make_question(date(2025, 4, 1), "B", n) for n in range(1, 6)])
        session.add_all([make_question(date(2025, 4, 1), "C", n) for n in range(1, 4)])

    with client_builder(seed_database) as test_client:
        yield test_client


@pytest.fixture
def client_two_users(client_builder, make_question):
    def seed_database(session: Session) -> None:
        session.add_all([make_question(date(2025, 4, 1), "B", n) for n in range(1, 6)])
        session.add_all([make_question(date(2025, 4, 1), "C", n) for n in range(1, 4)])
        create_test_user(session, email="other@example.com", password="Other-pass1!")

    with client_builder(seed_database) as test_client:
        yield test_client


# ── auth ──────────────────────────────────────────────────────────────────────

def test_reset_data_requires_auth(client: TestClient):
    r = client.delete("/api/v1/users/me/data")
    assert r.status_code == 401


# ── cascade delete ────────────────────────────────────────────────────────────

def test_reset_data_deletes_sessions(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]

    r = client.delete("/api/v1/users/me/data")
    assert r.status_code == 204

    sessions = client.get("/api/v1/users/me/sessions").json()
    assert sessions == []

    r2 = client.get(f"/api/v1/practice-sessions/{sid}")
    assert r2.status_code == 404


def test_reset_data_deletes_answers_and_mistakes(client: TestClient):
    user_id = dev_user(client)
    seed_mistakes(client, user_id, ["2025-04_B_001", "2025-04_B_002"])

    mistakes_before = client.get("/api/v1/users/me/mistakes").json()
    assert len(mistakes_before) == 2

    client.delete("/api/v1/users/me/data")

    mistakes_after = client.get("/api/v1/users/me/mistakes").json()
    assert mistakes_after == []


def test_reset_data_deletes_bookmarks(client: TestClient):
    dev_user(client)
    client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    client.post("/api/v1/users/me/bookmarks/2025-04_B_002")

    bookmarks_before = client.get("/api/v1/users/me/bookmarks").json()
    assert len(bookmarks_before) == 2

    client.delete("/api/v1/users/me/data")

    bookmarks_after = client.get("/api/v1/users/me/bookmarks").json()
    assert bookmarks_after == []


def test_reset_data_returns_204(client: TestClient):
    dev_user(client)
    r = client.delete("/api/v1/users/me/data")
    assert r.status_code == 204
    assert r.content == b""


def test_reset_data_is_idempotent(client: TestClient):
    dev_user(client)
    assert client.delete("/api/v1/users/me/data").status_code == 204
    assert client.delete("/api/v1/users/me/data").status_code == 204


# ── isolation ─────────────────────────────────────────────────────────────────

def test_reset_data_does_not_affect_other_user(client_two_users: TestClient):
    # user A creates a session and bookmark
    dev_user(client_two_users)
    client_two_users.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    )
    client_two_users.post("/api/v1/users/me/bookmarks/2025-04_B_001")

    # user B creates a session and bookmark
    auth_as(client_two_users, email="other@example.com", password="Other-pass1!")
    client_two_users.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    )
    client_two_users.post("/api/v1/users/me/bookmarks/2025-04_B_002")

    # user A resets their data
    auth_as(client_two_users)
    client_two_users.delete("/api/v1/users/me/data")
    assert client_two_users.get("/api/v1/users/me/sessions").json() == []

    # user B's data is untouched
    auth_as(client_two_users, email="other@example.com", password="Other-pass1!")
    assert len(client_two_users.get("/api/v1/users/me/sessions").json()) == 1
    assert len(client_two_users.get("/api/v1/users/me/bookmarks").json()) == 1
