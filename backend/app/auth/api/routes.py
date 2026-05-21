from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.schemas.auth import (
    AuthUserOut,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
)
from app.auth.services import auth_service
from app.auth.services.auth_service import AuthBundle, AuthError
from app.core.config import (
    AUTH_REFRESH_TOKEN_EXPIRE_DAYS,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_SAMESITE,
    REFRESH_COOKIE_SECURE,
)
from app.db.deps import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_MAX_AGE = AUTH_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=_REFRESH_MAX_AGE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def _respond(response: Response, bundle: AuthBundle) -> TokenResponse:
    _set_refresh_cookie(response, bundle.refresh_token)
    return bundle.response


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    try:
        bundle = auth_service.register(session, payload)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _respond(response, bundle)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    try:
        bundle = auth_service.login(session, payload)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _respond(response, bundle)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    session: Annotated[Session, Depends(get_session)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> RefreshResponse:
    try:
        return auth_service.refresh(session, refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    session: Annotated[Session, Depends(get_session)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> Response:
    auth_service.logout_by_refresh_token(session, refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response)
    return response


@router.get("/me", response_model=AuthUserOut)
def me(current_user: CurrentUser) -> AuthUserOut:
    return AuthUserOut.model_validate(current_user)
