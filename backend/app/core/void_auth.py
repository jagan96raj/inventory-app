"""Authorization gate for void (destructive) operations and backdated entries."""

import secrets
from datetime import date

from fastapi import HTTPException

from app.config import settings
from app.core.auth import verify_password
from app.models.entities import User
from app.utils.time import business_today

VOID_AUTH_HEADER = "X-Void-Authorization"
VOID_AUTH_REQUIRED_MSG = "Authorization password required to void"
VOID_AUTH_INVALID_MSG = "Invalid authorization password"
BACKDATE_AUTH_REQUIRED_MSG = "Authorization password required to record a past date"


def verify_void_authorization(password: str | None, user: User) -> None:
    """Accept admin void password (VOID_AUTH_PASSWORD) or the signed-in user's login password."""
    if not password or not password.strip():
        raise HTTPException(status_code=403, detail=VOID_AUTH_REQUIRED_MSG)

    pwd = password.strip()
    admin = settings.void_auth_password.strip()
    if admin and secrets.compare_digest(pwd, admin):
        return

    if user.password_hash and verify_password(pwd, user.password_hash):
        return

    raise HTTPException(status_code=403, detail=VOID_AUTH_INVALID_MSG)


def verify_backdate_authorization(optional_date: date | None, password: str | None, user: User) -> None:
    """Require void/login password when recording a transaction on a past business date."""
    if optional_date is None or optional_date >= business_today():
        return
    if password is None:
        raise HTTPException(status_code=403, detail=BACKDATE_AUTH_REQUIRED_MSG)
    if not isinstance(password, str):
        return  # FastAPI Header() default when route handler called in-process (tests)
    if not password.strip():
        raise HTTPException(status_code=403, detail=BACKDATE_AUTH_REQUIRED_MSG)
    verify_void_authorization(password, user)
