"""Create a deterministic development user with broad progress data.

Usage:
    python -m scripts.seed_dev_user

Optional:
    python -m scripts.seed_dev_user --email dev@example.com --password DevPass123!
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.db.session import SessionLocal
from app.models.bookmarked_question import BookmarkedQuestion
from app.models.practice_session import PracticeSession
from app.models.practice_session_question import PracticeSessionQuestion
from app.models.question import Question
from app.models.user_answer import UserAnswer
from app.repositories import user_repository

DEFAULT_FULL_NAME = "Dev Seed User"
DEFAULT_EMAIL = "dev@example.com"
DEFAULT_PASSWORD = "DevPass123!"
EXAM_QUESTIONS_PER_PART = 40


class SeedSession(NamedTuple):
    label: str
    row: PracticeSession


def main() -> int:
    args = _parse_args()
    with SessionLocal() as db:
        user = _upsert_user(db, full_name=args.full_name, email=args.email.lower(), password=args.password)
        _clear_user_progress(db, user.id)
        questions = _load_question_pool(db)
        sessions = _seed_progress(db, user.id, questions)
        db.commit()

        print(f"Seeded dev user id={user.id} email={user.email} password={args.password}")
        print("Created sessions:")
        for item in sessions:
            print(
                f"- {item.label}: id={item.row.id} "
                f"mode={item.row.mode} status={item.row.status} "
                f"answered={item.row.answered_count}/{item.row.total_questions}"
            )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-name", default=DEFAULT_FULL_NAME)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    return parser.parse_args()


def _upsert_user(db: Session, *, full_name: str, email: str, password: str):
    user = user_repository.get_by_email(db, email)
    password_hash = hash_password(password)
    if user is None:
        user = user_repository.create(db, full_name=full_name, email=email, password_hash=password_hash)
    else:
        user.full_name = full_name
        user.password_hash = password_hash
        user.is_active = True
        user.token_version += 1
        db.flush()
    return user


def _clear_user_progress(db: Session, user_id: int) -> None:
    session_ids = list(db.scalars(select(PracticeSession.id).where(PracticeSession.user_id == user_id)).all())
    if session_ids:
        db.execute(delete(UserAnswer).where(UserAnswer.session_id.in_(session_ids)))
        db.execute(delete(PracticeSessionQuestion).where(PracticeSessionQuestion.session_id.in_(session_ids)))
        db.execute(delete(PracticeSession).where(PracticeSession.id.in_(session_ids)))
    db.execute(delete(BookmarkedQuestion).where(BookmarkedQuestion.user_id == user_id))
    db.flush()


def _load_question_pool(db: Session) -> dict[str, list[Question]]:
    questions = list(
        db.scalars(
            select(Question).order_by(Question.exam_date.asc(), Question.part.asc(), Question.number.asc())
        ).all()
    )
    if not questions:
        raise SystemExit("No questions found. Run: python scripts/import_questions.py --input-dir outputs")

    active = [q for q in questions if q.status == "active"]
    invalidated = [q for q in questions if q.status == "invalidated"]
    if not invalidated:
        raise SystemExit("No invalidated questions found; dev seed needs imported official invalidated questions.")
    if len([q for q in active if q.part == "B"]) < 20 or len([q for q in active if q.part == "C"]) < 20:
        raise SystemExit("Not enough active questions found for a representative dev seed.")

    full_exam_dates: dict[object, set[str]] = defaultdict(set)
    for q in questions:
        full_exam_dates[q.exam_date].add(q.part)
    full_exam_date = next(
        (
            exam_date
            for exam_date, parts in sorted(full_exam_dates.items())
            if {"B", "C"}.issubset(parts)
            and _count_questions(questions, exam_date=exam_date, part="B") >= EXAM_QUESTIONS_PER_PART
            and _count_questions(questions, exam_date=exam_date, part="C") >= EXAM_QUESTIONS_PER_PART
        ),
        None,
    )
    if full_exam_date is None:
        raise SystemExit("No full B+C exam date found; import at least one full official exam.")

    return {
        "all": questions,
        "active": active,
        "invalidated": invalidated,
        "active_b": [q for q in active if q.part == "B"],
        "active_c": [q for q in active if q.part == "C"],
        "full_exam": [q for q in questions if q.exam_date == full_exam_date and q.part in {"B", "C"}],
    }


def _count_questions(questions: list[Question], *, exam_date, part: str) -> int:
    return sum(1 for q in questions if q.exam_date == exam_date and q.part == part)


def _seed_progress(db: Session, user_id: int, questions: dict[str, list[Question]]) -> list[SeedSession]:
    now = datetime.now(UTC).replace(microsecond=0)
    invalidated = questions["invalidated"][0]
    active_b = _without(questions["active_b"], {invalidated.id})
    active_c = questions["active_c"]

    sessions: list[SeedSession] = []
    sessions.append(
        SeedSession(
            "completed practice with correct, incorrect, invalidated, and unanswered questions",
            _create_session(
                db,
                user_id=user_id,
                mode="practice",
                status="completed",
                questions=[*active_b[0:4], invalidated, *active_c[0:2]],
                started_at=now - timedelta(days=15, minutes=35),
                completed_at=now - timedelta(days=15),
                answers=[
                    (active_b[0], _correct(active_b[0])),
                    (active_b[1], _wrong(active_b[1])),
                    (active_b[2], _wrong(active_b[2])),
                    (invalidated, "A"),
                    (active_c[0], _correct(active_c[0])),
                ],
            ),
        )
    )
    sessions.append(
        SeedSession(
            "completed practice that resolves one earlier mistake",
            _create_session(
                db,
                user_id=user_id,
                mode="practice",
                status="completed",
                questions=[active_b[1], active_b[4], active_c[1], active_c[2]],
                started_at=now - timedelta(days=12, minutes=28),
                completed_at=now - timedelta(days=12),
                answers=[
                    (active_b[1], _correct(active_b[1])),
                    (active_b[4], _correct(active_b[4])),
                    (active_c[1], _wrong(active_c[1])),
                ],
            ),
        )
    )
    sessions.append(
        SeedSession(
            "active practice in progress",
            _create_session(
                db,
                user_id=user_id,
                mode="practice",
                status="active",
                questions=[active_b[5], active_b[6], active_c[3], active_c[4], active_c[5]],
                started_at=now - timedelta(hours=3),
                answers=[
                    (active_b[5], _correct(active_b[5])),
                    (active_b[6], _wrong(active_b[6])),
                ],
            ),
        )
    )
    sessions.append(
        SeedSession(
            "abandoned practice",
            _create_session(
                db,
                user_id=user_id,
                mode="practice",
                status="abandoned",
                questions=[active_b[7], active_b[8], active_c[6]],
                started_at=now - timedelta(days=9, minutes=12),
                answers=[(active_b[7], _wrong(active_b[7]))],
            ),
        )
    )

    full_exam_questions = sorted(questions["full_exam"], key=lambda q: (q.part, q.number))
    full_exam_b = [q for q in full_exam_questions if q.part == "B"]
    full_exam_c = [q for q in full_exam_questions if q.part == "C"]
    sessions.append(
        SeedSession(
            "completed full exam with hidden-until-complete review data",
            _create_session(
                db,
                user_id=user_id,
                mode="exam",
                status="completed",
                questions=full_exam_questions,
                started_at=now - timedelta(days=7, hours=2),
                completed_at=now - timedelta(days=7),
                exam_date=full_exam_questions[0].exam_date,
                answers=_pattern_answers([*full_exam_b[:14], *full_exam_c[:14]], wrong_every=4),
            ),
        )
    )

    simulation_questions = [*questions["active_b"][10:50], *questions["active_c"][10:50]]
    simulation_b = [q for q in simulation_questions if q.part == "B"]
    simulation_c = [q for q in simulation_questions if q.part == "C"]
    sessions.append(
        SeedSession(
            "completed simulation with part breakdown",
            _create_session(
                db,
                user_id=user_id,
                mode="simulation",
                status="completed",
                questions=simulation_questions,
                started_at=now - timedelta(days=5, hours=2, minutes=15),
                completed_at=now - timedelta(days=5),
                answers=_pattern_answers([*simulation_b[:18], *simulation_c[:18]], wrong_every=3),
            ),
        )
    )

    mistake_questions = [active_b[2], active_b[6], active_c[1]]
    sessions.append(
        SeedSession(
            "active mistakes session",
            _create_session(
                db,
                user_id=user_id,
                mode="mistakes",
                status="active",
                questions=mistake_questions,
                started_at=now - timedelta(days=2, hours=2),
                answers=[(active_b[2], _wrong(active_b[2]))],
            ),
        )
    )
    sessions.append(
        SeedSession(
            "completed mistakes session with repeated mistake coverage",
            _create_session(
                db,
                user_id=user_id,
                mode="mistakes",
                status="completed",
                questions=mistake_questions,
                started_at=now - timedelta(days=1, hours=1),
                completed_at=now - timedelta(days=1),
                answers=[
                    (active_b[2], _wrong(active_b[2])),
                    (active_b[6], _wrong(active_b[6])),
                    (active_c[1], _correct(active_c[1])),
                ],
            ),
        )
    )

    bookmark_questions = [active_b[9], active_c[7], invalidated, active_c[8]]
    for q in bookmark_questions:
        db.add(BookmarkedQuestion(user_id=user_id, question_id=q.id))
    sessions.append(
        SeedSession(
            "active bookmarks session",
            _create_session(
                db,
                user_id=user_id,
                mode="bookmarks",
                status="active",
                questions=bookmark_questions,
                started_at=now - timedelta(hours=10),
                answers=[(active_b[9], _correct(active_b[9]))],
            ),
        )
    )
    sessions.append(
        SeedSession(
            "completed bookmarks session",
            _create_session(
                db,
                user_id=user_id,
                mode="bookmarks",
                status="completed",
                questions=bookmark_questions[:3],
                started_at=now - timedelta(days=3, minutes=22),
                completed_at=now - timedelta(days=3),
                answers=[
                    (active_b[9], _correct(active_b[9])),
                    (active_c[7], _wrong(active_c[7])),
                    (invalidated, "B"),
                ],
            ),
        )
    )
    return sessions


def _without(questions: list[Question], question_ids: set[int]) -> list[Question]:
    return [q for q in questions if q.id not in question_ids]


def _create_session(
    db: Session,
    *,
    user_id: int,
    mode: str,
    status: str,
    questions: list[Question],
    started_at: datetime,
    answers: list[tuple[Question, str]],
    completed_at: datetime | None = None,
    exam_date=None,
) -> PracticeSession:
    answered_count = len({q.id for q, _ in answers})
    ps = PracticeSession(
        user_id=user_id,
        mode=mode,
        status=status,
        exam_date=exam_date,
        part=_single_part_or_none(questions),
        total_questions=len(questions),
        answered_count=answered_count,
        started_at=started_at,
        completed_at=completed_at,
        created_at=started_at,
    )
    db.add(ps)
    db.flush()

    for position, q in enumerate(questions, start=1):
        db.add(PracticeSessionQuestion(session_id=ps.id, question_id=q.id, position=position))
    db.flush()

    answer_map = {q.id: (q, selected_answer) for q, selected_answer in answers}
    for q, selected_answer in answer_map.values():
        db.add(
            UserAnswer(
                session_id=ps.id,
                question_id=q.id,
                selected_answer=selected_answer,
                is_correct=q.status == "active" and selected_answer == q.correct_answer,
                answered_at=started_at + timedelta(minutes=5 + len(answer_map)),
            )
        )

    if status == "completed":
        correct_count = _correct_count(questions, answer_map)
        ps.correct_count = correct_count
        ps.score = Decimal(correct_count).quantize(Decimal("0.01"))
        if mode in {"exam", "simulation"}:
            breakdown = _part_breakdown(questions, answer_map)
            ps.part_breakdown_json = json.dumps(breakdown)
    db.flush()
    return ps


def _single_part_or_none(questions: list[Question]) -> str | None:
    parts = {q.part for q in questions}
    if len(parts) == 1:
        return next(iter(parts))
    return None


def _correct_count(questions: list[Question], answer_map: dict[int, tuple[Question, str]]) -> int:
    correct = 0
    for q in questions:
        answer = answer_map.get(q.id)
        if answer is None:
            continue
        _, selected_answer = answer
        if q.status == "invalidated" or selected_answer == q.correct_answer:
            correct += 1
    return correct


def _part_breakdown(questions: list[Question], answer_map: dict[int, tuple[Question, str]]) -> dict[str, dict]:
    breakdown = {}
    for part in ("B", "C"):
        part_questions = [q for q in questions if q.part == part]
        if not part_questions:
            continue
        answered = sum(1 for q in part_questions if q.id in answer_map)
        correct = _correct_count(part_questions, answer_map)
        breakdown[part] = {
            "total": len(part_questions),
            "answered": answered,
            "correct": correct,
            "score": str(Decimal(correct).quantize(Decimal("0.01"))),
            "max_score": EXAM_QUESTIONS_PER_PART,
        }
    return breakdown


def _correct(question: Question) -> str:
    if question.correct_answer is None:
        raise ValueError(f"Question {question.stable_id} has no correct answer")
    return question.correct_answer


def _wrong(question: Question) -> str:
    correct = _correct(question)
    return next(answer for answer in ("A", "B", "C", "D") if answer != correct)


def _pattern_answers(questions: list[Question], *, wrong_every: int) -> list[tuple[Question, str]]:
    answers = []
    for index, question in enumerate(questions, start=1):
        if question.status == "invalidated":
            selected = "A"
        elif index % wrong_every == 0:
            selected = _wrong(question)
        else:
            selected = _correct(question)
        answers.append((question, selected))
    return answers


if __name__ == "__main__":
    raise SystemExit(main())
