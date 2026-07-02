import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import User
from app.services.users import set_user_password

OTP_LENGTH = 6
INVALID_OTP = "Invalid or expired login code"


def _hash_otp(code: str) -> str:
    return hmac.new(settings.jwt_secret.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def generate_login_otp(db: Session, user: User) -> tuple[str, datetime]:
    code = _generate_code()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.login_otp_expire_minutes)
    user.login_otp_hash = _hash_otp(code)
    user.login_otp_expires_at = expires_at
    user.login_otp_created_at = now
    db.commit()
    db.refresh(user)
    return code, expires_at


def clear_login_otp(user: User) -> None:
    user.login_otp_hash = None
    user.login_otp_expires_at = None
    user.login_otp_created_at = None


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def verify_login_otp(user: User, code: str) -> bool:
    if not user.login_otp_hash or not user.login_otp_expires_at:
        return False
    if datetime.now(UTC) > _as_utc(user.login_otp_expires_at):
        return False
    normalized = code.strip()
    if len(normalized) != OTP_LENGTH or not normalized.isdigit():
        return False
    return hmac.compare_digest(user.login_otp_hash, _hash_otp(normalized))


def login_with_otp(
    db: Session,
    *,
    user: User,
    code: str,
    new_password: str | None = None,
) -> User:
    if not verify_login_otp(user, code):
        raise ValueError(INVALID_OTP)
    if new_password is not None:
        set_user_password(user, new_password)
    clear_login_otp(user)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user
