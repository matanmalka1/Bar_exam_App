import random
import sys
from collections.abc import Generator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.question import Question
from app.services import session_service


@pytest.fixture(autouse=True)
def deterministic_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_service, "_make_rng", lambda: random.Random(1234))


def make_question(
    exam_date: date,
    part: str,
    number: int,
    *,
    status: str = "active",
    correct_answer: str | None = "A",
    invalidation_note: str | None = None,
) -> Question:
    return Question(
        stable_id=f"{exam_date.strftime('%Y-%m')}_{part}_{number:03d}",
        exam_date=exam_date,
        part=part,
        number=number,
        body=f"גוף שאלה {number}",
        option_a="אפשרות א",
        option_b="אפשרות ב",
        option_c="אפשרות ג",
        option_d="אפשרות ד",
        status=status,
        correct_answer=correct_answer,
        reference="סימוכין רשמי",
        invalidation_note=invalidation_note,
    )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
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
        session.commit()

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_multi() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for exam in (date(2025, 4, 1), date(2025, 6, 1), date(2025, 12, 1)):
            session.add_all([make_question(exam, "B", n) for n in range(1, 41)])
            session.add_all([make_question(exam, "C", n, correct_answer="C") for n in range(1, 41)])
        session.commit()

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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


def test_exam_mode_hides_answer_key_during_active(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    r = client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "correct_answer" not in body
    assert "reference" not in body
    assert "is_correct" not in body

    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    q1 = next(q for q in detail["questions"] if q["stable_id"] == "2025-04_B_001")
    assert q1["correct_answer"] is None
    assert q1["reference"] is None


def test_exam_mode_exposes_answer_key_after_complete(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    q1 = next(q for q in detail["questions"] if q["stable_id"] == "2025-04_B_001")
    assert q1["correct_answer"] == "א"
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


def test_exam_active_hides_is_correct_in_session_detail(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "ב"},
    )
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    q1 = next(q for q in detail["questions"] if q["stable_id"] == "2025-04_B_001")
    assert q1["answer"]["selected_answer"] == "ב"
    assert q1["answer"]["is_correct"] is None


def test_exam_completed_exposes_is_correct_in_session_detail(client: TestClient):
    user_id = _dev_user(client)
    sid = client.post(
        "/api/v1/practice-sessions",
        json={"user_id": user_id, "mode": "exam", "exam_date": "2025-04", "part": "B"},
    ).json()["id"]
    client.post(
        f"/api/v1/practice-sessions/{sid}/answers",
        json={"stable_id": "2025-04_B_001", "selected_answer": "א"},
    )
    client.post(f"/api/v1/practice-sessions/{sid}/complete")
    detail = client.get(f"/api/v1/practice-sessions/{sid}").json()
    q1 = next(q for q in detail["questions"] if q["stable_id"] == "2025-04_B_001")
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
        "models/user_answer.py",
        "repositories/user_repository.py",
        "repositories/session_repository.py",
        "repositories/answer_repository.py",
        "services/user_service.py",
        "services/session_service.py",
        "services/answer_service.py",
        "routers/users.py",
        "routers/sessions.py",
        "schemas/user.py",
        "schemas/session.py",
        "schemas/answer.py",
    ):
        new_files.append(root / name)
    for path in new_files:
        text = path.read_text(encoding="utf-8")
        assert ".query(" not in text, f"{path} uses db.query()"
