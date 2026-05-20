from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.auth.schemas.auth import AuthUserOut, LoginRequest, TokenResponse
from app.auth.security import create_access_token, verify_password
from app.models.user import User
from app.repositories import user_repository


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


INVALID_CREDENTIALS = AuthError(401, "Invalid email or password")


def login(session: Session, payload: LoginRequest) -> TokenResponse:
    user = user_repository.get_by_email(session, payload.email.lower())
    if user is None or not user.is_active:
        raise INVALID_CREDENTIALS
    if not verify_password(payload.password, user.password_hash):
        raise INVALID_CREDENTIALS

    user.last_login_at = datetime.now(UTC)
    session.flush()
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    session.commit()
    return TokenResponse(access_token=token, user=AuthUserOut.model_validate(user))


def logout(session: Session, user: User) -> None:
    user_repository.increment_token_version(user)
    session.commit()
