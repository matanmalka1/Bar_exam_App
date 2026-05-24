from __future__ import annotations

import sys
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Generator[None, None, None]:
    from app.core.rate_limit import limiter

    limiter._storage.reset()
    yield
    limiter._storage.reset()


if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.question import Question

QuestionFactory = Callable[..., "Question"]
SeedDatabase = Callable[["Session"], None]


@pytest.fixture
def make_question() -> QuestionFactory:
    def _make_question(
        exam_date: date,
        part: str,
        number: int,
        *,
        status: str = "active",
        correct_answer: str | None = "A",
        invalidation_note: str | None = None,
    ) -> Question:
        from app.models.question import Question

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

    return _make_question


@pytest.fixture
def client_builder() -> Callable[[SeedDatabase], Iterator[TestClient]]:
    @contextmanager
    def _build_client(seed_database: SeedDatabase) -> Iterator[TestClient]:
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from sqlalchemy.pool import StaticPool

        from app.db.base import Base
        from app.db.deps import get_session
        from app.main import app

        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            seed_database(session)
            session.commit()

        def override_get_session() -> Generator[Session, None, None]:
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_session] = override_get_session
        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            app.dependency_overrides.clear()

    return _build_client
