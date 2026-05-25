from pydantic import BaseModel


class PartStatsOut(BaseModel):
    total_answered: int
    success_rate: float | None
    genuine_correct_answers: int
    invalidated_credit_answers: int


class StatsOverviewOut(BaseModel):
    total_answered: int
    overall_success_rate: float | None
    mastery_rate: float | None
    unique_answered_questions: int
    total_answer_attempts: int
    latest_correct_answers: int
    genuine_correct_answers: int
    invalidated_credit_answers: int
    latest_genuine_correct_answers: int
    latest_invalidated_credit_answers: int
    part_b: PartStatsOut
    part_c: PartStatsOut
    simulations_completed: int
    active_mistakes_count: int
    repeated_mistakes_count: int
    avg_session_duration_seconds: int | None
    practices_completed: int
    exams_completed: int
    incorrect_answers: int
    total_study_seconds: int
