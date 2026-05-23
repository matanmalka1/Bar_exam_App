"""add part_breakdown_json to practice_sessions

Revision ID: 20260523_0007
Revises: 20260521_0006
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260523_0007"
down_revision: str | None = "20260521_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "practice_sessions",
        sa.Column("part_breakdown_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("practice_sessions", "part_breakdown_json")
