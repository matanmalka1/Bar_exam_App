from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_id(session: Session, user_id: int) -> User | None:
    return session.scalars(select(User).where(User.id == user_id)).one_or_none()


def get_by_user_key(session: Session, user_key: str) -> User | None:
    return session.scalars(select(User).where(User.user_key == user_key)).one_or_none()


def upsert_by_user_key(session: Session, user_key: str, display_name: str) -> User:
    existing = get_by_user_key(session, user_key)
    if existing is not None:
        return existing
    try:
        with session.begin_nested():
            user = User(display_name=display_name, user_key=user_key)
            session.add(user)
            session.flush()
            return user
    except IntegrityError:
        user = get_by_user_key(session, user_key)
        assert user is not None
        return user
