from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import user_repository


def get_user(session: Session, user_id: int) -> User | None:
    return user_repository.get_by_id(session, user_id)
