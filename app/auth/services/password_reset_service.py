import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.auth.services.auth_service import AuthError
from app.core.config import settings
from app.core.email_service import send_password_reset_email
from app.models.user import User
from app.repositories import password_reset_token_repository, user_repository

logger = logging.getLogger(__name__)

_INVALID_TOKEN_MSG = "קישור איפוס הסיסמה אינו תקין או שפג תוקפו"


def _invalid_token() -> AuthError:
    return AuthError(400, _INVALID_TOKEN_MSG)


_FORGOT_MESSAGE = "אם קיים משתמש עם האימייל הזה, נשלחו הוראות לאיפוס סיסמה"
_RESET_MESSAGE = "הסיסמה אופסה בהצלחה"


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def request_password_reset(
    session: Session,
    email: str,
    requested_ip: str | None,
    user_agent: str | None,
) -> str:
    user = user_repository.get_by_email(session, email.strip().lower())
    if user is None or not user.is_active:
        return _FORGOT_MESSAGE

    _create_password_reset_token(session, user, requested_ip, user_agent)
    return _FORGOT_MESSAGE


def request_password_reset_for_user(
    session: Session,
    user: User,
    requested_ip: str | None,
    user_agent: str | None,
) -> str:
    _create_password_reset_token(session, user, requested_ip, user_agent)
    return _FORGOT_MESSAGE


def _create_password_reset_token(
    session: Session,
    user: User,
    requested_ip: str | None,
    user_agent: str | None,
) -> None:
    password_reset_token_repository.invalidate_unused_tokens_for_user(session, user.id)

    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    password_reset_token_repository.create(
        session,
        user_id=user.id,
        token_hash=_hash_token(raw),
        expires_at=expires_at,
        requested_ip=requested_ip,
        user_agent=user_agent,
    )
    session.commit()

    if settings.PASSWORD_RESET_DEV_LOG:
        url = f"{settings.FRONTEND_PASSWORD_RESET_URL}?token={raw}"
        logger.info("[DEV ONLY] Password reset URL: %s", url)

    reset_url = f"{settings.FRONTEND_PASSWORD_RESET_URL}?token={raw}"
    first_name = user.full_name.split()[0] if user.full_name else user.email
    try:
        send_password_reset_email(user.email, first_name, reset_url)
    except Exception:
        logger.exception("Failed to send password reset email to %s", user.email)


def reset_password(session: Session, token: str, new_password: str) -> str:
    token_hash = _hash_token(token)

    record = password_reset_token_repository.get_valid_by_token_hash(session, token_hash)
    if record is None:
        raise _invalid_token()

    user = user_repository.get_by_id(session, record.user_id)
    if user is None or not user.is_active:
        raise _invalid_token()

    updated = password_reset_token_repository.mark_used_atomic(session, record.id)
    if not updated:
        raise _invalid_token()

    user.password_hash = hash_password(new_password)
    user_repository.increment_token_version(user)
    session.commit()
    return _RESET_MESSAGE
