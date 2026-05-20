from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.db.deps import get_session
from app.schemas.answer import BookmarkedQuestionOut, BookmarkOut, BookmarkRemovedOut, MistakeOut
from app.schemas.session import SessionSummaryOut
from app.services import answer_service, practice_session_service
from app.services.answer_service import AnswerError
from app.services.practice_session_service import SessionError

router = APIRouter()

STABLE_ID_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])_[BC]_(00[1-9]|0[1-3][0-9]|040)$"


@router.get("/users/me/sessions", response_model=list[SessionSummaryOut])
def list_my_sessions(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    status: Annotated[Literal["active", "completed", "abandoned"] | None, Query()] = None,
) -> list[SessionSummaryOut]:
    try:
        return practice_session_service.list_user_sessions(session, current_user.id, status)
    except SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/users/me/mistakes", response_model=list[MistakeOut])
def get_my_mistakes(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> list[MistakeOut]:
    try:
        return answer_service.list_mistakes(session, current_user.id)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/users/me/bookmarks/{stable_id}", response_model=BookmarkOut)
def add_my_bookmark(
    stable_id: Annotated[str, Path(pattern=STABLE_ID_PATTERN)],
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> BookmarkOut:
    try:
        return answer_service.add_bookmark(session, current_user.id, stable_id)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/users/me/bookmarks/{stable_id}", response_model=BookmarkRemovedOut)
def delete_my_bookmark(
    stable_id: Annotated[str, Path(pattern=STABLE_ID_PATTERN)],
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> BookmarkRemovedOut:
    try:
        answer_service.remove_bookmark(session, current_user.id, stable_id)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return BookmarkRemovedOut(removed=True)


@router.get("/users/me/bookmarks", response_model=list[BookmarkedQuestionOut])
def list_my_bookmarks(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> list[BookmarkedQuestionOut]:
    try:
        return answer_service.list_bookmarks(session, current_user.id)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
