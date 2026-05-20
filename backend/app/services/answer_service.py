from sqlalchemy.orm import Session

from app.repositories import (
    answer_repository,
    bookmark_repository,
    practice_session_repository,
    question_repository,
    user_repository,
)
from app.schemas.answer import (
    AnswerExamOut,
    AnswerPracticeOut,
    AnswerSubmitIn,
    BookmarkedQuestionOut,
    BookmarkOut,
    MistakeOut,
)
from app.services.question_service import ANSWER_LABELS

HEBREW_TO_DB = {v: k for k, v in ANSWER_LABELS.items()}
DB_TO_HEBREW = ANSWER_LABELS


class AnswerError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def submit_answer(
    session: Session,
    session_id: int,
    user_id: int,
    payload: AnswerSubmitIn,
) -> AnswerPracticeOut | AnswerExamOut:
    ps = practice_session_repository.get_session_by_id(session, session_id)
    if ps is None or ps.user_id != user_id:
        raise AnswerError(404, "session not found")
    if ps.status != "active":
        raise AnswerError(409, f"session is {ps.status}")

    question = question_repository.get_question_by_stable_id(session, payload.stable_id)
    if question is None:
        raise AnswerError(422, "question not found")

    link = practice_session_repository.get_session_question_link(session, session_id, question.id)
    if link is None:
        raise AnswerError(422, "question does not belong to this session")
    if question.status != "active":
        raise AnswerError(422, "cannot answer invalidated question")

    db_answer = HEBREW_TO_DB[payload.selected_answer]
    is_correct = question.correct_answer is not None and question.correct_answer == db_answer

    ua, inserted = answer_repository.insert_user_answer(
        session,
        session_id=session_id,
        question_id=question.id,
        selected_answer=db_answer,
        is_correct=is_correct,
    )
    if inserted:
        practice_session_repository.increment_answered_count(session, session_id)
    session.commit()
    session.refresh(ua)

    if ps.mode in ("exam", "simulation"):
        return AnswerExamOut(
            stable_id=payload.stable_id,
            selected_answer=DB_TO_HEBREW[ua.selected_answer],
            answered_at=ua.answered_at,
        )
    return AnswerPracticeOut(
        stable_id=payload.stable_id,
        selected_answer=DB_TO_HEBREW[ua.selected_answer],
        is_correct=ua.is_correct,
        correct_answer=DB_TO_HEBREW[question.correct_answer] if question.correct_answer else None,
        reference=question.reference,
        answered_at=ua.answered_at,
    )


def list_mistakes(session: Session, user_id: int) -> list[MistakeOut]:
    if user_repository.get_by_id(session, user_id) is None:
        raise AnswerError(404, "user not found")
    rows = answer_repository.get_latest_mistakes(session, user_id)
    result: list[MistakeOut] = []
    for question, times_answered, times_wrong in rows:
        result.append(
            MistakeOut(
                stable_id=question.stable_id,
                number=question.number,
                exam_date=question.exam_date.strftime("%Y-%m"),
                part=question.part,
                body=question.body,
                options={
                    "א": question.option_a,
                    "ב": question.option_b,
                    "ג": question.option_c,
                    "ד": question.option_d,
                },
                correct_answer=(DB_TO_HEBREW[question.correct_answer] if question.correct_answer else None),
                reference=question.reference,
                times_answered=int(times_answered),
                times_wrong=int(times_wrong or 0),
            )
        )
    return result


def add_bookmark(session: Session, user_id: int, stable_id: str) -> BookmarkOut:
    if user_repository.get_by_id(session, user_id) is None:
        raise AnswerError(404, "user not found")
    question = question_repository.get_question_by_stable_id(session, stable_id)
    if question is None:
        raise AnswerError(404, "question not found")
    bm = bookmark_repository.add_bookmark(session, user_id, question.id)
    session.commit()
    session.refresh(bm)
    return BookmarkOut(user_id=user_id, stable_id=stable_id, created_at=bm.created_at)


def remove_bookmark(session: Session, user_id: int, stable_id: str) -> None:
    if user_repository.get_by_id(session, user_id) is None:
        raise AnswerError(404, "user not found")
    question = question_repository.get_question_by_stable_id(session, stable_id)
    if question is None:
        return
    bookmark_repository.remove_bookmark(session, user_id, question.id)
    session.commit()


def list_bookmarks(session: Session, user_id: int) -> list[BookmarkedQuestionOut]:
    if user_repository.get_by_id(session, user_id) is None:
        raise AnswerError(404, "user not found")
    rows = bookmark_repository.list_bookmarks(session, user_id)
    result: list[BookmarkedQuestionOut] = []
    for question, created_at in rows:
        result.append(
            BookmarkedQuestionOut(
                stable_id=question.stable_id,
                exam_date=question.exam_date.strftime("%Y-%m"),
                part=question.part,
                number=question.number,
                body=question.body,
                options={
                    "א": question.option_a,
                    "ב": question.option_b,
                    "ג": question.option_c,
                    "ד": question.option_d,
                },
                status=question.status,
                correct_answer=(DB_TO_HEBREW[question.correct_answer] if question.correct_answer else None),
                reference=question.reference,
                created_at=created_at,
            )
        )
    return result
