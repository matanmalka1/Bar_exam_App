from pydantic import BaseModel


class PartStatsOut(BaseModel):
    total_answered: int
    success_rate: float | None


class StatsOverviewOut(BaseModel):
    total_answered: int
    overall_success_rate: float | None
    part_b: PartStatsOut
    part_c: PartStatsOut
    simulations_completed: int
    active_mistakes_count: int
    repeated_mistakes_count: int
    avg_session_duration_seconds: int | None
