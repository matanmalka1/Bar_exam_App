from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.schemas.auth import (
    AuthUserOut,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
)
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.core.exceptions import AppError, app_error_code_for_status, app_error_message_for_status, contains_hebrew
from app.models.user import User
from app.repositories import user_repository


class AuthError(AppError):
    def __init__(self, status_code: int, detail: str) -> None:
        message = detail if contains_hebrew(detail) else app_error_message_for_status(status_code)
        super().__init__(
            code=app_error_code_for_status(status_code),
            message=message,
            status_code=status_code,
        )
        self.status_code = status_code
        self.detail = detail


def invalid_credentials() -> AuthError:
    return AuthError(401, "Invalid email or password")


def invalid_refresh() -> AuthError:
    return AuthError(401, "Invalid or expired refresh token")


def email_taken() -> AuthError:
    return AuthError(409, "כבר קיים משתמש עם האימייל הזה")


@dataclass(frozen=True)
class AuthBundle:
    response: TokenResponse
    refresh_token: str


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _issue_bundle(user: User) -> AuthBundle:
    access = create_access_token(user_id=user.id, token_version=user.token_version)
    refresh = create_refresh_token(user_id=user.id, token_version=user.token_version)
    return AuthBundle(
        response=TokenResponse(access_token=access, refresh_token=refresh, user=AuthUserOut.model_validate(user)),
        refresh_token=refresh,
    )


def login(session: Session, payload: LoginRequest) -> AuthBundle:
    user = user_repository.get_by_email(session, _normalize_email(payload.email))
    if user is None or not user.is_active:
        raise invalid_credentials()
    if not verify_password(payload.password, user.password_hash):
        raise invalid_credentials()

    user.last_login_at = datetime.now(UTC)
    session.flush()
    bundle = _issue_bundle(user)
    session.commit()
    return bundle


def register(session: Session, payload: RegisterRequest) -> AuthBundle:
    email = _normalize_email(payload.email)
    if user_repository.get_by_email(session, email) is not None:
        raise email_taken()
    try:
        user = user_repository.create(
            session,
            full_name=payload.full_name,
            email=email,
            password_hash=hash_password(payload.password),
        )
    except IntegrityError as exc:
        session.rollback()
        raise email_taken() from exc

    user.last_login_at = datetime.now(UTC)
    session.flush()
    bundle = _issue_bundle(user)
    session.commit()
    return bundle


def refresh(session: Session, refresh_token: str | None) -> RefreshResponse:
    if not refresh_token:
        raise invalid_refresh()
    try:
        payload = decode_refresh_token(refresh_token)
    except jwt.PyJWTError as exc:
        raise invalid_refresh() from exc

    sub = payload.get("sub")
    token_version = payload.get("token_version")
    if not isinstance(sub, str) or not isinstance(token_version, int):
        raise invalid_refresh()
    try:
        user_id = int(sub)
    except ValueError as exc:
        raise invalid_refresh() from exc

    user = user_repository.get_by_id(session, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise invalid_refresh()

    access = create_access_token(user_id=user.id, token_version=user.token_version)
    return RefreshResponse(access_token=access)


def logout_by_refresh_token(session: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    try:
        payload = decode_refresh_token(refresh_token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return
    user = user_repository.get_by_id(session, user_id)
    if user is None:
        return
    user_repository.increment_token_version(user)
    session.commit()
