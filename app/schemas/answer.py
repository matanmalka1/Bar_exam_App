from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.question import QuestionOptions


class AnswerSubmitIn(BaseModel):
    stable_id: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])_[BC]_(00[1-9]|0[1-3][0-9]|040)$")
    selected_answer: str = Field(pattern=r"^[אבגד]$")


class AnswerPracticeOut(BaseModel):
    stable_id: str
    selected_answer: str
    is_correct: bool | None
    scoring_status: Literal["correct", "incorrect", "invalidated"]
    correct_answer: str | None
    reference: str | None
    answered_at: datetime


class AnswerExamOut(BaseModel):
    stable_id: str
    selected_answer: str
    scoring_status: Literal["correct", "incorrect", "invalidated"] | None = None
    answered_at: datetime


class BookmarkOut(BaseModel):
    user_id: int
    stable_id: str
    created_at: datetime


class BookmarkRemovedOut(BaseModel):
    removed: bool


class MistakeOut(BaseModel):
    stable_id: str
    number: int
    exam_date: str
    part: str
    body: str
    options: QuestionOptions
    correct_answer: str | None
    reference: str
    times_answered: int
    times_wrong: int


class BookmarkedQuestionOut(BaseModel):
    stable_id: str
    exam_date: str
    part: str
    number: int
    body: str
    options: QuestionOptions
    status: str
    correct_answer: str | None
    reference: str
    created_at: datetime
