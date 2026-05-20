import random
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.practice_session import PracticeSession
from app.models.question import Question
from app.repositories import answer_repository, session_repository, user_repository
from app.schemas.session import (
    SessionCompleteOut,
    SessionCreateIn,
    SessionDetailOut,
    SessionQuestionOut,
    SessionSummaryOut,
)
from app.services.question_service import ANSWER_LABELS

DB_TO_HEBREW = ANSWER_LABELS


def _make_rng() -> random.Random:
    return random.Random()


class SessionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def create_session(session: Session, payload: SessionCreateIn) -> SessionSummaryOut:
    # TODO(auth): user_id comes from the request body — replace with verified identity.
    if user_repository.get_by_id(session, payload.user_id) is None:
        raise SessionError(404, "user not found")

    exam_date = _parse_exam_date(payload.exam_date) if payload.exam_date else None
    candidates = session_repository.select_candidate_questions(
        session,
        exam_date=exam_date,
        part=payload.part,
        include_invalidated=payload.include_invalidated,
    )
    if not candidates:
        raise SessionError(422, "no matching questions for session filters")
    if payload.question_count is not None and payload.question_count > len(candidates):
        raise SessionError(422, "question_count exceeds available question pool")

    ordered = _select_questions(
        candidates,
        seen_ids=session_repository.list_seen_question_ids(session, payload.user_id),
        question_count=payload.question_count,
    )

    ps = session_repository.create_session(
        session,
        user_id=payload.user_id,
        mode=payload.mode,
        exam_date=exam_date,
        part=payload.part,
        total_questions=len(ordered),
    )
    session_repository.add_session_questions(session, ps.id, [q.id for q in ordered])
    session.commit()
    session.refresh(ps)
    return _summary(ps)


def get_session_detail(session: Session, session_id: int) -> SessionDetailOut:
    ps = session_repository.get_session_by_id(session, session_id)
    if ps is None:
        raise SessionError(404, "session not found")
    rows = session_repository.get_session_questions(session, session_id)
    answers = {a.question_id: a for a in answer_repository.list_session_answers(session, session_id)}

    expose_answer_key = _expose_answer_key(ps)
    question_outs: list[SessionQuestionOut] = []
    for position, question in rows:
        ua = answers.get(question.id)
        answer_inline = None
        if ua is not None:
            answer_inline = {
                "selected_answer": DB_TO_HEBREW[ua.selected_answer],
                "is_correct": ua.is_correct if expose_answer_key else None,
                "answered_at": ua.answered_at,
            }
        item = SessionQuestionOut(
            position=position,
            stable_id=question.stable_id,
            number=question.number,
            body=question.body,
            options={
                "א": question.option_a,
                "ב": question.option_b,
                "ג": question.option_c,
                "ד": question.option_d,
            },
            status=question.status,
            answer=answer_inline,
            correct_answer=_hebrew_or_none(question.correct_answer) if expose_answer_key else None,
            reference=question.reference if expose_answer_key else None,
        )
        question_outs.append(item)

    summary = _summary(ps).model_dump()
    return SessionDetailOut(**summary, questions=question_outs)


def list_user_sessions(session: Session, user_id: int, status: str | None) -> list[SessionSummaryOut]:
    if user_repository.get_by_id(session, user_id) is None:
        raise SessionError(404, "user not found")
    sessions = session_repository.list_sessions_by_user(session, user_id, status)
    return [_summary(s) for s in sessions]


def complete_session(session: Session, session_id: int) -> SessionCompleteOut:
    ps = session_repository.get_session_by_id(session, session_id)
    if ps is None:
        raise SessionError(404, "session not found")
    if ps.status != "active":
        raise SessionError(409, f"session is {ps.status}")

    answers = answer_repository.list_session_answers(session, session_id)
    correct_count = sum(1 for a in answers if a.is_correct)
    score = (Decimal(correct_count * 100) / Decimal(ps.total_questions)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    now = datetime.now(UTC)
    session_repository.complete_session(
        session,
        session_id,
        correct_count=correct_count,
        score_percent=score,
        completed_at=now,
    )
    session.commit()
    session.refresh(ps)
    return SessionCompleteOut(
        id=ps.id,
        status=ps.status,
        total_questions=ps.total_questions,
        answered_count=ps.answered_count,
        correct_count=ps.correct_count or 0,
        score_percent=ps.score_percent or Decimal("0.00"),
        completed_at=ps.completed_at or now,
    )


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
        score_percent=ps.score_percent,
        started_at=ps.started_at,
        completed_at=ps.completed_at,
        created_at=ps.created_at,
    )


def _expose_answer_key(ps: PracticeSession) -> bool:
    if ps.mode in ("practice", "mistakes"):
        return True
    return ps.status == "completed"


def _hebrew_or_none(db_letter: str | None) -> str | None:
    if db_letter is None:
        return None
    return DB_TO_HEBREW[db_letter]


def _parse_exam_date(value: str) -> date:
    year_text, month_text = value.split("-")
    return date(int(year_text), int(month_text), 1)
