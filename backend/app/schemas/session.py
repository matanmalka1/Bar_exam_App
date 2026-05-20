from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.question import QuestionOptions


class SessionCreateIn(BaseModel):
    mode: Literal["exam", "simulation", "practice", "mistakes", "bookmarks"]
    exam_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    part: Literal["B", "C"] | None = None
    question_count: int | None = Field(default=None, gt=0)
    include_invalidated: bool = False

    model_config = ConfigDict(extra="forbid")


class SessionSummaryOut(BaseModel):
    id: int
    user_id: int
    mode: str
    status: str
    exam_date: str | None
    part: str | None
    total_questions: int
    answered_count: int
    correct_count: int | None
    score_percent: Decimal | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionAnswerInline(BaseModel):
    selected_answer: str
    is_correct: bool | None = None
    answered_at: datetime


class SessionQuestionOut(BaseModel):
    position: int
    stable_id: str
    number: int
    body: str
    options: QuestionOptions
    status: str
    answer: SessionAnswerInline | None
    correct_answer: str | None = None
    reference: str | None = None


class SessionDetailOut(SessionSummaryOut):
    questions: list[SessionQuestionOut]


class PartBreakdown(BaseModel):
    total: int
    answered: int
    correct: int
    score_percent: Decimal


class ExamMistakeOut(BaseModel):
    stable_id: str
    part: str
    number: int
    body: str
    options: QuestionOptions
    selected_answer: str | None
    correct_answer: str
    reference: str


class SessionCompleteOut(BaseModel):
    id: int
    status: str
    total_questions: int
    scorable_questions: int
    answered_count: int
    correct_count: int
    score_percent: Decimal
    completed_at: datetime
    part_breakdown: dict[str, PartBreakdown] | None = None
    mistakes: list[ExamMistakeOut] | None = None
