from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db.deps import get_session
from app.models.user import User
from app.repositories import user_repository

_bearer = HTTPBearer(auto_error=False)
_INVALID_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _INVALID_TOKEN
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise _INVALID_TOKEN from exc

    sub = payload.get("sub")
    token_version = payload.get("token_version")
    if not isinstance(sub, str) or not isinstance(token_version, int):
        raise _INVALID_TOKEN
    try:
        user_id = int(sub)
    except ValueError as exc:
        raise _INVALID_TOKEN from exc

    user = user_repository.get_by_id(session, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise _INVALID_TOKEN
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
