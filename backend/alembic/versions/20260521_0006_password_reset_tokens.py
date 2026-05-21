"""add password_reset_tokens table

Revision ID: 20260521_0006
Revises: 20260520_0005
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260521_0006"
down_revision: str | None = "20260520_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("requested_ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
    )
    op.create_unique_constraint("uq_prt_token_hash", "password_reset_tokens", ["token_hash"])
    op.create_index("ix_prt_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_prt_expires_at", "password_reset_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_prt_expires_at", table_name="password_reset_tokens")
    op.drop_index("ix_prt_user_id", table_name="password_reset_tokens")
    op.drop_constraint("uq_prt_token_hash", "password_reset_tokens", type_="unique")
    op.drop_table("password_reset_tokens")
