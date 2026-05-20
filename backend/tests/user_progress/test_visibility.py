from fastapi.testclient import TestClient

from .helpers import dev_user


def test_practice_unanswered_hides_answer_key_in_detail(client: TestClient):
    dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    answered = next(q for q in detail["questions"] if q["stable_id"] == "2025-04_B_001")
    unanswered = next(q for q in detail["questions"] if q["stable_id"] != "2025-04_B_001")
    assert answered["correct_answer"] == "א"
    assert answered["reference"] == "סימוכין רשמי"
    assert unanswered["correct_answer"] is None
    assert unanswered["reference"] is None


def test_simulation_mode_hides_answer_key_during_active(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    first_stable_id = detail["questions"][0]["stable_id"]
    r = client_multi.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": first_stable_id, "selected_answer": "ב"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "correct_answer" not in body
    assert "reference" not in body
    assert "is_correct" not in body

    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    q1 = next(q for q in detail["questions"] if q["stable_id"] == first_stable_id)
    assert q1["correct_answer"] is None
    assert q1["reference"] is None


def test_simulation_mode_exposes_answer_key_after_complete(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    first_stable_id = detail["questions"][0]["stable_id"]
    client_multi.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": first_stable_id, "selected_answer": "א"},
    )
    client_multi.post(f"/api/v1/practice-sessions/{sid}/complete")
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    q1 = next(q for q in detail["questions"] if q["stable_id"] == first_stable_id)
    assert q1["correct_answer"] is not None
    assert q1["reference"] == "סימוכין רשמי"


def test_simulation_active_hides_is_correct_in_session_detail(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    first_stable_id = detail["questions"][0]["stable_id"]
    client_multi.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": first_stable_id, "selected_answer": "ב"},
    )
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    q1 = next(q for q in detail["questions"] if q["stable_id"] == first_stable_id)
    assert q1["answer"]["selected_answer"] == "ב"
    assert q1["answer"]["is_correct"] is None


def test_simulation_completed_exposes_is_correct_in_session_detail(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    b_question = next(q for q in detail["questions"] if "_B_" in q["stable_id"])
    client_multi.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": b_question["stable_id"], "selected_answer": "א"},
    )
    client_multi.post(f"/api/v1/practice-sessions/{sid}/complete")
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    q1 = next(q for q in detail["questions"] if q["stable_id"] == b_question["stable_id"])
    assert q1["answer"]["is_correct"] is True
