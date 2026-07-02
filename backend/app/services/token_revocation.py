"""Spec v15.4 — server-side JWT revocation on logout."""
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import RevokedToken


def cleanup_expired_revoked_tokens(db: Session) -> None:
    """Drop revocation rows past token expiry — keeps table small."""
    now = datetime.now(UTC)
    db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
    db.flush()


def is_token_revoked(db: Session, jti: str) -> bool:
    return (
        db.scalar(select(RevokedToken.id).where(RevokedToken.jti == jti)) is not None
    )


def revoke_token(
    db: Session,
    *,
    jti: str,
    expires_at: datetime,
    user_id: int | None,
) -> None:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    cleanup_expired_revoked_tokens(db)
    row = RevokedToken(jti=jti, expires_at=expires_at, user_id=user_id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
