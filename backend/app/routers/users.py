from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db.deps import get_session
from app.schemas.answer import BookmarkedQuestionOut, BookmarkOut, BookmarkRemovedOut, MistakeOut
from app.schemas.session import SessionSummaryOut
from app.schemas.user import UserOut
from app.services import answer_service, practice_session_service, user_service
from app.services.answer_service import AnswerError
from app.services.practice_session_service import SessionError

router = APIRouter()

STABLE_ID_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])_[BC]_(00[1-9]|0[1-3][0-9]|040)$"


@router.post("/users/dev", response_model=UserOut)
def create_dev_user(session: Annotated[Session, Depends(get_session)]) -> UserOut:
    return user_service.ensure_dev_user(session)


@router.get("/users/{user_id}/sessions", response_model=list[SessionSummaryOut])
def list_user_sessions(
    user_id: int,
    session: Annotated[Session, Depends(get_session)],
    status: Annotated[Literal["active", "completed", "abandoned"] | None, Query()] = None,
) -> list[SessionSummaryOut]:
    try:
        return practice_session_service.list_user_sessions(session, user_id, status)
    except SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/users/{user_id}/mistakes", response_model=list[MistakeOut])
def get_mistakes(user_id: int, session: Annotated[Session, Depends(get_session)]) -> list[MistakeOut]:
    try:
        return answer_service.list_mistakes(session, user_id)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/users/{user_id}/bookmarks/{stable_id}", response_model=BookmarkOut)
def add_bookmark(
    user_id: int,
    stable_id: Annotated[str, Path(pattern=STABLE_ID_PATTERN)],
    session: Annotated[Session, Depends(get_session)],
) -> BookmarkOut:
    try:
        return answer_service.add_bookmark(session, user_id, stable_id)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/users/{user_id}/bookmarks/{stable_id}", response_model=BookmarkRemovedOut)
def delete_bookmark(
    user_id: int,
    stable_id: Annotated[str, Path(pattern=STABLE_ID_PATTERN)],
    session: Annotated[Session, Depends(get_session)],
) -> BookmarkRemovedOut:
    try:
        answer_service.remove_bookmark(session, user_id, stable_id)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return BookmarkRemovedOut(removed=True)


@router.get("/users/{user_id}/bookmarks", response_model=list[BookmarkedQuestionOut])
def list_user_bookmarks(user_id: int, session: Annotated[Session, Depends(get_session)]) -> list[BookmarkedQuestionOut]:
    try:
        return answer_service.list_bookmarks(session, user_id)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
