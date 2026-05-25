from fastapi.testclient import TestClient

from .helpers import dev_user, seed_mistakes


def test_mistakes_returns_latest_wrong(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_002", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
    mistakes = client.get("/api/v1/users/me/mistakes").json()
    stable_ids = [m["stable_id"] for m in mistakes]
    assert "2025-04_B_001" in stable_ids
    assert "2025-04_B_002" not in stable_ids


def test_mistakes_resolved_by_later_correct(client: TestClient):
    dev_user(client)
    s1 = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{s1}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    client.post(f"/api/v1/practice-sessions/{s1}/complete")
    s2 = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{s2}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{s2}/complete")
    mistakes = client.get("/api/v1/users/me/mistakes").json()
    stable_ids = [m["stable_id"] for m in mistakes]
    assert "2025-04_B_001" not in stable_ids


def test_mistakes_ignores_active_sessions(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    mistakes = client.get("/api/v1/users/me/mistakes").json()
    assert mistakes == []


def test_mistakes_mode_uses_only_active_mistakes(client: TestClient):
    user_id = dev_user(client)
    seed_mistakes(client, user_id, ["2025-04_B_001", "2025-04_B_002"])
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "mistakes"},
    )
    assert response.status_code == 201
    sid = response.json()["id"]
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    stable_ids = {q["stable_id"] for q in detail["questions"]}
    assert stable_ids == {"2025-04_B_001", "2025-04_B_002"}


def test_mistakes_mode_excludes_resolved_mistakes(client: TestClient):
    user_id = dev_user(client)
    seed_mistakes(client, user_id, ["2025-04_B_001"])
    s2 = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{s2}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{s2}/complete")
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "mistakes"},
    )
    assert response.status_code == 422


def test_mistakes_mode_ignores_active_session_wrong_answers(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "mistakes"},
    )
    assert response.status_code == 422


def test_mistakes_mode_no_pool_returns_422(client: TestClient):
    dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "mistakes"},
    )
    assert response.status_code == 422


def test_mistakes_mode_question_count_limits_pool(client: TestClient):
    user_id = dev_user(client)
    seed_mistakes(client, user_id, ["2025-04_B_001", "2025-04_B_002", "2025-04_B_003"])
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "mistakes", "question_count": 2},
    )
    assert response.status_code == 201
    assert response.json()["total_questions"] == 2


def test_mistakes_mode_question_count_overflow_returns_422(client: TestClient):
    user_id = dev_user(client)
    seed_mistakes(client, user_id, ["2025-04_B_001"])
    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "mistakes", "question_count": 5},
    )
    assert response.status_code == 422


def test_mistakes_mode_rejects_filter_args(client: TestClient):
    user_id = dev_user(client)
    seed_mistakes(client, user_id, ["2025-04_B_001"])
    for payload in (
        {"mode": "mistakes", "exam_date": "2025-04"},
        {"mode": "mistakes", "part": "B"},
    ):
        r = client.post("/api/v1/practice-sessions", json=payload)
        assert r.status_code == 422, payload


def test_mistakes_mode_does_not_treat_invalidated_credit_as_mistake(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
        },
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_006", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{sid}/complete")

    response = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "mistakes"},
    )
    assert response.status_code == 422
