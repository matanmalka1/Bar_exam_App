from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.question import ExamSummary, QuestionOut
from app.services import question_service

router = APIRouter()


@router.get("/exams", response_model=list[ExamSummary])
def get_exams(session: Annotated[Session, Depends(get_session)]) -> list[ExamSummary]:
    return question_service.list_exams(session)


@router.get("/questions", response_model=list[QuestionOut])
def get_questions(
    session: Annotated[Session, Depends(get_session)],
    exam_date: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    part: Literal["B", "C"],
) -> list[QuestionOut]:
    return question_service.list_questions(session, exam_date, part)


@router.get("/questions/{stable_id}", response_model=QuestionOut)
def get_question(
    stable_id: Annotated[str, Path(pattern=r"^\d{4}-(0[1-9]|1[0-2])_[BC]_(00[1-9]|0[1-3][0-9]|040)$")],
    session: Annotated[Session, Depends(get_session)],
) -> QuestionOut:
    question = question_service.get_question(session, stable_id)
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    return question
