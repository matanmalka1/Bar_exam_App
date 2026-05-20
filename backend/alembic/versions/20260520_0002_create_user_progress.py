"""create user progress tables

Revision ID: 20260520_0002
Revises: 20260520_0001
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260520_0002"
down_revision: str | None = "20260520_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("user_key", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(display_name)) > 0", name="ck_users_display_name_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_key", name="uq_users_user_key"),
    )

    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=True),
        sa.Column("part", sa.String(length=1), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("answered_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("correct_count", sa.Integer(), nullable=True),
        sa.Column("score_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("mode IN ('exam', 'practice', 'mistakes')", name="ck_sessions_mode"),
        sa.CheckConstraint("status IN ('active', 'completed', 'abandoned')", name="ck_sessions_status"),
        sa.CheckConstraint("part IS NULL OR part IN ('B', 'C')", name="ck_sessions_part"),
        sa.CheckConstraint("total_questions > 0", name="ck_sessions_total_positive"),
        sa.CheckConstraint("answered_count >= 0", name="ck_sessions_answered_nonneg"),
        sa.CheckConstraint("answered_count <= total_questions", name="ck_sessions_answered_le_total"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_sessions_user_id", "practice_sessions", ["user_id"], unique=False)
    op.create_index(
        "ix_practice_sessions_user_status",
        "practice_sessions",
        ["user_id", "status"],
        unique=False,
    )

    op.create_table(
        "practice_session_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("position >= 1", name="ck_psq_position_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "question_id", name="uq_psq_session_question"),
        sa.UniqueConstraint("session_id", "position", name="uq_psq_session_position"),
    )
    op.create_index("ix_psq_session_id", "practice_session_questions", ["session_id"], unique=False)

    op.create_table(
        "user_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("selected_answer", sa.String(length=1), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("selected_answer IN ('A', 'B', 'C', 'D')", name="ck_user_answers_selected"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "question_id", name="uq_user_answers_session_question"),
    )
    op.create_index("ix_user_answers_session_id", "user_answers", ["session_id"], unique=False)
    op.create_index("ix_user_answers_question_id", "user_answers", ["question_id"], unique=False)
    op.create_index(
        "ix_user_answers_question_updated",
        "user_answers",
        ["question_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "bookmarked_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "question_id", name="uq_bookmarks_user_question"),
    )
    op.create_index("ix_bookmarks_user_id", "bookmarked_questions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bookmarks_user_id", table_name="bookmarked_questions")
    op.drop_table("bookmarked_questions")
    op.drop_index("ix_user_answers_question_updated", table_name="user_answers")
    op.drop_index("ix_user_answers_question_id", table_name="user_answers")
    op.drop_index("ix_user_answers_session_id", table_name="user_answers")
    op.drop_table("user_answers")
    op.drop_index("ix_psq_session_id", table_name="practice_session_questions")
    op.drop_table("practice_session_questions")
    op.drop_index("ix_practice_sessions_user_status", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_user_id", table_name="practice_sessions")
    op.drop_table("practice_sessions")
    op.drop_table("users")
