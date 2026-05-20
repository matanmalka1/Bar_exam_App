from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Row, select, update
from sqlalchemy.orm import Session

from app.models.practice_session import PracticeSession, PracticeSessionQuestion
from app.models.question import Question


def create_session(
    session: Session,
    *,
    user_id: int,
    mode: str,
    exam_date: date | None,
    part: str | None,
    total_questions: int,
) -> PracticeSession:
    ps = PracticeSession(
        user_id=user_id,
        mode=mode,
        status="active",
        exam_date=exam_date,
        part=part,
        total_questions=total_questions,
        answered_count=0,
    )
    session.add(ps)
    session.flush()
    return ps


def add_session_questions(session: Session, session_id: int, ordered_question_ids: list[int]) -> None:
    rows = [
        PracticeSessionQuestion(session_id=session_id, question_id=qid, position=i + 1)
        for i, qid in enumerate(ordered_question_ids)
    ]
    session.add_all(rows)
    session.flush()


def select_candidate_questions(
    session: Session,
    *,
    exam_date: date | None,
    part: str | None,
    include_invalidated: bool,
) -> list[Question]:
    statement = select(Question)
    if exam_date is not None:
        statement = statement.where(Question.exam_date == exam_date)
    if part is not None:
        statement = statement.where(Question.part == part)
    if not include_invalidated:
        statement = statement.where(Question.status == "active")
    statement = statement.order_by(Question.exam_date.asc(), Question.part.asc(), Question.number.asc())
    return list(session.scalars(statement).all())


def list_seen_question_ids(session: Session, user_id: int) -> set[int]:
    statement = (
        select(PracticeSessionQuestion.question_id)
        .join(PracticeSession, PracticeSession.id == PracticeSessionQuestion.session_id)
        .where(PracticeSession.user_id == user_id)
        .distinct()
    )
    return set(session.scalars(statement).all())


def get_session_by_id(session: Session, session_id: int) -> PracticeSession | None:
    return session.scalars(select(PracticeSession).where(PracticeSession.id == session_id)).one_or_none()


def get_session_questions(session: Session, session_id: int) -> list[Row]:
    statement = (
        select(PracticeSessionQuestion.position, Question)
        .join(Question, Question.id == PracticeSessionQuestion.question_id)
        .where(PracticeSessionQuestion.session_id == session_id)
        .order_by(PracticeSessionQuestion.position.asc())
    )
    return list(session.execute(statement).all())


def get_session_question_link(session: Session, session_id: int, question_id: int) -> PracticeSessionQuestion | None:
    return session.scalars(
        select(PracticeSessionQuestion).where(
            PracticeSessionQuestion.session_id == session_id,
            PracticeSessionQuestion.question_id == question_id,
        )
    ).one_or_none()


def list_sessions_by_user(session: Session, user_id: int, status: str | None) -> list[PracticeSession]:
    statement = select(PracticeSession).where(PracticeSession.user_id == user_id)
    if status is not None:
        statement = statement.where(PracticeSession.status == status)
    statement = statement.order_by(PracticeSession.created_at.desc(), PracticeSession.id.desc())
    return list(session.scalars(statement).all())


def increment_answered_count(session: Session, session_id: int) -> None:
    session.execute(
        update(PracticeSession)
        .where(PracticeSession.id == session_id)
        .values(answered_count=PracticeSession.answered_count + 1)
    )


def complete_session(
    session: Session,
    session_id: int,
    *,
    correct_count: int,
    score_percent: Decimal,
    completed_at: datetime,
) -> None:
    session.execute(
        update(PracticeSession)
        .where(PracticeSession.id == session_id)
        .values(
            status="completed",
            correct_count=correct_count,
            score_percent=score_percent,
            completed_at=completed_at,
        )
    )
