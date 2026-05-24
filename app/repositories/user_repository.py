from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.bookmarked_question import BookmarkedQuestion
from app.models.practice_session import PracticeSession
from app.models.user import User


def get_by_id(session: Session, user_id: int) -> User | None:
    return session.scalars(select(User).where(User.id == user_id)).one_or_none()


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalars(select(User).where(User.email == email)).one_or_none()


def increment_token_version(user: User) -> None:
    user.token_version = user.token_version + 1


def delete_user_data(session: Session, user_id: int) -> None:
    """Delete all user-generated data. CASCADE handles user_answers and practice_session_questions."""
    session.execute(delete(PracticeSession).where(PracticeSession.user_id == user_id))
    session.execute(delete(BookmarkedQuestion).where(BookmarkedQuestion.user_id == user_id))


def create(
    session: Session,
    *,
    full_name: str,
    email: str,
    password_hash: str,
    is_active: bool = True,
) -> User:
    user = User(
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user
