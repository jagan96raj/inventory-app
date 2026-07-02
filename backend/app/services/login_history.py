"""Spec v16.0.6 — login history service."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.auth import normalize_auth_email
from app.models.entities import LoginEvent

logger = logging.getLogger(__name__)

USER_AGENT_MAX_LEN = 500


class LoginFailureReason:
    INVALID_CREDENTIALS = "invalid_credentials"
    RATE_LIMITED = "rate_limited"
    NOT_ALLOWED = "not_allowed"
    INVALID_OTP = "invalid_otp"


def truncate_user_agent(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    if len(user_agent) <= USER_AGENT_MAX_LEN:
        return user_agent
    return user_agent[:USER_AGENT_MAX_LEN]


def record_login_event(
    db: Session,
    *,
    email: str,
    user_id: int | None = None,
    success: bool,
    failure_reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append a login event row. Never raises — failures are logged only."""
    try:
        row = LoginEvent(
            email=normalize_auth_email(email),
            user_id=user_id,
            success=success,
            failure_reason=None if success else failure_reason,
            ip_address=ip_address,
            user_agent=truncate_user_agent(user_agent),
        )
        db.add(row)
        db.commit()
    except Exception:
        logger.warning(
            "Failed to record login event email=%s success=%s failure_reason=%s",
            email,
            success,
            failure_reason,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass


def login_event_to_out(row: LoginEvent) -> dict:
    return {
        "id": row.id,
        "email": row.email,
        "user_id": row.user_id,
        "success": row.success,
        "failure_reason": row.failure_reason,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "created_at": row.created_at,
    }
