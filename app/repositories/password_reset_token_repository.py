from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.models.password_reset_token import PasswordResetToken


def create(
    session: Session,
    *,
    user_id: int,
    token_hash: str,
    expires_at: datetime,
    requested_ip: str | None,
    user_agent: str | None,
) -> PasswordResetToken:
    token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        requested_ip=requested_ip,
        user_agent=user_agent,
    )
    session.add(token)
    session.flush()
    return token


def get_valid_by_token_hash(session: Session, token_hash: str) -> PasswordResetToken | None:
    now = datetime.now(UTC)
    return session.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.expires_at > now,
            PasswordResetToken.used_at.is_(None),
        )
    ).one_or_none()


def invalidate_unused_tokens_for_user(session: Session, user_id: int) -> None:
    now = datetime.now(UTC)
    session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )


def mark_used_atomic(session: Session, token_id: int) -> bool:
    now = datetime.now(UTC)
    result = session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == token_id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount == 1
