import random
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.question import Question
from app.services import practice_session_service

from .helpers import seed_default_user

QuestionFactory = Callable[..., Question]
ClientBuilder = Callable[[Callable[[Session], None]], AbstractContextManager[TestClient]]


@pytest.fixture(autouse=True)
def deterministic_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(practice_session_service, "_make_rng", lambda: random.Random(1234))


@pytest.fixture
def client_builder(client_builder: ClientBuilder) -> ClientBuilder:
    @contextmanager
    def _wrap(seed_database: Callable[[Session], None]):
        def _seed(session: Session) -> None:
            seed_default_user(session)
            seed_database(session)

        with client_builder(_seed) as test_client:
            yield test_client

    return _wrap


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
