from fastapi.testclient import TestClient

from .helpers import dev_user


def test_exam_mode_requires_exam_date(client_multi: TestClient):
    dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam"},
    )
    assert r.status_code == 422


def test_exam_mode_rejects_question_count(client_multi: TestClient):
    dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-04", "question_count": 50},
    )
    assert r.status_code == 422


def test_exam_mode_rejects_include_invalidated_true(client_multi: TestClient):
    dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-04", "include_invalidated": True},
    )
    assert r.status_code == 422


def test_exam_full_returns_40b_40c_from_single_exam_date(client_multi: TestClient):
    dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-06"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["total_questions"] == 80
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    for q in detail["questions"]:
        assert q["stable_id"].startswith("2025-06_")
    parts = [q["stable_id"].rsplit("_", 2)[1] for q in detail["questions"]]
    assert parts.count("B") == 40
    assert parts.count("C") == 40


def test_exam_part_b_returns_only_b_from_exam_date(client_multi: TestClient):
    dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-12", "part": "B"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["total_questions"] == 40
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    for q in detail["questions"]:
        assert q["stable_id"].startswith("2025-12_B_")
    invalidated = next(q for q in detail["questions"] if q["stable_id"] == "2025-12_B_020")
    assert invalidated["status"] == "invalidated"


def test_exam_does_not_mix_exam_dates(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-04"},
    ).json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    prefixes = {q["stable_id"].rsplit("_", 2)[0] for q in detail["questions"]}
    assert prefixes == {"2025-04"}


def test_exam_insufficient_total_pool_returns_422(client_exam_insufficient: TestClient):
    dev_user(client_exam_insufficient)
    r = client_exam_insufficient.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-04"},
    )
    assert r.status_code == 422


def test_exam_hides_answer_key_during_active(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-04"},
    ).json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    first_stable_id = detail["questions"][0]["stable_id"]
    r = client_multi.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": first_stable_id, "selected_answer": "ב"},
    )
    body = r.json()
    assert "correct_answer" not in body
    assert "reference" not in body


def test_exam_exposes_answer_key_after_complete(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-04"},
    ).json()["id"]
    client_multi.post(f"/api/v1/practice-sessions/{sid}/complete")
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    for q in detail["questions"]:
        assert q["correct_answer"] is not None
        assert q["reference"] == "סימוכין רשמי"


def test_exam_completion_returns_part_breakdown_and_mistakes(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-04"},
    ).json()["id"]
    body = client_multi.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert body["total_questions"] == 80
    assert body["scorable_questions"] == 80
    assert set(body["part_breakdown"].keys()) == {"B", "C"}
    assert body["part_breakdown"]["B"]["total"] == 40
    assert body["part_breakdown"]["C"]["total"] == 40
    assert body["mistakes"] is not None
    assert len(body["mistakes"]) == 80


def test_exam_part_b_completion_breakdown_only_b(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    body = client_multi.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert set(body["part_breakdown"].keys()) == {"B"}
    assert body["part_breakdown"]["B"]["total"] == 40


def test_exam_invalidated_question_excluded_from_score_and_mistakes(client_multi: TestClient):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-12", "part": "B"},
    ).json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    invalidated = next(q for q in detail["questions"] if q["stable_id"] == "2025-12_B_020")
    assert invalidated["status"] == "invalidated"

    for q in detail["questions"]:
        if q["status"] == "active":
            client_multi.post(
                f"/api/v1/practice-sessions/{sid}/answers",
                json={"stable_id": q["stable_id"], "selected_answer": "א"},
            )

    body = client_multi.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert body["total_questions"] == 40
    assert body["scorable_questions"] == 39
    assert body["correct_count"] == 39
    assert float(body["score_percent"]) == 100.0
    assert body["part_breakdown"]["B"]["total"] == 39
    assert body["part_breakdown"]["B"]["answered"] == 39
    assert body["part_breakdown"]["B"]["correct"] == 39
    assert body["mistakes"] == []

    completed_detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    completed_invalidated = next(q for q in completed_detail["questions"] if q["stable_id"] == "2025-12_B_020")
    assert completed_invalidated["status"] == "invalidated"
    assert completed_invalidated["correct_answer"] is None


def test_answer_invalidated_exam_question_returns_422_and_does_not_increment_answered_count(
    client_multi: TestClient,
):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-12", "part": "B"},
    ).json()["id"]
    before = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    assert before["answered_count"] == 0

    response = client_multi.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-12_B_020", "selected_answer": "א"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "cannot answer invalidated question"

    after = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    assert after["answered_count"] == 0
    invalidated = next(q for q in after["questions"] if q["stable_id"] == "2025-12_B_020")
    assert invalidated["answer"] is None


def test_completion_still_excludes_invalidated_from_score_and_mistakes_after_rejected_answer(
    client_multi: TestClient,
):
    dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "exam", "exam_date": "2025-12", "part": "B"},
    ).json()["id"]
    client_multi.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-12_B_020", "selected_answer": "א"},
    )

    body = client_multi.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert body["total_questions"] == 40
    assert body["scorable_questions"] == 39
    assert body["answered_count"] == 0
    assert body["correct_count"] == 0
    assert len(body["mistakes"]) == 39
    assert all(item["stable_id"] != "2025-12_B_020" for item in body["mistakes"])

    mistakes = client_multi.get("/api/v1/users/me/mistakes").json()
    assert all(item["stable_id"] != "2025-12_B_020" for item in mistakes)
