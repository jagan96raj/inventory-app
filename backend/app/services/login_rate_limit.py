"""Per-email login rate limiting (Spec v15.5)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import normalize_auth_email
from app.models.entities import LoginRateLimit


def _lockout_message(locked_until: datetime) -> str:
    now = datetime.now(UTC)
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    remaining_seconds = max(0, int((locked_until - now).total_seconds()))
    minutes = max(1, (remaining_seconds + 59) // 60)
    suffix = "minute" if minutes == 1 else "minutes"
    return f"Too many failed login attempts. Try again in {minutes} {suffix}."


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _prune_stale_rows(db: Session) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=7)
    db.execute(
        delete(LoginRateLimit).where(
            LoginRateLimit.locked_until.is_(None),
            LoginRateLimit.failed_attempts == 0,
            LoginRateLimit.updated_at < cutoff,
        ),
        execution_options={"synchronize_session": False},
    )


def check_login_allowed(db: Session, email: str) -> None:
    """Raise ValueError when the email is temporarily locked out."""
    normalized = normalize_auth_email(email)
    _prune_stale_rows(db)

    row = db.scalar(select(LoginRateLimit).where(LoginRateLimit.email == normalized))
    if not row or not row.locked_until:
        return

    now = datetime.now(UTC)
    locked_until = _ensure_utc(row.locked_until)
    if locked_until > now:
        raise ValueError(_lockout_message(locked_until))

    row.locked_until = None
    row.failed_attempts = 0
    row.updated_at = now
    db.commit()


def record_failed_login(db: Session, email: str) -> None:
    normalized = normalize_auth_email(email)
    now = datetime.now(UTC)

    row = db.scalar(select(LoginRateLimit).where(LoginRateLimit.email == normalized))
    if row is None:
        row = LoginRateLimit(email=normalized, failed_attempts=0)
        db.add(row)

    row.failed_attempts += 1
    row.last_failed_at = now
    row.updated_at = now
    if row.failed_attempts >= settings.login_max_failed_attempts:
        row.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
    db.commit()


def record_successful_login(db: Session, email: str) -> None:
    normalized = normalize_auth_email(email)
    row = db.scalar(select(LoginRateLimit).where(LoginRateLimit.email == normalized))
    if row is None:
        return

    row.failed_attempts = 0
    row.locked_until = None
    row.updated_at = datetime.now(UTC)
    db.commit()
