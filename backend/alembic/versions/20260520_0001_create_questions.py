"""create questions table

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0001"
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_date", "part", "number", name="uq_questions_exam_part_number"),
        sa.UniqueConstraint("stable_id", name="uq_questions_stable_id"),
        sa.CheckConstraint("number BETWEEN 1 AND 40", name="ck_questions_number_range"),
    )
    op.create_index(op.f("ix_questions_exam_date"), "questions", ["exam_date"], unique=False)
    op.create_index(op.f("ix_questions_part"), "questions", ["part"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_questions_part"), table_name="questions")
    op.drop_index(op.f("ix_questions_exam_date"), table_name="questions")
    op.drop_table("questions")
