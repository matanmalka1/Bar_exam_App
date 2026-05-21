from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.schemas.auth import (
    AuthUserOut,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
)
from app.auth.schemas.password_reset import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from app.auth.services import auth_service, password_reset_service
from app.auth.services.auth_service import AuthBundle
from app.core.config import (
    AUTH_REFRESH_TOKEN_EXPIRE_DAYS,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_SAMESITE,
    REFRESH_COOKIE_SECURE,
)
from app.core.rate_limit import get_email_key, limiter
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
@limiter.limit("5/minute")
@limiter.limit("3/hour", key_func=get_email_key("auth:register"))
async def register(
    request: Request,
    payload: RegisterRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    bundle = auth_service.register(session, payload)
    return _respond(response, bundle)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
@limiter.limit("5/minute", key_func=get_email_key("auth:login"))
async def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    bundle = auth_service.login(session, payload)
    return _respond(response, bundle)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    session: Annotated[Session, Depends(get_session)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> RefreshResponse:
    return auth_service.refresh(session, refresh_token)


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


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("5/minute")
@limiter.limit("3/hour", key_func=get_email_key("auth:forgot-password"))
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> ForgotPasswordResponse:
    requested_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    message = password_reset_service.request_password_reset(session, payload.email, requested_ip, user_agent)
    return ForgotPasswordResponse(message=message)


@router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit("10/minute")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ResetPasswordResponse:
    message = password_reset_service.reset_password(session, payload.token, payload.new_password)
    return ResetPasswordResponse(message=message)
