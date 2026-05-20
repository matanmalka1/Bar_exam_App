from sqlalchemy import Row, case, func, select
from sqlalchemy.orm import Session

from app.models.practice_session import PracticeSession
from app.models.question import Question
from app.models.user_answer import UserAnswer


def get_answer_totals(session: Session, user_id: int) -> Row:
    statement = (
        select(
            func.count(UserAnswer.id).label("total_answered"),
            func.coalesce(func.sum(case((UserAnswer.is_correct.is_(True), 1), else_=0)), 0).label(
                "correct_answered"
            ),
        )
        .join(PracticeSession, PracticeSession.id == UserAnswer.session_id)
        .join(Question, Question.id == UserAnswer.question_id)
        .where(
            PracticeSession.user_id == user_id,
            PracticeSession.status == "completed",
            Question.status == "active",
        )
    )
    return session.execute(statement).one()


def get_answer_totals_by_part(session: Session, user_id: int) -> list[Row]:
    statement = (
        select(
            Question.part.label("part"),
            func.count(UserAnswer.id).label("total_answered"),
            func.coalesce(func.sum(case((UserAnswer.is_correct.is_(True), 1), else_=0)), 0).label(
                "correct_answered"
            ),
        )
        .join(PracticeSession, PracticeSession.id == UserAnswer.session_id)
        .join(Question, Question.id == UserAnswer.question_id)
        .where(
            PracticeSession.user_id == user_id,
            PracticeSession.status == "completed",
            Question.status == "active",
        )
        .group_by(Question.part)
    )
    return list(session.execute(statement).all())


def list_completed_session_stats_inputs(session: Session, user_id: int) -> list[Row]:
    statement = (
        select(
            PracticeSession.mode.label("mode"),
            PracticeSession.started_at.label("started_at"),
            PracticeSession.completed_at.label("completed_at"),
        )
        .where(PracticeSession.user_id == user_id, PracticeSession.status == "completed")
    )
    return list(session.execute(statement).all())


def count_active_mistakes(session: Session, user_id: int) -> int:
    # Intentionally duplicates Phase 2 mistakes endpoint semantics without importing answer_repository.
    user_answers = (
        select(
            UserAnswer.id.label("ua_id"),
            UserAnswer.question_id.label("qid"),
            UserAnswer.is_correct.label("is_correct"),
            UserAnswer.answered_at.label("answered_at"),
        )
        .join(PracticeSession, PracticeSession.id == UserAnswer.session_id)
        .join(Question, Question.id == UserAnswer.question_id)
        .where(
            PracticeSession.user_id == user_id,
            PracticeSession.status == "completed",
            Question.status == "active",
        )
        .subquery()
    )
    ranked = (
        select(
            user_answers.c.ua_id,
            user_answers.c.qid,
            user_answers.c.is_correct,
            # answered_at is stable once the session is completed; id breaks rare timestamp ties.
            func.row_number()
            .over(
                partition_by=user_answers.c.qid,
                order_by=(user_answers.c.answered_at.desc(), user_answers.c.ua_id.desc()),
            )
            .label("rn"),
        )
    ).subquery()
    latest = select(ranked.c.qid, ranked.c.is_correct).where(ranked.c.rn == 1).subquery()
    statement = select(func.count()).select_from(latest).where(latest.c.is_correct.is_(False))
    return int(session.scalar(statement) or 0)


def count_repeated_mistakes(session: Session, user_id: int) -> int:
    wrong_count = func.sum(case((UserAnswer.is_correct.is_(False), 1), else_=0))
    repeated = (
        select(UserAnswer.question_id.label("qid"))
        .join(PracticeSession, PracticeSession.id == UserAnswer.session_id)
        .join(Question, Question.id == UserAnswer.question_id)
        .where(
            PracticeSession.user_id == user_id,
            PracticeSession.status == "completed",
            Question.status == "active",
        )
        .group_by(UserAnswer.question_id)
        .having(wrong_count >= 2)
        .subquery()
    )
    statement = select(func.count()).select_from(repeated)
    return int(session.scalar(statement) or 0)
