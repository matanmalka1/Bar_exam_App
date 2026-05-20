import random
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.question import Question
from app.services import practice_session_service

QuestionFactory = Callable[..., Question]
ClientBuilder = Callable[[Callable[[Session], None]], AbstractContextManager[TestClient]]


@pytest.fixture(autouse=True)
def deterministic_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(practice_session_service, "_make_rng", lambda: random.Random(1234))


@pytest.fixture
def client(
    client_builder: ClientBuilder,
    make_question: QuestionFactory,
) -> Generator[TestClient, None, None]:
    def seed_database(session: Session) -> None:
        session.add_all([make_question(date(2025, 4, 1), "B", n) for n in range(1, 6)])
        session.add(
            make_question(
                date(2025, 4, 1),
                "B",
                6,
                status="invalidated",
                correct_answer=None,
                invalidation_note="נפסלה",
            )
        )
        session.add_all([make_question(date(2025, 4, 1), "B", n, correct_answer="B") for n in range(7, 11)])
        session.add_all([make_question(date(2025, 4, 1), "C", n, correct_answer="C") for n in range(1, 4)])

    with client_builder(seed_database) as test_client:
        yield test_client


@pytest.fixture
def client_multi(
    client_builder: ClientBuilder,
    make_question: QuestionFactory,
) -> Generator[TestClient, None, None]:
    def seed_database(session: Session) -> None:
        for exam in (date(2025, 4, 1), date(2025, 6, 1), date(2025, 12, 1)):
            session.add_all(
                [
                    make_question(
                        exam,
                        "B",
                        n,
                        status="invalidated",
                        correct_answer=None,
                        invalidation_note="נפסלה",
                    )
                    if exam == date(2025, 12, 1) and n == 20
                    else make_question(exam, "B", n)
                    for n in range(1, 41)
                ]
            )
            session.add_all([make_question(exam, "C", n, correct_answer="C") for n in range(1, 41)])

    with client_builder(seed_database) as test_client:
        yield test_client


@pytest.fixture
def client_exam(
    client_builder: ClientBuilder,
    make_question: QuestionFactory,
) -> Generator[TestClient, None, None]:
    """45 active B + 45 active C across 2 exam dates, plus 5 invalidated of each part."""

    def seed_database(session: Session) -> None:
        # 2025-04: 25 active B, 25 active C, 5 invalidated B, 5 invalidated C
        session.add_all([make_question(date(2025, 4, 1), "B", n) for n in range(1, 26)])
        session.add_all([make_question(date(2025, 4, 1), "C", n, correct_answer="C") for n in range(1, 26)])
        session.add_all(
            [
                make_question(
                    date(2025, 4, 1),
                    "B",
                    n,
                    status="invalidated",
                    correct_answer=None,
                    invalidation_note="נפסלה",
                )
                for n in range(26, 31)
            ]
        )
        session.add_all(
            [
                make_question(
                    date(2025, 4, 1),
                    "C",
                    n,
                    status="invalidated",
                    correct_answer=None,
                    invalidation_note="נפסלה",
                )
                for n in range(26, 31)
            ]
        )
        # 2025-06: 20 active B, 20 active C
        session.add_all([make_question(date(2025, 6, 1), "B", n) for n in range(1, 21)])
        session.add_all([make_question(date(2025, 6, 1), "C", n, correct_answer="C") for n in range(1, 21)])

    with client_builder(seed_database) as test_client:
        yield test_client


@pytest.fixture
def client_exam_insufficient(
    client_builder: ClientBuilder,
    make_question: QuestionFactory,
) -> Generator[TestClient, None, None]:
    """39 total B, 40 total C — exam should fail with 422."""

    def seed_database(session: Session) -> None:
        session.add_all([make_question(date(2025, 4, 1), "B", n) for n in range(1, 40)])
        session.add_all([make_question(date(2025, 4, 1), "C", n, correct_answer="C") for n in range(1, 41)])

    with client_builder(seed_database) as test_client:
        yield test_client


def _dev_user(client: TestClient) -> int:
    response = client.post("/api/v1/users/dev")
    assert response.status_code == 200
    return response.json()["id"]


def test_dev_user_idempotent(client: TestClient):
    r1 = client.post("/api/v1/users/dev")
    r2 = client.post("/api/v1/users/dev")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["user_key"] == "dev"


def test_create_session_basic(client: TestClient):
    user_id = _dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={
            "user_id": user_id,
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["total_questions"] == 9  # 10 part-B questions minus 1 invalidated
    assert body["answered_count"] == 0


def test_create_session_includes_invalidated_when_requested(client: TestClient):
    user_id = _dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={
            "user_id": user_id,
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
            "include_invalidated": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["total_questions"] == 10


def test_session_question_order_stable(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    a = client.get(f"/api/v1/practice-sessions/{sid}").json()
    b = client.get(f"/api/v1/practice-sessions/{sid}").json()
    assert [q["position"] for q in a["questions"]] == [q["position"] for q in b["questions"]]
    assert [q["stable_id"] for q in a["questions"]] == [q["stable_id"] for q in b["questions"]]
    assert a["questions"][0]["position"] == 1


def test_submit_answer_practice_mode(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
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
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
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
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
    r = client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    assert r.status_code == 409


def test_submit_answer_for_question_not_in_session(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    r = client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_C_001", "selected_answer": "א"},
    )
    assert r.status_code == 422


def test_complete_session_score(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    # 5 correct (A → א) and 4 from 7..10 are correct=B, plus invalidated excluded.
    # Answer first 3 correctly (א), rest wrong.
    for n in range(1, 4):
        client.post(
            f"/api/v1/practice-sessions/{sid}/answers",
            json={"stable_id": f"2025-04_B_{n:03d}", "selected_answer": "א"},
        )
    r = client.post(f"/api/v1/practice-sessions/{sid}/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["total_questions"] == 9
    assert body["scorable_questions"] == 9
    assert body["correct_count"] == 3
    assert float(body["score_percent"]) == pytest.approx(33.33, rel=0, abs=0.01)


def test_complete_twice_returns_409(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
    r = client.post(f"/api/v1/practice-sessions/{sid}/complete")
    assert r.status_code == 409


def test_get_session_includes_unanswered_as_null(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    assert all(q["answer"] is None for q in detail["questions"])


def test_simulation_mode_hides_answer_key_during_active(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
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
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
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


def test_mistakes_returns_latest_wrong(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    # Answer Q1 wrong, Q2 correct.
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_002", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
    mistakes = client.get(f"/api/v1/users/{user_id}/mistakes").json()
    stable_ids = [m["stable_id"] for m in mistakes]
    assert "2025-04_B_001" in stable_ids
    assert "2025-04_B_002" not in stable_ids


def test_mistakes_resolved_by_later_correct(client: TestClient):
    user_id = _dev_user(client)
    s1 = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{s1}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    client.post(f"/api/v1/practice-sessions/{s1}/complete")
    s2 = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{s2}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{s2}/complete")
    mistakes = client.get(f"/api/v1/users/{user_id}/mistakes").json()
    stable_ids = [m["stable_id"] for m in mistakes]
    assert "2025-04_B_001" not in stable_ids


def test_bookmark_idempotent(client: TestClient):
    user_id = _dev_user(client)
    r1 = client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    r2 = client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    assert r1.status_code == 200
    assert r2.status_code == 200
    bookmarks = client.get(f"/api/v1/users/{user_id}/bookmarks").json()
    assert len([b for b in bookmarks if b["stable_id"] == "2025-04_B_001"]) == 1


def test_bookmark_delete_idempotent(client: TestClient):
    user_id = _dev_user(client)
    r1 = client.delete(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    assert r1.status_code == 200
    client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    r2 = client.delete(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    assert r2.status_code == 200
    assert r2.json() == {"removed": True}


def test_bookmarks_list_includes_correct_answer(client: TestClient):
    user_id = _dev_user(client)
    client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    bookmarks = client.get(f"/api/v1/users/{user_id}/bookmarks").json()
    assert len(bookmarks) == 1
    assert bookmarks[0]["correct_answer"] == "א"
    assert bookmarks[0]["reference"] == "סימוכין רשמי"


def test_list_user_sessions_filter(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    sessions = client.get(f"/api/v1/users/{user_id}/sessions?status=active").json()
    assert any(s["id"] == sid for s in sessions)
    completed = client.get(f"/api/v1/users/{user_id}/sessions?status=completed").json()
    assert all(s["id"] != sid for s in completed)


def test_simulation_active_hides_is_correct_in_session_detail(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
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
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
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


def test_mistakes_ignores_active_sessions(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    mistakes = client.get(f"/api/v1/users/{user_id}/mistakes").json()
    assert mistakes == []


def test_question_count_returns_exactly_n_unique(client: TestClient):
    user_id = _dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={
            "user_id": user_id,
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
    user_id = _dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={
            "user_id": user_id,
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
            "question_count": 999,
        },
    )
    assert response.status_code == 422


def test_exam_date_restricts_selection(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    response = client_multi.post(
        "/api/v1/practice-sessions",
        json={
            "user_id": user_id,
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
    user_id = _dev_user(client_multi)
    response = client_multi.post(
        "/api/v1/practice-sessions",
        json={
            "user_id": user_id,
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
    user_id = _dev_user(client_multi)
    s1 = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "part": "B", "question_count": 40},
    ).json()
    s2 = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "part": "B", "question_count": 40},
    ).json()
    d1 = client_multi.get(f"/api/v1/practice-sessions/{s1['id']}").json()
    d2 = client_multi.get(f"/api/v1/practice-sessions/{s2['id']}").json()
    ids1 = {q["stable_id"] for q in d1["questions"]}
    ids2 = {q["stable_id"] for q in d2["questions"]}
    assert ids1 != ids2
    assert ids1.isdisjoint(ids2)


def test_unseen_pool_insufficient_fills_from_seen(client: TestClient):
    user_id = _dev_user(client)
    s1 = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B", "question_count": 7},
    ).json()
    d1 = client.get(f"/api/v1/practice-sessions/{s1['id']}").json()
    seen = {q["stable_id"] for q in d1["questions"]}

    s2 = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B", "question_count": 5},
    ).json()
    d2 = client.get(f"/api/v1/practice-sessions/{s2['id']}").json()
    ids2 = [q["stable_id"] for q in d2["questions"]]
    assert len(ids2) == 5
    assert len(set(ids2)) == 5
    overlap = seen & set(ids2)
    # only 2 unseen remain (9 active - 7 seen); 3 slots must come from seen.
    assert len(overlap) == 3


def test_get_session_detail_returns_persisted_order(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B", "question_count": 5},
    ).json()["id"]
    a = client.get(f"/api/v1/practice-sessions/{sid}").json()
    b = client.get(f"/api/v1/practice-sessions/{sid}").json()
    assert [q["stable_id"] for q in a["questions"]] == [q["stable_id"] for q in b["questions"]]
    assert [q["position"] for q in a["questions"]] == [1, 2, 3, 4, 5]


def test_no_db_query_in_new_modules():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    new_files = []
    for name in (
        "models/user.py",
        "models/practice_session.py",
        "models/practice_session_question.py",
        "models/user_answer.py",
        "models/bookmarked_question.py",
        "repositories/user_repository.py",
        "repositories/practice_session_repository.py",
        "repositories/answer_repository.py",
        "repositories/bookmark_repository.py",
        "services/user_service.py",
        "services/practice_session_service.py",
        "services/answer_service.py",
        "routers/users.py",
        "routers/practice_sessions.py",
        "schemas/user.py",
        "schemas/session.py",
        "schemas/answer.py",
    ):
        new_files.append(root / name)
    for path in new_files:
        text = path.read_text(encoding="utf-8")
        assert ".query(" not in text, f"{path} uses db.query()"


# ---------------------------------------------------------------------------
# Per-question visibility (practice)
# ---------------------------------------------------------------------------


def test_practice_unanswered_hides_answer_key_in_detail(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
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


# ---------------------------------------------------------------------------
# Mistakes mode — session creation from active mistakes pool
# ---------------------------------------------------------------------------


def _seed_mistakes(client: TestClient, user_id: int, wrong_ids: list[str]) -> None:
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    for stable_id in wrong_ids:
        client.post(
            f"/api/v1/practice-sessions/{sid}/answers",
            json={"stable_id": stable_id, "selected_answer": "ב"},  # wrong (correct is "א")
        )
    client.post(f"/api/v1/practice-sessions/{sid}/complete")


def test_mistakes_mode_uses_only_active_mistakes(client: TestClient):
    user_id = _dev_user(client)
    _seed_mistakes(client, user_id, ["2025-04_B_001", "2025-04_B_002"])
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "mistakes"},
    )
    assert response.status_code == 201
    sid = response.json()["id"]
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    stable_ids = {q["stable_id"] for q in detail["questions"]}
    assert stable_ids == {"2025-04_B_001", "2025-04_B_002"}


def test_mistakes_mode_excludes_resolved_mistakes(client: TestClient):
    user_id = _dev_user(client)
    _seed_mistakes(client, user_id, ["2025-04_B_001"])
    # Now answer it correctly in a second completed session.
    s2 = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{s2}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{s2}/complete")
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "mistakes"},
    )
    assert response.status_code == 422


def test_mistakes_mode_ignores_active_session_wrong_answers(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    # Session not completed — mistake should not count.
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "mistakes"},
    )
    assert response.status_code == 422


def test_mistakes_mode_no_pool_returns_422(client: TestClient):
    user_id = _dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "mistakes"},
    )
    assert response.status_code == 422


def test_mistakes_mode_question_count_limits_pool(client: TestClient):
    user_id = _dev_user(client)
    _seed_mistakes(client, user_id, ["2025-04_B_001", "2025-04_B_002", "2025-04_B_003"])
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "mistakes", "question_count": 2},
    )
    assert response.status_code == 201
    assert response.json()["total_questions"] == 2


def test_mistakes_mode_question_count_overflow_returns_422(client: TestClient):
    user_id = _dev_user(client)
    _seed_mistakes(client, user_id, ["2025-04_B_001"])
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "mistakes", "question_count": 5},
    )
    assert response.status_code == 422


def test_mistakes_mode_rejects_filter_args(client: TestClient):
    user_id = _dev_user(client)
    _seed_mistakes(client, user_id, ["2025-04_B_001"])
    for payload in (
        {"user_id": user_id, "mode": "mistakes", "exam_date": "2025-04"},
        {"user_id": user_id, "mode": "mistakes", "part": "B"},
        {"user_id": user_id, "mode": "mistakes", "include_invalidated": True},
    ):
        r = client.post("/api/v1/practice-sessions", json=payload)
        assert r.status_code == 422, payload


def test_mistakes_mode_excludes_invalidated_questions(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={
            "user_id": user_id,
            "mode": "practice",
            "exam_date": "2025-04",
            "part": "B",
            "include_invalidated": True,
        },
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_006", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{sid}/complete")

    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "mistakes"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Bookmarks mode
# ---------------------------------------------------------------------------


def test_bookmarks_mode_creates_session_from_bookmarks(client: TestClient):
    user_id = _dev_user(client)
    client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_002")
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "bookmarks"},
    )
    assert response.status_code == 201
    sid = response.json()["id"]
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    stable_ids = {q["stable_id"] for q in detail["questions"]}
    assert stable_ids == {"2025-04_B_001", "2025-04_B_002"}


def test_bookmarks_mode_no_pool_returns_422(client: TestClient):
    user_id = _dev_user(client)
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "bookmarks"},
    )
    assert response.status_code == 422


def test_bookmarks_mode_question_count_overflow_returns_422(client: TestClient):
    user_id = _dev_user(client)
    client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    response = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "bookmarks", "question_count": 5},
    )
    assert response.status_code == 422


def test_bookmarks_mode_prefers_unseen_bookmarked_questions(client: TestClient):
    user_id = _dev_user(client)
    for stable_id in ("2025-04_B_001", "2025-04_B_002", "2025-04_B_003"):
        client.post(f"/api/v1/users/{user_id}/bookmarks/{stable_id}")

    first_sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "bookmarks", "question_count": 2},
    ).json()["id"]
    first_detail = client.get(f"/api/v1/practice-sessions/{first_sid}").json()
    first_ids = {q["stable_id"] for q in first_detail["questions"]}

    second_sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "bookmarks", "question_count": 1},
    ).json()["id"]
    second_detail = client.get(f"/api/v1/practice-sessions/{second_sid}").json()
    second_ids = {q["stable_id"] for q in second_detail["questions"]}

    assert second_ids == {"2025-04_B_001", "2025-04_B_002", "2025-04_B_003"} - first_ids


def test_bookmarks_mode_answered_reveals_key(client: TestClient):
    user_id = _dev_user(client)
    client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_002")
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "bookmarks"},
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
    user_id = _dev_user(client)
    client.post(f"/api/v1/users/{user_id}/bookmarks/2025-04_B_001")
    for payload in (
        {"user_id": user_id, "mode": "bookmarks", "exam_date": "2025-04"},
        {"user_id": user_id, "mode": "bookmarks", "part": "B"},
        {"user_id": user_id, "mode": "bookmarks", "include_invalidated": True},
    ):
        r = client.post("/api/v1/practice-sessions", json=payload)
        assert r.status_code == 422, payload


# ---------------------------------------------------------------------------
# Exam mode — official past exam by exam_date
# ---------------------------------------------------------------------------


def test_exam_mode_requires_exam_date(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam"},
    )
    assert r.status_code == 422


def test_exam_mode_rejects_question_count(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04", "question_count": 50},
    )
    assert r.status_code == 422


def test_exam_mode_rejects_include_invalidated_true(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04", "include_invalidated": True},
    )
    assert r.status_code == 422


def test_exam_full_returns_40B_40C_from_single_exam_date(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-06"},
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
    user_id = _dev_user(client_multi)
    r = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-12", "part": "B"},
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
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04"},
    ).json()["id"]
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    prefixes = {q["stable_id"].rsplit("_", 2)[0] for q in detail["questions"]}
    assert prefixes == {"2025-04"}


def test_exam_insufficient_total_pool_returns_422(client_exam_insufficient: TestClient):
    user_id = _dev_user(client_exam_insufficient)
    r = client_exam_insufficient.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04"},
    )
    assert r.status_code == 422


def test_exam_hides_answer_key_during_active(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04"},
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
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04"},
    ).json()["id"]
    client_multi.post(f"/api/v1/practice-sessions/{sid}/complete")
    detail = client_multi.get(f"/api/v1/practice-sessions/{sid}").json()
    for q in detail["questions"]:
        assert q["correct_answer"] is not None
        assert q["reference"] == "סימוכין רשמי"


def test_exam_completion_returns_part_breakdown_and_mistakes(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04"},
    ).json()["id"]
    body = client_multi.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert body["total_questions"] == 80
    assert body["scorable_questions"] == 80
    assert set(body["part_breakdown"].keys()) == {"B", "C"}
    assert body["part_breakdown"]["B"]["total"] == 40
    assert body["part_breakdown"]["C"]["total"] == 40
    assert body["mistakes"] is not None
    assert len(body["mistakes"]) == 80  # all unanswered


def test_exam_part_b_completion_breakdown_only_b(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    body = client_multi.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert set(body["part_breakdown"].keys()) == {"B"}
    assert body["part_breakdown"]["B"]["total"] == 40


def test_exam_invalidated_question_excluded_from_score_and_mistakes(client_multi: TestClient):
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-12", "part": "B"},
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
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-12", "part": "B"},
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
    user_id = _dev_user(client_multi)
    sid = client_multi.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-12", "part": "B"},
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

    mistakes = client_multi.get(f"/api/v1/users/{user_id}/mistakes").json()
    assert all(item["stable_id"] != "2025-12_B_020" for item in mistakes)


# ---------------------------------------------------------------------------
# Simulation mode — mixed 80-question simulation from full pool
# ---------------------------------------------------------------------------


def test_simulation_mode_rejects_exam_date(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation", "exam_date": "2025-04"},
    )
    assert r.status_code == 422


def test_simulation_mode_rejects_part(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation", "part": "B"},
    )
    assert r.status_code == 422


def test_simulation_mode_rejects_question_count(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation", "question_count": 50},
    )
    assert r.status_code == 422


def test_simulation_mode_rejects_include_invalidated_true(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation", "include_invalidated": True},
    )
    assert r.status_code == 422


def test_simulation_creates_80_questions_40B_40C(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    r = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["total_questions"] == 80
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    parts = [q["stable_id"].rsplit("_", 2)[1] for q in detail["questions"]]
    assert parts.count("B") == 40
    assert parts.count("C") == 40


def test_simulation_grouped_b_then_c_order(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
    ).json()["id"]
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    parts = [q["stable_id"].rsplit("_", 2)[1] for q in detail["questions"]]
    assert all(p == "B" for p in parts[:40])
    assert all(p == "C" for p in parts[40:])


def test_simulation_excludes_invalidated(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
    ).json()["id"]
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    for q in detail["questions"]:
        assert q["status"] == "active"


def test_simulation_pool_spans_multiple_exam_dates(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
    ).json()["id"]
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    prefixes = {q["stable_id"].rsplit("_", 2)[0] for q in detail["questions"]}
    assert len(prefixes) > 1


def test_simulation_insufficient_pool_returns_422(client_exam_insufficient: TestClient):
    user_id = _dev_user(client_exam_insufficient)
    r = client_exam_insufficient.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
    )
    assert r.status_code == 422


def test_simulation_completion_returns_part_breakdown_and_mistakes(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
    ).json()["id"]
    detail = client_exam.get(f"/api/v1/practice-sessions/{sid}").json()
    b_q = next(q for q in detail["questions"] if "_B_" in q["stable_id"])
    client_exam.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": b_q["stable_id"], "selected_answer": "א"},
    )
    body = client_exam.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert set(body["part_breakdown"].keys()) == {"B", "C"}
    assert body["scorable_questions"] == 80
    assert body["part_breakdown"]["B"]["total"] == 40
    assert body["part_breakdown"]["C"]["total"] == 40
    assert body["mistakes"] is not None
    assert len(body["mistakes"]) == 79
    sample = body["mistakes"][0]
    assert sample["correct_answer"] is not None
    assert sample["reference"] == "סימוכין רשמי"


def test_simulation_unanswered_counts_as_incorrect(client_exam: TestClient):
    user_id = _dev_user(client_exam)
    sid = client_exam.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "simulation"},
    ).json()["id"]
    body = client_exam.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert body["correct_count"] == 0
    assert float(body["score_percent"]) == 0.0
    assert body["total_questions"] == 80
    assert body["scorable_questions"] == 80


def test_complete_practice_session_has_null_breakdown_and_mistakes(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "practice", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    body = client.post(f"/api/v1/practice-sessions/{sid}/complete").json()
    assert body["scorable_questions"] == body["total_questions"]
    assert body["part_breakdown"] is None
    assert body["mistakes"] is None
