import json
import random
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppError,
    app_error_code_for_status,
    app_error_message_for_status,
    contains_hebrew,
    frontend_safe_details,
)
from app.models.practice_session import PracticeSession
from app.models.question import Question
from app.repositories import (
    answer_repository,
    bookmark_repository,
    practice_session_repository,
    user_repository,
)
from app.schemas.question import QuestionOptions
from app.schemas.session import (
    ExamMistakeOut,
    PartBreakdown,
    SessionAnswerInline,
    SessionCompleteOut,
    SessionCreateIn,
    SessionDetailOut,
    SessionQuestionOut,
    SessionSummaryOut,
)
from app.services.question_service import ANSWER_LABELS

DB_TO_HEBREW = ANSWER_LABELS
ScoringStatus = Literal["correct", "incorrect", "invalidated"]
SCORING_CORRECT = "correct"
SCORING_INCORRECT = "incorrect"
SCORING_INVALIDATED = "invalidated"

EXAM_QUESTIONS_PER_PART = 40
EXAM_TOTAL_QUESTIONS = 80


def _make_rng() -> random.Random:
    return random.Random()


class SessionError(AppError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(
            code=app_error_code_for_status(status_code),
            message=detail if contains_hebrew(detail) else app_error_message_for_status(status_code),
            status_code=status_code,
            details=frontend_safe_details(detail),
        )
        self.status_code = status_code
        self.detail = detail


def create_session(session: Session, user_id: int, payload: SessionCreateIn) -> SessionSummaryOut:
    if payload.mode == "exam":
        ps = _create_exam_session(session, user_id, payload)
    elif payload.mode == "simulation":
        ps = _create_simulation_session(session, user_id, payload)
    elif payload.mode == "mistakes":
        ps = _create_mistakes_session(session, user_id, payload)
    elif payload.mode == "bookmarks":
        ps = _create_bookmarks_session(session, user_id, payload)
    else:
        ps = _create_practice_session(session, user_id, payload)

    session.commit()
    session.refresh(ps)
    return _summary(ps)


def _create_practice_session(session: Session, user_id: int, payload: SessionCreateIn) -> PracticeSession:
    exam_date = _parse_exam_date(payload.exam_date) if payload.exam_date else None
    candidates = practice_session_repository.select_candidate_questions(
        session,
        exam_date=exam_date,
        part=payload.part,
    )
    if not candidates:
        raise SessionError(422, "no matching questions for session filters")
    if payload.question_count is not None and payload.question_count > len(candidates):
        raise SessionError(422, "question_count exceeds available question pool")

    ordered = _select_questions(
        candidates,
        seen_ids=practice_session_repository.list_seen_question_ids(session, user_id),
        question_count=payload.question_count,
    )
    return _persist_session(
        session,
        user_id=user_id,
        mode="practice",
        exam_date=exam_date,
        part=payload.part,
        questions=ordered,
    )


def _create_mistakes_session(session: Session, user_id: int, payload: SessionCreateIn) -> PracticeSession:
    _reject_filters(payload, mode="mistakes")
    pool = answer_repository.list_active_mistake_questions(session, user_id)
    if not pool:
        raise SessionError(422, "no active mistakes to practice")
    if payload.question_count is not None and payload.question_count > len(pool):
        raise SessionError(422, "question_count exceeds available mistakes pool")

    pool = _select_questions(
        pool,
        seen_ids=practice_session_repository.list_seen_question_ids(session, user_id),
        question_count=payload.question_count,
    )
    return _persist_session(
        session,
        user_id=user_id,
        mode="mistakes",
        exam_date=None,
        part=None,
        questions=pool,
    )


def _create_bookmarks_session(session: Session, user_id: int, payload: SessionCreateIn) -> PracticeSession:
    _reject_filters(payload, mode="bookmarks")
    pool = bookmark_repository.list_bookmarked_questions(session, user_id)
    if not pool:
        raise SessionError(422, "no bookmarked questions to practice")
    if payload.question_count is not None and payload.question_count > len(pool):
        raise SessionError(422, "question_count exceeds available bookmarks pool")

    pool = _select_questions(
        pool,
        seen_ids=practice_session_repository.list_seen_question_ids(session, user_id),
        question_count=payload.question_count,
    )
    return _persist_session(
        session,
        user_id=user_id,
        mode="bookmarks",
        exam_date=None,
        part=None,
        questions=pool,
    )


def _create_exam_session(session: Session, user_id: int, payload: SessionCreateIn) -> PracticeSession:
    if payload.exam_date is None:
        raise SessionError(422, "exam mode requires exam_date")
    if payload.question_count is not None:
        raise SessionError(422, "exam mode does not accept question_count")

    exam_date = _parse_exam_date(payload.exam_date)
    rng = _make_rng()

    if payload.part is not None:
        pool = practice_session_repository.select_official_exam_questions(
            session, exam_date=exam_date, part=payload.part
        )
        if len(pool) < EXAM_QUESTIONS_PER_PART:
            raise SessionError(
                422,
                f"insufficient part {payload.part} questions for exam {payload.exam_date} (need 40)",
            )
        rng.shuffle(pool)
        ordered = pool[:EXAM_QUESTIONS_PER_PART]
    else:
        b_pool = practice_session_repository.select_official_exam_questions(session, exam_date=exam_date, part="B")
        c_pool = practice_session_repository.select_official_exam_questions(session, exam_date=exam_date, part="C")
        if len(b_pool) < EXAM_QUESTIONS_PER_PART:
            raise SessionError(422, f"insufficient part B questions for exam {payload.exam_date} (need 40)")
        if len(c_pool) < EXAM_QUESTIONS_PER_PART:
            raise SessionError(422, f"insufficient part C questions for exam {payload.exam_date} (need 40)")
        rng.shuffle(b_pool)
        rng.shuffle(c_pool)
        ordered = b_pool[:EXAM_QUESTIONS_PER_PART] + c_pool[:EXAM_QUESTIONS_PER_PART]
        assert len(ordered) == EXAM_TOTAL_QUESTIONS

    return _persist_session(
        session,
        user_id=user_id,
        mode="exam",
        exam_date=exam_date,
        part=payload.part,
        questions=ordered,
    )


def _create_simulation_session(session: Session, user_id: int, payload: SessionCreateIn) -> PracticeSession:
    if payload.exam_date is not None:
        raise SessionError(422, "simulation mode does not accept exam_date")
    if payload.part is not None:
        raise SessionError(422, "simulation mode does not accept part")
    if payload.question_count is not None:
        raise SessionError(422, "simulation mode does not accept question_count")

    b_pool = practice_session_repository.select_exam_candidates(session, part="B")
    c_pool = practice_session_repository.select_exam_candidates(session, part="C")
    if len(b_pool) < EXAM_QUESTIONS_PER_PART:
        raise SessionError(422, "insufficient part B questions for simulation (need 40)")
    if len(c_pool) < EXAM_QUESTIONS_PER_PART:
        raise SessionError(422, "insufficient part C questions for simulation (need 40)")

    seen_ids = practice_session_repository.list_seen_question_ids(session, user_id)
    b_chosen = _select_questions(b_pool, seen_ids=seen_ids, question_count=EXAM_QUESTIONS_PER_PART)
    c_chosen = _select_questions(c_pool, seen_ids=seen_ids, question_count=EXAM_QUESTIONS_PER_PART)
    ordered = b_chosen + c_chosen
    assert len(ordered) == EXAM_TOTAL_QUESTIONS
    return _persist_session(
        session,
        user_id=user_id,
        mode="simulation",
        exam_date=None,
        part=None,
        questions=ordered,
    )


def _persist_session(
    session: Session,
    *,
    user_id: int,
    mode: str,
    exam_date: date | None,
    part: str | None,
    questions: list[Question],
) -> PracticeSession:
    ps = practice_session_repository.create_session(
        session,
        user_id=user_id,
        mode=mode,
        exam_date=exam_date,
        part=part,
        total_questions=len(questions),
    )
    practice_session_repository.add_session_questions(session, ps.id, [q.id for q in questions])
    return ps


def _reject_filters(payload: SessionCreateIn, *, mode: str) -> None:
    if payload.exam_date is not None:
        raise SessionError(422, f"{mode} mode does not accept exam_date")
    if payload.part is not None:
        raise SessionError(422, f"{mode} mode does not accept part")


def get_session_detail(session: Session, session_id: int, user_id: int) -> SessionDetailOut:
    ps = practice_session_repository.get_session_by_id(session, session_id)
    if ps is None or ps.user_id != user_id:
        raise SessionError(404, "session not found")
    rows = practice_session_repository.get_session_questions(session, session_id)
    answers = {a.question_id: a for a in answer_repository.list_session_answers(session, session_id)}

    question_outs: list[SessionQuestionOut] = []
    for position, question in rows:
        ua = answers.get(question.id)
        user_answered = ua is not None
        expose = _expose_for_question(ps, user_answered=user_answered)
        answer_inline: SessionAnswerInline | None = None
        if ua is not None:
            is_correct = None if question.status == "invalidated" else ua.is_correct
            answer_inline = SessionAnswerInline(
                selected_answer=DB_TO_HEBREW[ua.selected_answer],
                is_correct=is_correct if expose else None,
                scoring_status=_scoring_status(question, ua) if expose else None,
                answered_at=ua.answered_at,
            )
        item = SessionQuestionOut(
            position=position,
            stable_id=question.stable_id,
            number=question.number,
            body=question.body,
            options=QuestionOptions.model_validate({
                "א": question.option_a,
                "ב": question.option_b,
                "ג": question.option_c,
                "ד": question.option_d,
            }),
            status=question.status,
            invalidation_note=question.invalidation_note,
            answer=answer_inline,
            correct_answer=_hebrew_or_none(question.correct_answer) if expose else None,
            reference=question.reference if expose else None,
        )
        question_outs.append(item)

    summary = _summary(ps).model_dump()
    return SessionDetailOut(**summary, questions=question_outs)


def list_user_sessions(
    session: Session, user_id: int, status: str | None, mode: str | None = None
) -> list[SessionSummaryOut]:
    if user_repository.get_by_id(session, user_id) is None:
        raise SessionError(404, "user not found")
    sessions = practice_session_repository.list_sessions_by_user(session, user_id, status, mode)
    return [_summary(s) for s in sessions]


def complete_session(session: Session, session_id: int, user_id: int) -> SessionCompleteOut:
    ps = practice_session_repository.get_session_by_id(session, session_id)
    if ps is None or ps.user_id != user_id:
        raise SessionError(404, "session not found")
    if ps.status != "active":
        raise SessionError(409, f"session is {ps.status}")

    rows = practice_session_repository.get_session_questions(session, session_id)
    answers = answer_repository.list_session_answers(session, session_id)
    answers_by_qid = {a.question_id: a for a in answers}
    correct_count = _scored_correct_count(rows, answers_by_qid)
    score_denominator = ps.total_questions
    now = datetime.now(UTC)
    part_breakdown: dict[str, PartBreakdown] | None = None
    mistakes: list[ExamMistakeOut] | None = None
    part_breakdown_json: str | None = None
    if ps.mode in ("exam", "simulation"):
        part_breakdown = _build_part_breakdown(rows, answers_by_qid)
        mistakes = _build_exam_mistakes(rows, answers_by_qid)
        part_breakdown_json = json.dumps({k: v.model_dump(mode="json") for k, v in part_breakdown.items()})
        score, max_score = _exam_score(part_breakdown)
    else:
        score = Decimal(correct_count)
        max_score = score_denominator

    practice_session_repository.complete_session(
        session,
        session_id,
        correct_count=correct_count,
        score=score,
        completed_at=now,
        part_breakdown_json=part_breakdown_json,
    )

    session.commit()
    session.refresh(ps)
    return SessionCompleteOut(
        id=ps.id,
        status=ps.status,
        total_questions=ps.total_questions,
        scorable_questions=score_denominator,
        answered_count=ps.answered_count,
        correct_count=ps.correct_count or 0,
        score=ps.score or Decimal("0.00"),
        max_score=max_score,
        completed_at=ps.completed_at or now,
        part_breakdown=part_breakdown,
        mistakes=mistakes,
    )


def abandon_session(session: Session, session_id: int, user_id: int) -> None:
    ps = practice_session_repository.get_session_by_id(session, session_id)
    if ps is None or ps.user_id != user_id:
        raise SessionError(404, "session not found")
    if ps.status != "active":
        raise SessionError(409, f"session is {ps.status}")
    practice_session_repository.abandon_session(session, session_id)
    session.commit()


def _exam_score(part_breakdown: dict[str, PartBreakdown]) -> tuple[Decimal, int]:
    """Returns (score, max_score). Each part contributes up to 40 points (1 point per question)."""
    total_score = sum((p.score for p in part_breakdown.values()), Decimal("0"))
    max_score = len(part_breakdown) * EXAM_QUESTIONS_PER_PART
    return total_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), max_score


def _build_part_breakdown(rows: list, answers_by_qid: dict) -> dict[str, PartBreakdown]:
    breakdown: dict[str, PartBreakdown] = {}
    for part in ("B", "C"):
        part_questions = [q for _, q in rows if q.part == part]
        total = len(part_questions)
        if total == 0:
            continue
        answered = 0
        correct = 0
        for q in part_questions:
            ua = answers_by_qid.get(q.id)
            if ua is not None:
                answered += 1
            if ua is not None and (q.status == "invalidated" or ua.is_correct):
                correct += 1
        breakdown[part] = PartBreakdown(
            total=total,
            answered=answered,
            correct=correct,
            score=Decimal(correct),
            max_score=EXAM_QUESTIONS_PER_PART,
        )
    return breakdown


def _build_exam_mistakes(rows: list, answers_by_qid: dict) -> list[ExamMistakeOut]:
    mistakes: list[ExamMistakeOut] = []
    for _, q in rows:
        if q.status == "invalidated":
            continue
        ua = answers_by_qid.get(q.id)
        if ua is not None and ua.is_correct:
            continue
        assert q.correct_answer is not None
        mistakes.append(
            ExamMistakeOut(
                stable_id=q.stable_id,
                part=q.part,
                number=q.number,
                body=q.body,
                options=QuestionOptions.model_validate({
                    "א": q.option_a,
                    "ב": q.option_b,
                    "ג": q.option_c,
                    "ד": q.option_d,
                }),
                selected_answer=DB_TO_HEBREW[ua.selected_answer] if ua is not None else None,
                correct_answer=DB_TO_HEBREW[q.correct_answer],
                reference=q.reference,
            )
        )
    return mistakes


def _scored_correct_count(rows: list, answers_by_qid: dict) -> int:
    correct = 0
    for _, question in rows:
        answer = answers_by_qid.get(question.id)
        if answer is not None and (question.status == "invalidated" or answer.is_correct):
            correct += 1
    return correct


def _select_questions(
    candidates: list[Question],
    *,
    seen_ids: set[int],
    question_count: int | None,
) -> list[Question]:
    unseen = [q for q in candidates if q.id not in seen_ids]
    seen = [q for q in candidates if q.id in seen_ids]
    rng = _make_rng()
    rng.shuffle(unseen)
    rng.shuffle(seen)
    ordered = unseen + seen
    if question_count is not None:
        ordered = ordered[:question_count]
    return ordered


def _summary(ps: PracticeSession) -> SessionSummaryOut:
    part_breakdown = None
    if ps.part_breakdown_json:
        raw = json.loads(ps.part_breakdown_json)
        part_breakdown = {k: PartBreakdown(**v) for k, v in raw.items()}
    max_score: int | None = None
    if ps.status == "completed" and part_breakdown is not None:
        max_score = len(part_breakdown) * EXAM_QUESTIONS_PER_PART
    elif ps.status == "completed":
        max_score = ps.total_questions
    return SessionSummaryOut(
        id=ps.id,
        user_id=ps.user_id,
        mode=ps.mode,
        status=ps.status,
        exam_date=ps.exam_date.strftime("%Y-%m") if ps.exam_date else None,
        part=ps.part,
        total_questions=ps.total_questions,
        answered_count=ps.answered_count,
        correct_count=ps.correct_count,
        score=ps.score,
        max_score=max_score,
        started_at=ps.started_at,
        completed_at=ps.completed_at,
        created_at=ps.created_at,
        part_breakdown=part_breakdown,
    )


def _expose_for_question(ps: PracticeSession, *, user_answered: bool) -> bool:
    if ps.mode in ("exam", "simulation"):
        return ps.status == "completed"
    return user_answered


def _hebrew_or_none(db_letter: str | None) -> str | None:
    if db_letter is None:
        return None
    return DB_TO_HEBREW[db_letter]


def _scoring_status(question: Question, answer) -> ScoringStatus:
    if question.status == "invalidated":
        return SCORING_INVALIDATED
    return SCORING_CORRECT if answer.is_correct else SCORING_INCORRECT


def _parse_exam_date(value: str) -> date:
    year_text, month_text = value.split("-")
    return date(int(year_text), int(month_text), 1)
