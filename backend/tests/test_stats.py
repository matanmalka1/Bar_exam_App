from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.practice_session import PracticeSession
from app.models.question import Question
from app.models.user import User
from app.models.user_answer import UserAnswer

QuestionFactory = Callable[..., Question]
ClientBuilder = Callable[[Callable[[Session], None]], AbstractContextManager[TestClient]]

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0)
UNSET = object()


def _user(user_id: int = 1) -> User:
    return User(
        id=user_id,
        full_name=f"משתמש {user_id}",
        email=f"user-{user_id}@example.com",
        password_hash="!",
    )


def _session(
    session_id: int,
    *,
    user_id: int = 1,
    mode: str = "practice",
    status: str = "completed",
    part: str | None = "B",
    started_at: datetime | None | object = UNSET,
    completed_at: datetime | None = None,
) -> PracticeSession:
    return PracticeSession(
        id=session_id,
        user_id=user_id,
        mode=mode,
        status=status,
        exam_date=date(2025, 4, 1),
        part=part,
        total_questions=10,
        answered_count=0,
        started_at=BASE_TIME if started_at is UNSET else started_at,
        completed_at=completed_at,
    )


def _answer(answer_id: int, *, session_id: int, question_id: int, is_correct: bool) -> UserAnswer:
    return UserAnswer(
        id=answer_id,
        session_id=session_id,
        question_id=question_id,
        selected_answer="A" if is_correct else "B",
        is_correct=is_correct,
        answered_at=BASE_TIME + timedelta(minutes=answer_id),
        updated_at=BASE_TIME + timedelta(minutes=answer_id),
    )


def _stats(client: TestClient, user_id: int = 1) -> dict:
    response = client.get(f"/api/v1/users/{user_id}/stats/overview")
    assert response.status_code == 200
    return response.json()


def test_user_with_no_completed_sessions_returns_empty_stats(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        session.add(make_question(date(2025, 4, 1), "B", 1))

    with client_builder(seed) as client:
        body = _stats(client)

    assert body == {
        "total_answered": 0,
        "overall_success_rate": None,
        "part_b": {"total_answered": 0, "success_rate": None},
        "part_c": {"total_answered": 0, "success_rate": None},
        "simulations_completed": 0,
        "active_mistakes_count": 0,
        "repeated_mistakes_count": 0,
        "avg_session_duration_seconds": None,
    }


def test_unknown_user_returns_404(client_builder: ClientBuilder) -> None:
    with client_builder(lambda session: None) as client:
        response = client.get("/api/v1/users/999/stats/overview")

    assert response.status_code == 404
    assert response.json()["detail"] == "user not found"


def test_total_answered_counts_answer_events_and_rounds_success_rate(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        q1 = make_question(date(2025, 4, 1), "B", 1)
        q2 = make_question(date(2025, 4, 1), "B", 2)
        session.add_all([q1, q2])
        session.flush()
        session.add_all(
            [
                _session(1, completed_at=BASE_TIME + timedelta(minutes=10)),
                _session(2, completed_at=BASE_TIME + timedelta(minutes=20)),
            ]
        )
        session.add_all(
            [
                _answer(1, session_id=1, question_id=q1.id, is_correct=True),
                _answer(2, session_id=1, question_id=q2.id, is_correct=False),
                _answer(3, session_id=2, question_id=q1.id, is_correct=False),
            ]
        )

    with client_builder(seed) as client:
        body = _stats(client)

    assert body["total_answered"] == 3
    assert body["overall_success_rate"] == 33.33
    assert body["part_b"] == {"total_answered": 3, "success_rate": 33.33}
    assert body["part_c"] == {"total_answered": 0, "success_rate": None}


def test_part_stats_use_question_part_when_session_part_is_null(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        qb = make_question(date(2025, 4, 1), "B", 1)
        qc = make_question(date(2025, 4, 1), "C", 1)
        session.add_all([qb, qc])
        session.flush()
        session.add(_session(1, part=None, completed_at=BASE_TIME + timedelta(minutes=10)))
        session.add_all(
            [
                _answer(1, session_id=1, question_id=qb.id, is_correct=True),
                _answer(2, session_id=1, question_id=qc.id, is_correct=False),
            ]
        )

    with client_builder(seed) as client:
        body = _stats(client)

    assert body["part_b"] == {"total_answered": 1, "success_rate": 100.0}
    assert body["part_c"] == {"total_answered": 1, "success_rate": 0.0}


def test_invalidated_questions_are_excluded_from_totals_rates_and_repeated_mistakes(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        active = make_question(date(2025, 4, 1), "B", 1)
        invalidated = make_question(
            date(2025, 4, 1),
            "B",
            2,
            status="invalidated",
            correct_answer=None,
            invalidation_note="נפסלה",
        )
        session.add_all([active, invalidated])
        session.flush()
        session.add_all(
            [
                _session(1, completed_at=BASE_TIME + timedelta(minutes=10)),
                _session(2, completed_at=BASE_TIME + timedelta(minutes=20)),
            ]
        )
        session.add_all(
            [
                _answer(1, session_id=1, question_id=active.id, is_correct=True),
                _answer(2, session_id=1, question_id=invalidated.id, is_correct=False),
                _answer(3, session_id=2, question_id=invalidated.id, is_correct=False),
            ]
        )

    with client_builder(seed) as client:
        body = _stats(client)

    assert body["total_answered"] == 1
    assert body["overall_success_rate"] == 100.0
    assert body["repeated_mistakes_count"] == 0


def test_simulations_completed_counts_only_completed_exam_sessions(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        session.add(make_question(date(2025, 4, 1), "B", 1))
        session.add_all(
            [
                _session(1, mode="exam", status="completed", completed_at=BASE_TIME + timedelta(minutes=10)),
                _session(2, mode="exam", status="active", completed_at=None),
                _session(3, mode="simulation", status="completed", completed_at=BASE_TIME + timedelta(minutes=10)),
                _session(4, mode="practice", status="completed", completed_at=BASE_TIME + timedelta(minutes=10)),
            ]
        )

    with client_builder(seed) as client:
        body = _stats(client)

    assert body["simulations_completed"] == 1


def test_active_sessions_do_not_contribute_to_answer_or_mistake_stats(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        q1 = make_question(date(2025, 4, 1), "B", 1)
        q2 = make_question(date(2025, 4, 1), "B", 2)
        session.add_all([q1, q2])
        session.flush()
        session.add_all(
            [
                _session(1, status="completed", completed_at=BASE_TIME + timedelta(minutes=10)),
                _session(2, status="active", completed_at=None),
                _session(3, status="active", completed_at=None),
            ]
        )
        session.add_all(
            [
                _answer(1, session_id=1, question_id=q1.id, is_correct=True),
                _answer(2, session_id=2, question_id=q1.id, is_correct=False),
                _answer(3, session_id=2, question_id=q2.id, is_correct=False),
                _answer(4, session_id=3, question_id=q2.id, is_correct=False),
            ]
        )

    with client_builder(seed) as client:
        body = _stats(client)

    assert body["total_answered"] == 1
    assert body["active_mistakes_count"] == 0
    assert body["repeated_mistakes_count"] == 0


def test_active_mistakes_count_matches_mistakes_endpoint(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        q1 = make_question(date(2025, 4, 1), "B", 1)
        q2 = make_question(date(2025, 4, 1), "B", 2)
        q3 = make_question(date(2025, 4, 1), "B", 3)
        session.add_all([q1, q2, q3])
        session.flush()
        session.add_all(
            [
                _session(1, completed_at=BASE_TIME + timedelta(minutes=10)),
                _session(2, completed_at=BASE_TIME + timedelta(minutes=20)),
            ]
        )
        session.add_all(
            [
                _answer(1, session_id=1, question_id=q1.id, is_correct=False),
                _answer(2, session_id=1, question_id=q2.id, is_correct=False),
                _answer(3, session_id=2, question_id=q2.id, is_correct=True),
                _answer(4, session_id=2, question_id=q3.id, is_correct=False),
            ]
        )

    with client_builder(seed) as client:
        stats = _stats(client)
        mistakes_response = client.get("/api/v1/users/1/mistakes")
        assert mistakes_response.status_code == 200
        mistakes = mistakes_response.json()

    assert stats["active_mistakes_count"] == len(mistakes)


def test_active_mistakes_use_answered_at_not_updated_at(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        q1 = make_question(date(2025, 4, 1), "B", 1)
        session.add(q1)
        session.flush()
        session.add_all(
            [
                _session(1, completed_at=BASE_TIME + timedelta(minutes=10)),
                _session(2, completed_at=BASE_TIME + timedelta(minutes=20)),
            ]
        )
        older_wrong = _answer(1, session_id=1, question_id=q1.id, is_correct=False)
        newer_correct = _answer(2, session_id=2, question_id=q1.id, is_correct=True)
        older_wrong.answered_at = BASE_TIME + timedelta(minutes=1)
        older_wrong.updated_at = BASE_TIME + timedelta(minutes=30)
        newer_correct.answered_at = BASE_TIME + timedelta(minutes=20)
        newer_correct.updated_at = BASE_TIME + timedelta(minutes=20)
        session.add_all([older_wrong, newer_correct])

    with client_builder(seed) as client:
        body = _stats(client)
        mistakes_response = client.get("/api/v1/users/1/mistakes")
        assert mistakes_response.status_code == 200

    assert body["active_mistakes_count"] == 0
    assert mistakes_response.json() == []


def test_repeated_mistakes_count_only_questions_with_at_least_two_completed_wrong_answers(
    client_builder: ClientBuilder, make_question: QuestionFactory
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        q1 = make_question(date(2025, 4, 1), "B", 1)
        q2 = make_question(date(2025, 4, 1), "B", 2)
        session.add_all([q1, q2])
        session.flush()
        session.add_all(
            [
                _session(1, completed_at=BASE_TIME + timedelta(minutes=10)),
                _session(2, completed_at=BASE_TIME + timedelta(minutes=20)),
            ]
        )
        session.add_all(
            [
                _answer(1, session_id=1, question_id=q1.id, is_correct=False),
                _answer(2, session_id=2, question_id=q1.id, is_correct=False),
                _answer(3, session_id=1, question_id=q2.id, is_correct=False),
                _answer(4, session_id=2, question_id=q2.id, is_correct=True),
            ]
        )

    with client_builder(seed) as client:
        body = _stats(client)

    assert body["repeated_mistakes_count"] == 1


def test_avg_duration_null_with_no_valid_completed_sessions(client_builder: ClientBuilder) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        session.add_all(
            [
                _session(1, status="active", completed_at=None),
                _session(2, status="completed", completed_at=None),
                _session(
                    3,
                    status="completed",
                    started_at=BASE_TIME + timedelta(minutes=10),
                    completed_at=BASE_TIME,
                ),
            ]
        )

    with client_builder(seed) as client:
        body = _stats(client)

    assert body["avg_session_duration_seconds"] is None


def test_duration_filter_handles_null_started_at_rows_without_counting_them() -> None:
    from app.services.stats_service import _valid_completed_session_durations

    class Row:
        def __init__(self, started_at: datetime | None, completed_at: datetime | None) -> None:
            self.started_at = started_at
            self.completed_at = completed_at

    rows = [
        Row(None, BASE_TIME + timedelta(seconds=10)),
        Row(BASE_TIME, None),
        Row(BASE_TIME + timedelta(seconds=20), BASE_TIME),
        Row(BASE_TIME, BASE_TIME + timedelta(seconds=30)),
    ]

    assert _valid_completed_session_durations(rows) == [(BASE_TIME, BASE_TIME + timedelta(seconds=30))]


def test_avg_duration_averages_multiple_completed_sessions_and_ignores_invalid_timestamps(
    client_builder: ClientBuilder,
) -> None:
    def seed(session: Session) -> None:
        session.add(_user())
        session.add_all(
            [
                _session(1, completed_at=BASE_TIME + timedelta(seconds=10)),
                _session(2, completed_at=BASE_TIME + timedelta(seconds=20)),
                _session(3, completed_at=None),
                _session(4, started_at=BASE_TIME + timedelta(seconds=5), completed_at=BASE_TIME),
            ]
        )

    with client_builder(seed) as client:
        body = _stats(client)

    assert body["avg_session_duration_seconds"] == 15


def test_no_db_query_in_stats_code() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    for relative_path in (
        "repositories/stats_repository.py",
        "services/stats_service.py",
        "routers/stats.py",
        "schemas/stats.py",
    ):
        text = (root / relative_path).read_text(encoding="utf-8")
        assert ".query(" not in text
