from fastapi.testclient import TestClient

from .helpers import dev_user


def test_question_count_returns_exactly_n_unique(client: TestClient):
    dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
            "question_count": 3,
        },
    )
    assert response.status_code == 201
    sid = response.json()["id"]
    assert response.json()["total_questions"] == 3
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    assert [q["position"] for q in detail["questions"]] == [1, 2, 3]
    stable_ids = [q["stable_id"] for q in detail["questions"]]
    assert len(set(stable_ids)) == 3
    for sid_ in stable_ids:
        assert sid_.startswith("2025-04_B_")


def test_question_count_exceeds_pool_returns_422(client: TestClient):
    dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
            "question_count": 999,
        },
    )
    assert response.status_code == 422


def test_exam_date_restricts_selection(client_multi: TestClient):
    dev_user(client_multi)
    response = client_multi.post(
        "/api/v1/practice-sessions",
        json={
            "mode": "practice",
            "exam_date": "2025-06",
            "part": "B",
            "question_count": 5,
        },
    )
    assert response.status_code == 201
    sid = response.json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    for q in detail["questions"]:
        assert q["stable_id"].startswith("2025-06_B_")


def test_subject_pool_spans_all_exams_when_date_omitted(client_multi: TestClient):
    dev_user(client_multi)
    response = client_multi.post(
        "/api/v1/practice-sessions",
        json={
            "mode": "practice",
            "part": "B",
            "question_count": 40,
        },
    )
    assert response.status_code == 201
    sid = response.json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    exam_prefixes = {q["stable_id"].rsplit("_", 2)[0] for q in detail["questions"]}
    assert len(exam_prefixes) > 1
    for q in detail["questions"]:
        assert "_B_" in q["stable_id"]


def test_second_session_prefers_unseen(client_multi: TestClient):
    dev_user(client_multi)
    s1 = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "part": "B", "question_count": 40},
    ).json()
    s2 = client_multi.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "part": "B", "question_count": 40},
    ).json()
    d1 = client_multi.get(f"/api/v1/practice-sessions/{s1['id']}").json()
    d2 = client_multi.get(f"/api/v1/practice-sessions/{s2['id']}").json()
    ids1 = {q["stable_id"] for q in d1["questions"]}
    ids2 = {q["stable_id"] for q in d2["questions"]}
    assert ids1 != ids2
    assert ids1.isdisjoint(ids2)


def test_unseen_pool_insufficient_fills_from_seen(client: TestClient):
    dev_user(client)
    s1 = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B", "question_count": 7},
    ).json()
    d1 = client.get(f"/api/v1/practice-sessions/{s1['id']}").json()
    seen = {q["stable_id"] for q in d1["questions"]}

    s2 = client.post(
        "/api/v1/practice-sessions",
        json={"mode": "practice", "exam_date": "2025-04", "part": "B", "question_count": 5},
    ).json()
    d2 = client.get(f"/api/v1/practice-sessions/{s2['id']}").json()
    ids2 = [q["stable_id"] for q in d2["questions"]]
    assert len(ids2) == 5
    assert len(set(ids2)) == 5
    overlap = seen & set(ids2)
    assert len(overlap) == 3
