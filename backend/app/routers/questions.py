from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db.deps import get_session
from app.schemas.question import ExamSummary, QuestionPracticeOut, QuestionReviewOut
from app.services import question_service

router = APIRouter()


@router.get("/exams", response_model=list[ExamSummary])
def get_exams(session: Annotated[Session, Depends(get_session)]) -> list[ExamSummary]:
    return question_service.list_exams(session)


@router.get("/questions", response_model=list[QuestionPracticeOut])
def get_questions(
    session: Annotated[Session, Depends(get_session)],
    exam_date: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    part: Literal["B", "C"],
) -> list[QuestionPracticeOut]:
    return question_service.list_questions(session, exam_date, part)


@router.get("/questions/review", response_model=list[QuestionReviewOut])
def get_questions_for_review(
    session: Annotated[Session, Depends(get_session)],
    exam_date: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    part: Literal["B", "C"],
) -> list[QuestionReviewOut]:
    return question_service.list_questions_for_review(session, exam_date, part)


@router.get("/questions/{stable_id}", response_model=QuestionPracticeOut)
def get_question(
    stable_id: Annotated[str, Path(pattern=r"^\d{4}-(0[1-9]|1[0-2])_[BC]_(00[1-9]|0[1-3][0-9]|040)$")],
    session: Annotated[Session, Depends(get_session)],
) -> QuestionPracticeOut:
    question = question_service.get_question(session, stable_id)
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    return question


@router.get("/questions/{stable_id}/review", response_model=QuestionReviewOut)
def get_question_for_review(
    stable_id: Annotated[str, Path(pattern=r"^\d{4}-(0[1-9]|1[0-2])_[BC]_(00[1-9]|0[1-3][0-9]|040)$")],
    session: Annotated[Session, Depends(get_session)],
) -> QuestionReviewOut:
    question = question_service.get_question_for_review(session, stable_id)
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    return question
