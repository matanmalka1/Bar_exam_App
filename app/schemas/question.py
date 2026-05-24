from pydantic import BaseModel, ConfigDict


class ExamSummary(BaseModel):
    exam_date: str
    part: str
    part_name: str
    label: str
    question_count: int

    model_config = ConfigDict(from_attributes=True)


class QuestionOptions(BaseModel):
    א: str
    ב: str
    ג: str
    ד: str

    model_config = ConfigDict(from_attributes=True)


class QuestionPracticeOut(BaseModel):
    stable_id: str
    exam_date: str
    part: str
    part_name: str
    label: str
    number: int
    body: str
    options: QuestionOptions
    status: str
    invalidation_note: str | None

    model_config = ConfigDict(from_attributes=True)


class QuestionReviewOut(QuestionPracticeOut):
    correct_answer: str | None
    reference: str
