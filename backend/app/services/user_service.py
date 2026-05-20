from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import user_repository
from app.schemas.user import UserOut

DEV_USER_KEY = "dev"
DEV_USER_NAME = "Dev User"


def ensure_dev_user(session: Session) -> UserOut:
    # TODO(auth): replace with real authenticated identity.
    user = user_repository.upsert_by_user_key(session, DEV_USER_KEY, DEV_USER_NAME)
    session.commit()
    return _to_out(user)


def get_user(session: Session, user_id: int) -> User | None:
    # TODO(auth): user identity should come from a verified token, not the request.
    return user_repository.get_by_id(session, user_id)


def _to_out(user: User) -> UserOut:
    return UserOut.model_validate(user)
