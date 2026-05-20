from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.schemas.auth import AuthUserOut, LoginRequest, TokenResponse
from app.auth.services import auth_service
from app.auth.services.auth_service import AuthError
from app.db.deps import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Annotated[Session, Depends(get_session)]) -> TokenResponse:
    try:
        return auth_service.login(session, payload)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    auth_service.logout(session, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AuthUserOut)
def me(current_user: CurrentUser) -> AuthUserOut:
    return AuthUserOut.model_validate(current_user)
