from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppError,
    app_error_code_for_status,
    app_error_message_for_status,
    contains_hebrew,
    frontend_safe_details,
)
from app.repositories import stats_repository, user_repository
from app.schemas.stats import PartStatsOut, StatsOverviewOut


class StatsError(AppError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(
            code=app_error_code_for_status(status_code),
            message=detail if contains_hebrew(detail) else app_error_message_for_status(status_code),
            status_code=status_code,
            details=frontend_safe_details(detail),
        )
        self.status_code = status_code
        self.detail = detail


def get_overview(session: Session, user_id: int) -> StatsOverviewOut:
    if user_repository.get_by_id(session, user_id) is None:
        raise StatsError(404, "user not found")

    answer_totals = stats_repository.get_answer_totals(session, user_id)
    total_answered = answer_totals.total_answered
    correct_answered = answer_totals.correct_answered
    genuine_correct = int(answer_totals.genuine_correct)
    invalidated_credit = int(answer_totals.invalidated_credit)
    mastery_row = stats_repository.get_mastery_totals(session, user_id)
    unique_answered = int(mastery_row.unique_answered)
    latest_correct = int(mastery_row.latest_correct)
    latest_genuine_correct = int(mastery_row.latest_genuine_correct)
    latest_invalidated_credit = int(mastery_row.latest_invalidated_credit)
    part_rows = stats_repository.get_answer_totals_by_part(session, user_id)
    parts = {
        row.part: PartStatsOut(
            total_answered=int(row.total_answered),
            success_rate=_success_rate(int(row.correct_answered), int(row.total_answered)),
            genuine_correct_answers=int(row.genuine_correct),
            invalidated_credit_answers=int(row.invalidated_credit),
        )
        for row in part_rows
    }
    completed_session_rows = stats_repository.list_completed_session_stats_inputs(session, user_id)
    valid_durations = _valid_completed_session_durations(completed_session_rows)
    session_counts = stats_repository.get_session_counts_by_mode(session, user_id)

    total_answered_int = int(total_answered)
    correct_answered_int = int(correct_answered)

    return StatsOverviewOut(
        total_answered=total_answered_int,
        overall_success_rate=_success_rate(correct_answered_int, total_answered_int),
        mastery_rate=_success_rate(latest_correct, unique_answered),
        unique_answered_questions=unique_answered,
        total_answer_attempts=total_answered_int,
        latest_correct_answers=latest_correct,
        genuine_correct_answers=genuine_correct,
        invalidated_credit_answers=invalidated_credit,
        latest_genuine_correct_answers=latest_genuine_correct,
        latest_invalidated_credit_answers=latest_invalidated_credit,
        part_b=parts.get(
            "B",
            PartStatsOut(total_answered=0, success_rate=None, genuine_correct_answers=0, invalidated_credit_answers=0),
        ),
        part_c=parts.get(
            "C",
            PartStatsOut(total_answered=0, success_rate=None, genuine_correct_answers=0, invalidated_credit_answers=0),
        ),
        simulations_completed=int(session_counts.simulations_completed),
        active_mistakes_count=stats_repository.count_active_mistakes(session, user_id),
        repeated_mistakes_count=stats_repository.count_repeated_mistakes(session, user_id),
        avg_session_duration_seconds=_average_duration_seconds(valid_durations),
        practices_completed=int(session_counts.practices_completed),
        exams_completed=int(session_counts.exams_completed),
        incorrect_answers=max(0, total_answered_int - correct_answered_int),
        total_study_seconds=_total_study_seconds(valid_durations),
    )


def _success_rate(correct: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(correct / total * 100, 2)


def _average_duration_seconds(durations: list[tuple[datetime, datetime]]) -> int | None:
    if not durations:
        return None
    total_seconds = sum((completed_at - started_at).total_seconds() for started_at, completed_at in durations)
    return round(total_seconds / len(durations))


def _total_study_seconds(durations: list[tuple[datetime, datetime]]) -> int:
    return round(sum((completed_at - started_at).total_seconds() for started_at, completed_at in durations))


def _valid_completed_session_durations(rows: list) -> list[tuple[datetime, datetime]]:
    durations: list[tuple[datetime, datetime]] = []
    for row in rows:
        if row.started_at is None or row.completed_at is None:
            continue
        if row.completed_at < row.started_at:
            continue
        durations.append((row.started_at, row.completed_at))
    return durations
