from fastapi.testclient import TestClient

from .helpers import dev_user


def test_bookmark_idempotent(client: TestClient):
    dev_user(client)
    r1 = client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    r2 = client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    assert r1.status_code == 200
    assert r2.status_code == 200
    bookmarks = client.get("/api/v1/users/me/bookmarks").json()
    assert len([b for b in bookmarks if b["stable_id"] == "2025-04_B_001"]) == 1


def test_bookmark_delete_idempotent(client: TestClient):
    dev_user(client)
    r1 = client.delete("/api/v1/users/me/bookmarks/2025-04_B_001")
    assert r1.status_code == 200
    client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    r2 = client.delete("/api/v1/users/me/bookmarks/2025-04_B_001")
    assert r2.status_code == 200
    assert r2.json() == {"removed": True}


def test_bookmarks_list_includes_correct_answer(client: TestClient):
    dev_user(client)
    client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    bookmarks = client.get("/api/v1/users/me/bookmarks").json()
    assert len(bookmarks) == 1
    assert bookmarks[0]["correct_answer"] == "א"
    assert bookmarks[0]["reference"] == "סימוכין רשמי"


def test_bookmarks_mode_creates_session_from_bookmarks(client: TestClient):
    dev_user(client)
    client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    client.post("/api/v1/users/me/bookmarks/2025-04_B_002")
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "bookmarks"},
    )
    assert response.status_code == 201
    sid = response.json()["id"]
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    stable_ids = {q["stable_id"] for q in detail["questions"]}
    assert stable_ids == {"2025-04_B_001", "2025-04_B_002"}


def test_bookmarks_mode_no_pool_returns_422(client: TestClient):
    dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "bookmarks"},
    )
    assert response.status_code == 422


def test_bookmarks_mode_question_count_overflow_returns_422(client: TestClient):
    dev_user(client)
    client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "bookmarks", "question_count": 5},
    )
    assert response.status_code == 422


def test_bookmarks_mode_prefers_unseen_bookmarked_questions(client: TestClient):
    dev_user(client)
    for stable_id in ("2025-04_B_001", "2025-04_B_002", "2025-04_B_003"):
        client.post(f"/api/v1/users/me/bookmarks/{stable_id}")

    first_sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "bookmarks", "question_count": 2},
    ).json()["id"]
    first_detail = client.get(f"/api/v1/practice-sessions/{first_sid}").json()
    first_ids = {q["stable_id"] for q in first_detail["questions"]}

    second_sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "bookmarks", "question_count": 1},
    ).json()["id"]
    second_detail = client.get(f"/api/v1/practice-sessions/{second_sid}").json()
    second_ids = {q["stable_id"] for q in second_detail["questions"]}

    assert second_ids == {"2025-04_B_001", "2025-04_B_002", "2025-04_B_003"} - first_ids


def test_bookmarks_mode_answered_reveals_key(client: TestClient):
    dev_user(client)
    client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    client.post("/api/v1/users/me/bookmarks/2025-04_B_002")
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "bookmarks"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    answered = next(q for q in detail["questions"] if q["stable_id"] == "2025-04_B_001")
    unanswered = next(q for q in detail["questions"] if q["stable_id"] == "2025-04_B_002")
    assert answered["correct_answer"] == "א"
    assert answered["reference"] == "סימוכין רשמי"
    assert unanswered["correct_answer"] is None
    assert unanswered["reference"] is None


def test_bookmarks_mode_rejects_filter_args(client: TestClient):
    dev_user(client)
    client.post("/api/v1/users/me/bookmarks/2025-04_B_001")
    for payload in (
        {"mode": "bookmarks", "exam_date": "2025-04"},
        {"mode": "bookmarks", "part": "B"},
    ):
        r = client.post("/api/v1/practice-sessions", json=payload)
        assert r.status_code == 422, payload
