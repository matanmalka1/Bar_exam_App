from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stable_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    part: Mapped[str] = mapped_column(String(1), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str] = mapped_column(Text, nullable=False)
    option_b: Mapped[str] = mapped_column(Text, nullable=False)
    option_c: Mapped[str] = mapped_column(Text, nullable=False)
    option_d: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    correct_answer: Mapped[str | None] = mapped_column(String(1), nullable=True)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    invalidation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("exam_date", "part", "number", name="uq_questions_exam_part_number"),
        CheckConstraint("part IN ('B', 'C')", name="ck_questions_part"),
        CheckConstraint("number BETWEEN 1 AND 40", name="ck_questions_number_range"),
        CheckConstraint("status IN ('active', 'invalidated')", name="ck_questions_status"),
        CheckConstraint("length(trim(body)) > 0", name="ck_questions_body_not_empty"),
        CheckConstraint("length(trim(option_a)) > 0", name="ck_questions_option_a_not_empty"),
        CheckConstraint("length(trim(option_b)) > 0", name="ck_questions_option_b_not_empty"),
        CheckConstraint("length(trim(option_c)) > 0", name="ck_questions_option_c_not_empty"),
        CheckConstraint("length(trim(option_d)) > 0", name="ck_questions_option_d_not_empty"),
        CheckConstraint("length(trim(reference)) > 0", name="ck_questions_reference_not_empty"),
        CheckConstraint(
            "("
            "status = 'active' AND correct_answer IN ('A', 'B', 'C', 'D') "
            "AND invalidation_note IS NULL"
            ") OR ("
            "status = 'invalidated' AND correct_answer IS NULL "
            "AND invalidation_note IS NOT NULL AND length(trim(invalidation_note)) > 0"
            ")",
            name="ck_questions_status_answer_invalidation",
        ),
    )
