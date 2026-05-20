from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models.question import Question
from app.models.user import User

ClientBuilder = Callable[[Callable[[Session], None]], AbstractContextManager[TestClient]]
QuestionFactory = Callable[..., Question]

PASSWORD = "iso-pass"
ALICE = "alice@example.com"
BOB = "bob@example.com"


def _make_question(number: int, *, part: str = "B", correct: str = "A") -> Question:
    return Question(
        stable_id=f"2025-04_{part}_{number:03d}",
        exam_date=date(2025, 4, 1),
        part=part,
        number=number,
        body=f"גוף שאלה {number}",
        option_a="א",
        option_b="ב",
        option_c="ג",
        option_d="ד",
        status="active",
        correct_answer=correct,
        reference="ref",
    )


def _seed_two_users(session: Session) -> None:
    session.add_all(
        [
            User(full_name="Alice", email=ALICE, password_hash=hash_password(PASSWORD)),
            User(full_name="Bob", email=BOB, password_hash=hash_password(PASSWORD)),
        ]
    )
    session.add_all([_make_question(n) for n in range(1, 6)])


def _login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_my_sessions_unauthenticated_returns_401(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_two_users) as client:
        assert client.get("/api/v1/users/me/sessions").status_code == 401
        assert client.get("/api/v1/users/me/mistakes").status_code == 401
        assert client.get("/api/v1/users/me/bookmarks").status_code == 401
        assert client.get("/api/v1/users/me/stats/overview").status_code == 401
        assert client.post("/api/v1/practice-sessions", json={"mode": "practice"}).status_code == 401


def test_session_create_uses_token_user_not_payload(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_two_users) as client:
        alice = _login(client, ALICE)
        # Even if client tries to pass user_id, schema rejects unknown fields.
        bad = client.post(
            "/api/v1/practice-sessions",
            json={"mode": "practice", "user_id": 9999, "part": "B"},
            headers=alice,
        )
        assert bad.status_code == 422  # extra field forbidden

        ok = client.post(
            "/api/v1/practice-sessions",
            json={"mode": "practice", "part": "B"},
            headers=alice,
        )
        assert ok.status_code == 201
        session_id = ok.json()["id"]

        sessions = client.get("/api/v1/users/me/sessions", headers=alice).json()
        assert [s["id"] for s in sessions] == [session_id]
        assert sessions[0]["user_id"] != 9999


def test_user_cannot_access_other_users_session(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_two_users) as client:
        alice = _login(client, ALICE)
        session_id = client.post(
            "/api/v1/practice-sessions",
            json={"mode": "practice", "part": "B"},
            headers=alice,
        ).json()["id"]

        bob = _login(client, BOB)
        # Detail: 404 (not 403) so we don't leak session existence.
        assert client.get(f"/api/v1/practice-sessions/{session_id}", headers=bob).status_code == 404
        assert (
            client.post(
                f"/api/v1/practice-sessions/{session_id}/answers",
                json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
                headers=bob,
            ).status_code
            == 404
        )
        assert client.post(f"/api/v1/practice-sessions/{session_id}/complete", headers=bob).status_code == 404

        # Bob's own session list is empty.
        assert client.get("/api/v1/users/me/sessions", headers=bob).json() == []


def test_bookmarks_scoped_to_current_user(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_two_users) as client:
        alice = _login(client, ALICE)
        client.post("/api/v1/users/me/bookmarks/2025-04_B_001", headers=alice)

        bob = _login(client, BOB)
        assert client.get("/api/v1/users/me/bookmarks", headers=bob).json() == []

        alice_bookmarks = client.get("/api/v1/users/me/bookmarks", headers=alice).json()
        assert len(alice_bookmarks) == 1
        assert alice_bookmarks[0]["stable_id"] == "2025-04_B_001"


def test_stats_and_mistakes_scoped_to_current_user(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_two_users) as client:
        alice = _login(client, ALICE)
        sid = client.post(
            "/api/v1/practice-sessions",
            json={"mode": "practice", "part": "B"},
            headers=alice,
        ).json()["id"]
        client.post(
            f"/api/v1/practice-sessions/{sid}/answers",
            json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
            headers=alice,
        )
        client.post(f"/api/v1/practice-sessions/{sid}/complete", headers=alice)

        alice_stats = client.get("/api/v1/users/me/stats/overview", headers=alice).json()
        assert alice_stats["total_answered"] == 1
        assert client.get("/api/v1/users/me/mistakes", headers=alice).json() != []

        bob = _login(client, BOB)
        bob_stats = client.get("/api/v1/users/me/stats/overview", headers=bob).json()
        assert bob_stats["total_answered"] == 0
        assert client.get("/api/v1/users/me/mistakes", headers=bob).json() == []


def test_no_dev_user_endpoint(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_two_users) as client:
        assert client.post("/api/v1/users/dev").status_code == 404


def test_legacy_user_id_path_routes_gone(client_builder: ClientBuilder) -> None:
    with client_builder(_seed_two_users) as client:
        alice = _login(client, ALICE)
        # Old style paths should 404 — only /me variants exist.
        assert client.get("/api/v1/users/1/sessions", headers=alice).status_code == 404
        assert client.get("/api/v1/users/1/stats/overview", headers=alice).status_code == 404
        assert client.get("/api/v1/users/1/bookmarks", headers=alice).status_code == 404
