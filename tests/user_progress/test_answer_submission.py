import pytest
from fastapi.testclient import TestClient

from .helpers import dev_user


def test_submit_answer_practice_mode(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    response = client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selected_answer"] == "א"
    assert body["is_correct"] is True
    assert body["correct_answer"] == "א"
    assert "reference" in body


def test_submit_answer_upsert(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    r = client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    assert r.status_code == 200
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    assert detail["answered_count"] == 1
    q1 = next(q for q in detail["questions"] if q["stable_id"] == "2025-04_B_001")
    assert q1["answer"]["selected_answer"] == "א"
    assert q1["answer"]["is_correct"] is True


def test_submit_answer_after_complete_returns_409(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
    r = client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    assert r.status_code == 409


def test_submit_answer_for_question_not_in_session(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    r = client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_C_001", "selected_answer": "א"},
    )
    assert r.status_code == 422


def test_complete_session_score(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    for n in range(1, 4):
        client.post(
            f"/api/v1/practice-sessions/{sid}/answers",
            json={"stable_id": f"2025-04_B_{n:03d}", "selected_answer": "א"},
        )
    r = client.post(f"/api/v1/practice-sessions/{sid}/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["total_questions"] == 10
    assert body["scorable_questions"] == 10
    assert body["correct_count"] == 4
    assert float(body["score_percent"]) == pytest.approx(40.0, rel=0, abs=0.01)


def test_complete_twice_returns_409(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
    r = client.post(f"/api/v1/practice-sessions/{sid}/complete")
    assert r.status_code == 409
