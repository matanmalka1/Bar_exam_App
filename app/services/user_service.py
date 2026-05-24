from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import user_repository


def get_user(session: Session, user_id: int) -> User | None:
    return user_repository.get_by_id(session, user_id)


def reset_user_data(session: Session, user_id: int) -> None:
    user_repository.delete_user_data(session, user_id)
    session.commit()
