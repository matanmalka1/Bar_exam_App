from datetime import datetime

from sqlalchemy.orm import Session

from app.repositories import stats_repository, user_repository
from app.schemas.stats import PartStatsOut, StatsOverviewOut


class StatsError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def get_overview(session: Session, user_id: int) -> StatsOverviewOut:
    if user_repository.get_by_id(session, user_id) is None:
        raise StatsError(404, "user not found")

    total_answered, correct_answered = stats_repository.get_answer_totals(session, user_id)
    part_rows = stats_repository.get_answer_totals_by_part(session, user_id)
    parts = {
        row.part: PartStatsOut(
            total_answered=int(row.total_answered),
            success_rate=_success_rate(int(row.correct_answered), int(row.total_answered)),
        )
        for row in part_rows
    }
    completed_session_rows = stats_repository.list_completed_session_stats_inputs(session, user_id)
    valid_durations = _valid_completed_session_durations(completed_session_rows)

    return StatsOverviewOut(
        total_answered=int(total_answered),
        overall_success_rate=_success_rate(int(correct_answered), int(total_answered)),
        part_b=parts.get("B", PartStatsOut(total_answered=0, success_rate=None)),
        part_c=parts.get("C", PartStatsOut(total_answered=0, success_rate=None)),
        simulations_completed=sum(1 for row in completed_session_rows if row.mode == "exam"),
        active_mistakes_count=stats_repository.count_active_mistakes(session, user_id),
        repeated_mistakes_count=stats_repository.count_repeated_mistakes(session, user_id),
        avg_session_duration_seconds=_average_duration_seconds(valid_durations),
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


def _valid_completed_session_durations(rows: list) -> list[tuple[datetime, datetime]]:
    durations: list[tuple[datetime, datetime]] = []
    for row in rows:
        if row.started_at is None or row.completed_at is None:
            continue
        if row.completed_at < row.started_at:
            continue
        durations.append((row.started_at, row.completed_at))
    return durations
