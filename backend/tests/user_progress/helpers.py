from fastapi.testclient import TestClient


def dev_user(client: TestClient) -> int:
    response = client.post("/api/v1/users/dev")
    assert response.status_code == 200
    return response.json()["id"]


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
