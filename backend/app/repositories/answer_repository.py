from sqlalchemy import Row, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.practice_session import PracticeSession
from app.models.question import Question
from app.models.user_answer import UserAnswer


def get_user_answer(session: Session, session_id: int, question_id: int) -> UserAnswer | None:
    return session.scalars(
        select(UserAnswer).where(UserAnswer.session_id == session_id, UserAnswer.question_id == question_id)
    ).one_or_none()


def insert_user_answer(
    session: Session,
    *,
    session_id: int,
    question_id: int,
    selected_answer: str,
    is_correct: bool,
) -> tuple[UserAnswer, bool]:
    """Insert a new user_answer or fall through to update on unique conflict.

    Returns (row, inserted). `inserted=True` means a new row was created — the caller should
    bump the session's answered_count exactly once in that case.
    """
    try:
        with session.begin_nested():
            ua = UserAnswer(
                session_id=session_id,
                question_id=question_id,
                selected_answer=selected_answer,
                is_correct=is_correct,
            )
            session.add(ua)
            session.flush()
            return ua, True
    except IntegrityError:
        existing = get_user_answer(session, session_id, question_id)
        assert existing is not None
        existing.selected_answer = selected_answer
        existing.is_correct = is_correct
        session.flush()
        return existing, False


def list_session_answers(session: Session, session_id: int) -> list[UserAnswer]:
    return list(session.scalars(select(UserAnswer).where(UserAnswer.session_id == session_id)).all())


def get_latest_mistakes(session: Session, user_id: int) -> list[Row]:
    user_answers = (
        select(
            UserAnswer.id.label("ua_id"),
            UserAnswer.question_id.label("qid"),
            UserAnswer.is_correct.label("is_correct"),
            UserAnswer.updated_at.label("updated_at"),
        )
        .join(PracticeSession, PracticeSession.id == UserAnswer.session_id)
        .where(PracticeSession.user_id == user_id, PracticeSession.status == "completed")
        .subquery()
    )
    ranked = (
        select(
            user_answers.c.ua_id,
            user_answers.c.qid,
            user_answers.c.is_correct,
            func.row_number()
            .over(
                partition_by=user_answers.c.qid,
                order_by=(user_answers.c.updated_at.desc(), user_answers.c.ua_id.desc()),
            )
            .label("rn"),
        )
    ).subquery()
    latest = select(ranked.c.qid, ranked.c.is_correct).where(ranked.c.rn == 1).subquery()
    counts = (
        select(
            UserAnswer.question_id.label("qid"),
            func.count(UserAnswer.id).label("times_answered"),
            func.sum(case((UserAnswer.is_correct.is_(False), 1), else_=0)).label("times_wrong"),
        )
        .join(PracticeSession, PracticeSession.id == UserAnswer.session_id)
        .where(PracticeSession.user_id == user_id, PracticeSession.status == "completed")
        .group_by(UserAnswer.question_id)
        .subquery()
    )
    statement = (
        select(Question, counts.c.times_answered, counts.c.times_wrong)
        .join(latest, latest.c.qid == Question.id)
        .join(counts, counts.c.qid == Question.id)
        .where(latest.c.is_correct.is_(False), Question.status == "active")
        .order_by(Question.exam_date.asc(), Question.part.asc(), Question.number.asc())
    )
    return list(session.execute(statement).all())


def list_active_mistake_questions(session: Session, user_id: int) -> list[Question]:
    """Questions where the user's latest answer across completed sessions is incorrect.

    Active sessions are ignored. Order: Question.stable_id asc (deterministic).
    """
    user_answers = (
        select(
            UserAnswer.id.label("ua_id"),
            UserAnswer.question_id.label("qid"),
            UserAnswer.is_correct.label("is_correct"),
            UserAnswer.updated_at.label("updated_at"),
        )
        .join(PracticeSession, PracticeSession.id == UserAnswer.session_id)
        .where(PracticeSession.user_id == user_id, PracticeSession.status == "completed")
        .subquery()
    )
    ranked = select(
        user_answers.c.ua_id,
        user_answers.c.qid,
        user_answers.c.is_correct,
        func.row_number()
        .over(
            partition_by=user_answers.c.qid,
            order_by=(user_answers.c.updated_at.desc(), user_answers.c.ua_id.desc()),
        )
        .label("rn"),
    ).subquery()
    latest = select(ranked.c.qid, ranked.c.is_correct).where(ranked.c.rn == 1).subquery()
    statement = (
        select(Question)
        .join(latest, latest.c.qid == Question.id)
        .where(latest.c.is_correct.is_(False), Question.status == "active")
        .order_by(Question.stable_id.asc())
    )
    return list(session.scalars(statement).all())
