"""rename score_percent to score in practice_sessions

Revision ID: 0002_rename_score_percent_to_score
Revises: 0001_initial
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_rename_score_percent_to_score"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("practice_sessions", "score_percent", new_column_name="score")


def downgrade() -> None:
    op.alter_column("practice_sessions", "score", new_column_name="score_percent")
