from sqlalchemy import Row, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.bookmarked_question import BookmarkedQuestion
from app.models.question import Question


def add_bookmark(session: Session, user_id: int, question_id: int) -> BookmarkedQuestion:
    try:
        with session.begin_nested():
            bm = BookmarkedQuestion(user_id=user_id, question_id=question_id)
            session.add(bm)
            session.flush()
            return bm
    except IntegrityError:
        existing = session.scalars(
            select(BookmarkedQuestion).where(
                BookmarkedQuestion.user_id == user_id,
                BookmarkedQuestion.question_id == question_id,
            )
        ).one_or_none()
        assert existing is not None
        return existing


def remove_bookmark(session: Session, user_id: int, question_id: int) -> None:
    session.execute(
        delete(BookmarkedQuestion).where(
            BookmarkedQuestion.user_id == user_id,
            BookmarkedQuestion.question_id == question_id,
        )
    )


def list_bookmarks(session: Session, user_id: int) -> list[Row]:
    statement = (
        select(Question, BookmarkedQuestion.created_at)
        .join(BookmarkedQuestion, BookmarkedQuestion.question_id == Question.id)
        .where(BookmarkedQuestion.user_id == user_id)
        .order_by(BookmarkedQuestion.created_at.desc(), Question.stable_id.asc())
    )
    return list(session.execute(statement).all())


def list_bookmarked_questions(session: Session, user_id: int) -> list[Question]:
    statement = (
        select(Question)
        .join(BookmarkedQuestion, BookmarkedQuestion.question_id == Question.id)
        .where(BookmarkedQuestion.user_id == user_id)
        .order_by(Question.stable_id.asc())
    )
    return list(session.scalars(statement).all())
