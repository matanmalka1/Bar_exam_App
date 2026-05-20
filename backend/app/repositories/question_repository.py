from datetime import date

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from app.models.question import Question


def get_exams(session: Session) -> list[Row]:
    statement = (
        select(
            Question.exam_date,
            Question.part,
            func.count(Question.id).label("active_count"),
        )
        .where(Question.status == "active")
        .group_by(Question.exam_date, Question.part)
        .order_by(Question.exam_date.asc(), Question.part.asc())
    )
    return list(session.execute(statement).all())


def get_questions_by_exam(session: Session, exam_date: date, part: str) -> list[Question]:
    statement = (
        select(Question)
        .where(Question.exam_date == exam_date, Question.part == part)
        .order_by(Question.number.asc())
    )
    return list(session.scalars(statement).all())


def get_question_by_stable_id(session: Session, stable_id: str) -> Question | None:
    statement = select(Question).where(Question.stable_id == stable_id)
    return session.scalars(statement).one_or_none()
