from datetime import date
from typing import TypedDict

from sqlalchemy.orm import Session

from app.models.question import Question
from app.repositories import question_repository
from app.schemas.question import ExamSummary, QuestionOptions, QuestionPracticeOut, QuestionReviewOut

PART_NAMES = {"B": "דין דיוני", "C": "דין מהותי"}
MONTH_LABELS = {"02": "פברואר", "04": "אפריל", "06": "יוני", "09": "ספטמבר", "12": "דצמבר"}
ANSWER_LABELS = {"A": "א", "B": "ב", "C": "ג", "D": "ד"}


class _QuestionBaseFields(TypedDict):
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


def list_exams(session: Session) -> list[ExamSummary]:
    exams = []
    for row in question_repository.get_exams(session):
        exam_date = row.exam_date.strftime("%Y-%m")
        exams.append(
            ExamSummary(
                exam_date=exam_date,
                part=row.part,
                part_name=_part_name(row.part),
                label=_exam_label(exam_date),
                question_count=row.question_count,
            )
        )
    return exams


def list_questions(session: Session, exam_date: str, part: str) -> list[QuestionPracticeOut]:
    parsed_exam_date = _parse_exam_date(exam_date)
    if parsed_exam_date is None:
        return []

    questions = question_repository.get_questions_by_exam(session, parsed_exam_date, part)
    return [_build_question_practice_out(question) for question in questions]


def list_questions_for_review(session: Session, exam_date: str, part: str) -> list[QuestionReviewOut]:
    parsed_exam_date = _parse_exam_date(exam_date)
    if parsed_exam_date is None:
        return []

    questions = question_repository.get_questions_by_exam(session, parsed_exam_date, part)
    return [_build_question_review_out(question) for question in questions]


def get_question(session: Session, stable_id: str) -> QuestionPracticeOut | None:
    question = question_repository.get_question_by_stable_id(session, stable_id)
    if question is None:
        return None
    return _build_question_practice_out(question)


def get_question_for_review(session: Session, stable_id: str) -> QuestionReviewOut | None:
    question = question_repository.get_question_by_stable_id(session, stable_id)
    if question is None:
        return None
    return _build_question_review_out(question)


def _parse_exam_date(value: str) -> date | None:
    year_text, month_text = value.split("-")
    try:
        return date(int(year_text), int(month_text), 1)
    except ValueError:
        return None


def _build_question_practice_out(question: Question) -> QuestionPracticeOut:
    return QuestionPracticeOut(
        **_question_base_fields(question),
    )


def _build_question_review_out(question: Question) -> QuestionReviewOut:
    return QuestionReviewOut(
        **_question_base_fields(question),
        correct_answer=_answer_label(question.correct_answer),
        reference=question.reference,
    )


def _question_base_fields(question: Question) -> _QuestionBaseFields:
    exam_date = question.exam_date.strftime("%Y-%m")
    return {
        "stable_id": question.stable_id,
        "exam_date": exam_date,
        "part": question.part,
        "part_name": _part_name(question.part),
        "label": _exam_label(exam_date),
        "number": question.number,
        "body": question.body,
        "options": QuestionOptions(
            א=question.option_a,
            ב=question.option_b,
            ג=question.option_c,
            ד=question.option_d,
        ),
        "status": question.status,
        "invalidation_note": question.invalidation_note,
    }


def _part_name(part: str) -> str:
    return PART_NAMES[part]


def _exam_label(exam_date: str) -> str:
    year, month = exam_date.split("-")
    month_name = MONTH_LABELS.get(month, month)
    return f"{month_name} {year}"


def _answer_label(answer: str | None) -> str | None:
    if answer is None:
        return None
    return ANSWER_LABELS[answer]
