import sys
from collections.abc import Generator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.question import Question


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
        session.add_all(
            [
                make_question(date(2025, 4, 1), "B", number)
                for number in range(1, 41)
            ]
        )
        session.add(make_question(date(2025, 4, 1), "C", 1, correct_answer="B"))
        session.add_all(
            [
                make_question(date(2025, 12, 1), "B", number)
                for number in range(1, 20)
            ]
        )
        session.add(
            make_question(
                date(2025, 12, 1),
                "B",
                20,
                status="invalidated",
                correct_answer=None,
                invalidation_note="השאלה נפסלה לפי מפתח התשובות הרשמי",
            )
        )
        session.add_all(
            [
                make_question(date(2025, 12, 1), "B", number)
                for number in range(21, 41)
            ]
        )
        session.commit()

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_database_is_reachable(client: TestClient):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_database_is_unavailable(client: TestClient):
    class UnavailableSession:
        def execute(self, statement: object) -> None:
            raise SQLAlchemyError("unavailable")

    def override_get_session() -> Generator[UnavailableSession, None, None]:
        yield UnavailableSession()

    app.dependency_overrides[get_session] = override_get_session

    response = client.get("/ready")

    assert response.status_code == 503


def test_cors_allows_vite_localhost(client: TestClient):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_get_exams_returns_labels_and_active_counts(client: TestClient):
    response = client.get("/api/v1/exams")

    assert response.status_code == 200
    assert response.json() == [
        {
            "exam_date": "2025-04",
            "part": "B",
            "part_name": "דין דיוני",
            "label": "אפריל 2025",
            "question_count": 40,
        },
        {
            "exam_date": "2025-04",
            "part": "C",
            "part_name": "דין מהותי",
            "label": "אפריל 2025",
            "question_count": 1,
        },
        {
            "exam_date": "2025-12",
            "part": "B",
            "part_name": "דין דיוני",
            "label": "דצמבר 2025",
            "question_count": 39,
        },
    ]


def test_get_questions_returns_40_ordered_questions(client: TestClient):
    response = client.get("/api/v1/questions?exam_date=2025-04&part=B")

    assert response.status_code == 200
    questions = response.json()
    assert len(questions) == 40
    assert [question["number"] for question in questions] == list(range(1, 41))


def test_get_questions_returns_hebrew_answer_and_options(client: TestClient):
    response = client.get("/api/v1/questions?exam_date=2025-04&part=B")

    assert response.status_code == 200
    question = response.json()[0]
    assert question["correct_answer"] == "א"
    assert question["options"] == {
        "א": "אפשרות א",
        "ב": "אפשרות ב",
        "ג": "אפשרות ג",
        "ד": "אפשרות ד",
    }


def test_get_questions_for_missing_exam_returns_empty_list(client: TestClient):
    response = client.get("/api/v1/questions?exam_date=2099-12&part=B")

    assert response.status_code == 200
    assert response.json() == []


def test_get_questions_rejects_invalid_exam_date_month(client: TestClient):
    response = client.get("/api/v1/questions?exam_date=9999-99&part=B")

    assert response.status_code == 422


def test_get_questions_requires_params(client: TestClient):
    response = client.get("/api/v1/questions")

    assert response.status_code == 422


def test_get_questions_rejects_invalid_part(client: TestClient):
    response = client.get("/api/v1/questions?exam_date=2025-04&part=X")

    assert response.status_code == 422


def test_get_question_by_stable_id(client: TestClient):
    response = client.get("/api/v1/questions/2025-04_B_001")

    assert response.status_code == 200
    question = response.json()
    assert question["stable_id"] == "2025-04_B_001"
    assert question["number"] == 1


def test_get_question_rejects_invalid_stable_id_format(client: TestClient):
    response = client.get("/api/v1/questions/does-not-exist")

    assert response.status_code == 422


def test_get_question_returns_404_for_unknown_valid_stable_id(client: TestClient):
    response = client.get("/api/v1/questions/2026-05_B_001")

    assert response.status_code == 404
    assert response.json() == {"detail": "question not found"}


def test_invalidated_question_has_no_correct_answer_and_note(client: TestClient):
    response = client.get("/api/v1/questions/2025-12_B_020")

    assert response.status_code == 200
    question = response.json()
    assert question["status"] == "invalidated"
    assert question["correct_answer"] is None
    assert question["invalidation_note"] == "השאלה נפסלה לפי מפתח התשובות הרשמי"
