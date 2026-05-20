from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.answer import AnswerExamOut, AnswerPracticeOut, AnswerSubmitIn
from app.schemas.session import (
    SessionCompleteOut,
    SessionCreateIn,
    SessionDetailOut,
    SessionSummaryOut,
)
from app.services import answer_service, session_service
from app.services.answer_service import AnswerError
from app.services.session_service import SessionError

router = APIRouter()


@router.post("/practice-sessions", response_model=SessionSummaryOut, status_code=201)
def create_session(
    payload: SessionCreateIn, session: Annotated[Session, Depends(get_session)]
) -> SessionSummaryOut:
    try:
        return session_service.create_session(session, payload)
    except SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/practice-sessions/{session_id}", response_model=SessionDetailOut)
def get_session_detail(
    session_id: int, session: Annotated[Session, Depends(get_session)]
) -> SessionDetailOut:
    try:
        return session_service.get_session_detail(session, session_id)
    except SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/practice-sessions/{session_id}/answers",
    response_model=AnswerPracticeOut | AnswerExamOut,
)
def submit_answer(
    session_id: int,
    payload: AnswerSubmitIn,
    session: Annotated[Session, Depends(get_session)],
) -> AnswerPracticeOut | AnswerExamOut:
    try:
        return answer_service.submit_answer(session, session_id, payload)
    except AnswerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/practice-sessions/{session_id}/complete", response_model=SessionCompleteOut)
def complete_session(
    session_id: int, session: Annotated[Session, Depends(get_session)]
) -> SessionCompleteOut:
    try:
        return session_service.complete_session(session, session_id)
    except SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
