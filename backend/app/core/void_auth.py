"""Authorization gate for void (destructive) operations."""

import secrets

from fastapi import HTTPException

from app.config import settings
from app.core.auth import verify_password
from app.models.entities import User

VOID_AUTH_HEADER = "X-Void-Authorization"
VOID_AUTH_REQUIRED_MSG = "Authorization password required to void"
VOID_AUTH_INVALID_MSG = "Invalid authorization password"


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
