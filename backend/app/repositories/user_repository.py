from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_id(session: Session, user_id: int) -> User | None:
    return session.scalars(select(User).where(User.id == user_id)).one_or_none()


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalars(select(User).where(User.email == email)).one_or_none()


def increment_token_version(user: User) -> None:
    user.token_version = user.token_version + 1


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
