"""add bookmarks mode to practice_sessions.mode check constraint

Revision ID: 20260520_0003
Revises: 20260520_0002
Create Date: 2026-05-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260520_0003"
down_revision: str | None = "20260520_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_sessions_mode", "practice_sessions", type_="check")
    op.create_check_constraint(
        "ck_sessions_mode",
        "practice_sessions",
        "mode IN ('exam', 'practice', 'mistakes', 'bookmarks')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sessions_mode", "practice_sessions", type_="check")
    op.create_check_constraint(
        "ck_sessions_mode",
        "practice_sessions",
        "mode IN ('exam', 'practice', 'mistakes')",
    )
