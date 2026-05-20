"""user auth columns

Revision ID: 20260520_0005
Revises: 20260520_0004
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260520_0005"
down_revision: str | None = "20260520_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_users_display_name_not_empty", "users", type_="check")
    op.drop_constraint("uq_users_user_key", "users", type_="unique")
    op.drop_column("users", "user_key")
    op.alter_column("users", "display_name", new_column_name="full_name")

    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE users SET email = 'user-' || id || '@local', password_hash = '!' WHERE email IS NULL")

    op.alter_column("users", "email", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_check_constraint("ck_users_full_name_not_empty", "users", "length(trim(full_name)) > 0")
    op.create_check_constraint("ck_users_email_not_empty", "users", "length(trim(email)) > 0")


def downgrade() -> None:
    op.drop_constraint("ck_users_email_not_empty", "users", type_="check")
    op.drop_constraint("ck_users_full_name_not_empty", "users", type_="check")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "token_version")
    op.drop_column("users", "is_active")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
    op.alter_column("users", "full_name", new_column_name="display_name")
    op.add_column("users", sa.Column("user_key", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_users_user_key", "users", ["user_key"])
    op.create_check_constraint("ck_users_display_name_not_empty", "users", "length(trim(display_name)) > 0")
