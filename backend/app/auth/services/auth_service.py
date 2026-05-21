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
from app.models.user import User
from app.repositories import user_repository


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


INVALID_CREDENTIALS = AuthError(401, "Invalid email or password")
INVALID_REFRESH = AuthError(401, "Invalid or expired refresh token")
EMAIL_TAKEN = AuthError(409, "כבר קיים משתמש עם האימייל הזה")


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
        response=TokenResponse(access_token=access, user=AuthUserOut.model_validate(user)),
        refresh_token=refresh,
    )


def login(session: Session, payload: LoginRequest) -> AuthBundle:
    user = user_repository.get_by_email(session, _normalize_email(payload.email))
    if user is None or not user.is_active:
        raise INVALID_CREDENTIALS
    if not verify_password(payload.password, user.password_hash):
        raise INVALID_CREDENTIALS

    user.last_login_at = datetime.now(UTC)
    session.flush()
    bundle = _issue_bundle(user)
    session.commit()
    return bundle


def register(session: Session, payload: RegisterRequest) -> AuthBundle:
    email = _normalize_email(payload.email)
    if user_repository.get_by_email(session, email) is not None:
        raise EMAIL_TAKEN
    try:
        user = user_repository.create(
            session,
            full_name=payload.full_name,
            email=email,
            password_hash=hash_password(payload.password),
        )
    except IntegrityError as exc:
        session.rollback()
        raise EMAIL_TAKEN from exc

    user.last_login_at = datetime.now(UTC)
    session.flush()
    bundle = _issue_bundle(user)
    session.commit()
    return bundle


def refresh(session: Session, refresh_token: str | None) -> RefreshResponse:
    if not refresh_token:
        raise INVALID_REFRESH
    try:
        payload = decode_refresh_token(refresh_token)
    except jwt.PyJWTError as exc:
        raise INVALID_REFRESH from exc

    sub = payload.get("sub")
    token_version = payload.get("token_version")
    if not isinstance(sub, str) or not isinstance(token_version, int):
        raise INVALID_REFRESH
    try:
        user_id = int(sub)
    except ValueError as exc:
        raise INVALID_REFRESH from exc

    user = user_repository.get_by_id(session, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise INVALID_REFRESH

    access = create_access_token(user_id=user.id, token_version=user.token_version)
    return RefreshResponse(access_token=access)


def logout(session: Session, user: User) -> None:
    user_repository.increment_token_version(user)
    session.commit()
