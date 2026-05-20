from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    part: Mapped[str | None] = mapped_column(String(1), nullable=True)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    answered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    correct_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "mode IN ('exam', 'simulation', 'practice', 'mistakes', 'bookmarks')",
            name="ck_sessions_mode",
        ),
        CheckConstraint("status IN ('active', 'completed', 'abandoned')", name="ck_sessions_status"),
        CheckConstraint("part IS NULL OR part IN ('B', 'C')", name="ck_sessions_part"),
        CheckConstraint("total_questions > 0", name="ck_sessions_total_positive"),
        CheckConstraint("answered_count >= 0", name="ck_sessions_answered_nonneg"),
        CheckConstraint("answered_count <= total_questions", name="ck_sessions_answered_le_total"),
    )
