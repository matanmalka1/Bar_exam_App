from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PracticeSessionQuestion(Base):
    __tablename__ = "practice_session_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_psq_session_question"),
        UniqueConstraint("session_id", "position", name="uq_psq_session_position"),
        CheckConstraint("position >= 1", name="ck_psq_position_positive"),
    )
