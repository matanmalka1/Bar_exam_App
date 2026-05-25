from fastapi.testclient import TestClient

from .helpers import dev_user


def test_create_session_basic(client: TestClient):
    dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["total_questions"] == 10
    assert body["answered_count"] == 0


def test_create_session_marks_invalidated_questions(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
        },
    ).json()["id"]
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    invalidated = next(q for q in detail["questions"] if q["status"] == "invalidated")
    assert invalidated["invalidation_note"] == "נפסלה"


def test_session_question_order_stable(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    a = client.get(f"/api/v1/practice-sessions/{sid}").json()
    b = client.get(f"/api/v1/practice-sessions/{sid}").json()
    assert [q["position"] for q in a["questions"]] == [q["position"] for q in b["questions"]]
    assert [q["stable_id"] for q in a["questions"]] == [q["stable_id"] for q in b["questions"]]
    assert a["questions"][0]["position"] == 1


def test_get_session_includes_unanswered_as_null(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    assert all(q["answer"] is None for q in detail["questions"])


def test_get_session_detail_returns_persisted_order(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B", "question_count": 5},
    ).json()["id"]
    a = client.get(f"/api/v1/practice-sessions/{sid}").json()
    b = client.get(f"/api/v1/practice-sessions/{sid}").json()
    assert [q["stable_id"] for q in a["questions"]] == [q["stable_id"] for q in b["questions"]]
    assert [q["position"] for q in a["questions"]] == [1, 2, 3, 4, 5]


def test_list_user_sessions_filter(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    sessions = client.get("/api/v1/users/me/sessions?status=active").json()
    assert any(s["id"] == sid for s in sessions)
    completed = client.get("/api/v1/users/me/sessions?status=completed").json()
    assert all(s["id"] != sid for s in completed)


def test_complete_practice_session_has_null_breakdown_and_mistakes(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    body = client.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert body["scorable_questions"] == body["total_questions"]
    assert body["part_breakdown"] is None
    assert body["mistakes"] is None
