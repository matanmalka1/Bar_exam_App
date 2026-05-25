import pytest
from fastapi.testclient import TestClient

from .helpers import dev_user


def test_simulation_mode_rejects_exam_date(client_exam: TestClient):
    dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation", "exam_date": "2025-04"},
    )
    assert r.status_code == 422


def test_simulation_mode_rejects_part(client_exam: TestClient):
    dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation", "part": "B"},
    )
    assert r.status_code == 422


def test_simulation_mode_rejects_question_count(client_exam: TestClient):
    dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation", "question_count": 50},
    )
    assert r.status_code == 422


def test_simulation_creates_80_questions_40b_40c(client_exam: TestClient):
    dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["total_questions"] == 80
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    parts = [q["stable_id"].rsplit("_", 2)[1] for q in detail["questions"]]
    assert parts.count("B") == 40
    assert parts.count("C") == 40


def test_simulation_grouped_b_then_c_order(client_exam: TestClient):
    dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    parts = [q["stable_id"].rsplit("_", 2)[1] for q in detail["questions"]]
    assert all(p == "B" for p in parts[:40])
    assert all(p == "C" for p in parts[40:])


def test_simulation_can_include_invalidated(client_exam: TestClient):
    dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    assert detail["total_questions"] == 80
    assert {q["status"] for q in detail["questions"]} <= {"active", "invalidated"}


def test_simulation_pool_spans_multiple_exam_dates(client_exam: TestClient):
    dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    prefixes = {q["stable_id"].rsplit("_", 2)[0] for q in detail["questions"]}
    assert len(prefixes) > 1


def test_simulation_insufficient_pool_returns_422(client_exam_insufficient: TestClient):
    dev_user(client_exam_insufficient)
    r = client_exam_insufficient.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    )
    assert r.status_code == 422


def test_simulation_completion_returns_part_breakdown_and_mistakes(client_exam: TestClient):
    dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    b_q = next(q for q in detail["questions"] if "_B_" in q["stable_id"])
    client_exam.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": b_q["stable_id"], "selected_answer": "א"},
    )
    body = client_exam.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    active_questions = [q for q in detail["questions"] if q["status"] == "active"]
    invalidated_questions = [q for q in detail["questions"] if q["status"] == "invalidated"]
    answered_active_correct = 1 if b_q["status"] == "active" else 0
    assert set(body["part_breakdown"].keys()) == {"B", "C"}
    assert body["scorable_questions"] == 80
    assert body["part_breakdown"]["B"]["total"] == 40
    assert body["part_breakdown"]["C"]["total"] == 40
    assert body["correct_count"] == len(invalidated_questions) + answered_active_correct
    assert body["mistakes"] is not None
    assert len(body["mistakes"]) == len(active_questions) - answered_active_correct
    sample = body["mistakes"][0]
    assert sample["correct_answer"] is not None
    assert sample["reference"] == "סימוכין רשמי"


def test_simulation_unanswered_counts_as_incorrect(client_exam: TestClient):
    dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"mode": "simulation"},
    ).json()["id"]
    body = client_exam.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert body["total_questions"] == 80
    assert body["scorable_questions"] == 80
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    invalidated_count = sum(1 for q in detail["questions"] if q["status"] == "invalidated")
    assert body["correct_count"] == invalidated_count
    assert float(body["score_percent"]) == pytest.approx(invalidated_count / 80 * 100, abs=0.01)
