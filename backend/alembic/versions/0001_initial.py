"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stable_id", sa.String(length=32), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=False),
        sa.Column("part", sa.String(length=1), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("option_a", sa.Text(), nullable=False),
        sa.Column("option_b", sa.Text(), nullable=False),
        sa.Column("option_c", sa.Text(), nullable=False),
        sa.Column("option_d", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("correct_answer", sa.String(length=1), nullable=True),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("invalidation_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("part IN ('B', 'C')", name="ck_questions_part"),
        sa.CheckConstraint("status IN ('active', 'invalidated')", name="ck_questions_status"),
        sa.CheckConstraint("length(trim(body)) > 0", name="ck_questions_body_not_empty"),
        sa.CheckConstraint("length(trim(option_a)) > 0", name="ck_questions_option_a_not_empty"),
        sa.CheckConstraint("length(trim(option_b)) > 0", name="ck_questions_option_b_not_empty"),
        sa.CheckConstraint("length(trim(option_c)) > 0", name="ck_questions_option_c_not_empty"),
        sa.CheckConstraint("length(trim(option_d)) > 0", name="ck_questions_option_d_not_empty"),
        sa.CheckConstraint("length(trim(reference)) > 0", name="ck_questions_reference_not_empty"),
        sa.CheckConstraint(
            "("
            "status = 'active' AND correct_answer IN ('A', 'B', 'C', 'D') "
            "AND invalidation_note IS NULL"
            ") OR ("
            "status = 'invalidated' AND correct_answer IS NULL "
            "AND invalidation_note IS NOT NULL AND length(trim(invalidation_note)) > 0"
            ")",
            name="ck_questions_status_answer_invalidation",
        ),
        sa.CheckConstraint("number BETWEEN 1 AND 40", name="ck_questions_number_range"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_date", "part", "number", name="uq_questions_exam_part_number"),
        sa.UniqueConstraint("stable_id", name="uq_questions_stable_id"),
    )
    op.create_index("ix_questions_exam_date", "questions", ["exam_date"])
    op.create_index("ix_questions_part", "questions", ["part"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(full_name)) > 0", name="ck_users_full_name_not_empty"),
        sa.CheckConstraint("length(trim(email)) > 0", name="ck_users_email_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("requested_ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_prt_token_hash"),
    )
    op.create_index("ix_prt_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_prt_expires_at", "password_reset_tokens", ["expires_at"])

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
        sa.Column("part_breakdown_json", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "mode IN ('exam', 'simulation', 'practice', 'mistakes', 'bookmarks')",
            name="ck_sessions_mode",
        ),
        sa.CheckConstraint("status IN ('active', 'completed', 'abandoned')", name="ck_sessions_status"),
        sa.CheckConstraint("part IS NULL OR part IN ('B', 'C')", name="ck_sessions_part"),
        sa.CheckConstraint("total_questions > 0", name="ck_sessions_total_positive"),
        sa.CheckConstraint("answered_count >= 0", name="ck_sessions_answered_nonneg"),
        sa.CheckConstraint("answered_count <= total_questions", name="ck_sessions_answered_le_total"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_sessions_user_id", "practice_sessions", ["user_id"])
    op.create_index("ix_practice_sessions_user_status", "practice_sessions", ["user_id", "status"])

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
    op.create_index("ix_psq_session_id", "practice_session_questions", ["session_id"])

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
    op.create_index("ix_user_answers_session_id", "user_answers", ["session_id"])
    op.create_index("ix_user_answers_question_id", "user_answers", ["question_id"])
    op.create_index("ix_user_answers_question_updated", "user_answers", ["question_id", "updated_at"])

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
    op.create_index("ix_bookmarks_user_id", "bookmarked_questions", ["user_id"])


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
    op.drop_index("ix_prt_expires_at", table_name="password_reset_tokens")
    op.drop_index("ix_prt_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("users")
    op.drop_index("ix_questions_part", table_name="questions")
    op.drop_index("ix_questions_exam_date", table_name="questions")
    op.drop_table("questions")
