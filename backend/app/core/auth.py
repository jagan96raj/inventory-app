import bcrypt

from dataclasses import dataclass

from datetime import UTC, datetime, timedelta

from uuid import uuid4



import jwt

from fastapi import Depends, HTTPException, Request, Response

from google.auth.transport import requests as google_requests

from google.oauth2 import id_token

from sqlalchemy import func, select

from sqlalchemy.orm import Session



from app.config import settings

from app.database import get_db

from app.models.entities import User

from app.services.token_revocation import is_token_revoked, revoke_token



COOKIE_NAME = "access_token"

NOT_AUTHENTICATED = "Not authenticated"

INVALID_CREDENTIALS = "Invalid email or password"

ACCOUNT_DISABLED = "Account disabled. Contact the owner."

ACCOUNT_DISABLED_LOGIN = "This account has been disabled. Contact the owner."

EMAIL_NOT_AUTHORIZED = "Email not authorized"





@dataclass(frozen=True)

class AccessTokenClaims:

    user_id: int

    jti: str

    expires_at: datetime





def hash_password(password: str) -> str:

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")





def verify_password(password: str, password_hash: str) -> bool:

    try:

        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    except (ValueError, TypeError):

        return False





def set_auth_cookie(response: Response, user_id: int) -> None:

    token = create_access_token(user_id)

    response.set_cookie(

        key=COOKIE_NAME,

        value=token,

        httponly=True,

        samesite="lax",

        secure=settings.cookie_secure,

        max_age=settings.jwt_expire_hours * 3600,

        path="/",

    )





def clear_auth_cookie(response: Response) -> None:

    response.delete_cookie(key=COOKIE_NAME, path="/", samesite="lax")





def verify_google_id_token(token: str) -> dict[str, str | None]:

    if not settings.google_client_id:

        raise ValueError("GOOGLE_CLIENT_ID is not configured")

    idinfo = id_token.verify_oauth2_token(

        token,

        google_requests.Request(),

        settings.google_client_id,

    )

    if idinfo.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):

        raise ValueError("Invalid token issuer")

    email = idinfo.get("email")

    sub = idinfo.get("sub")

    if not email or not sub:

        raise ValueError("Token missing email or sub")

    return {

        "sub": sub,

        "email": email,

        "name": idinfo.get("name"),

        "picture": idinfo.get("picture"),

    }





def create_access_token(user_id: int) -> str:

    jti = str(uuid4())

    expire = datetime.now(UTC) + timedelta(hours=settings.jwt_expire_hours)

    payload = {"sub": str(user_id), "exp": expire, "jti": jti}

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)





def _expires_at_from_payload(payload: dict) -> datetime:

    exp = payload["exp"]

    if isinstance(exp, datetime):

        return exp if exp.tzinfo else exp.replace(tzinfo=UTC)

    return datetime.fromtimestamp(int(exp), tz=UTC)





def parse_access_token(token: str) -> AccessTokenClaims:

    """Decode JWT signature and expiry only (no revocation check)."""

    try:

        payload = jwt.decode(

            token,

            settings.jwt_secret,

            algorithms=[settings.jwt_algorithm],

        )

        jti = payload.get("jti")

        if not jti:

            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED)

        return AccessTokenClaims(

            user_id=int(payload["sub"]),

            jti=str(jti),

            expires_at=_expires_at_from_payload(payload),

        )

    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:

        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED) from exc





def decode_access_token(token: str, db: Session) -> int:

    claims = parse_access_token(token)

    if is_token_revoked(db, claims.jti):

        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED)

    return claims.user_id





def revoke_access_token(db: Session, token: str) -> None:

    try:

        claims = parse_access_token(token)

    except HTTPException:

        return

    revoke_token(

        db,

        jti=claims.jti,

        expires_at=claims.expires_at,

        user_id=claims.user_id,

    )





def normalize_auth_email(email: str) -> str:

    return email.strip().lower()





def get_allowed_emails() -> set[str] | None:

    raw = settings.allowed_emails.strip()

    if not raw:

        return None

    emails = {normalize_auth_email(part) for part in raw.split(",") if part.strip()}

    return emails or None





def is_email_allowlist_active() -> bool:

    return get_allowed_emails() is not None





def _registered_user_exists(db: Session, normalized_email: str) -> bool:

    return (

        db.scalar(select(User.id).where(func.lower(User.email) == normalized_email)) is not None

    )





def check_email_allowed_for_signup(email: str) -> None:

    """Self-service signup — must be on ALLOWED_EMAILS when allowlist is active."""

    normalized = normalize_auth_email(email)

    if not normalized or "@" not in normalized:

        raise HTTPException(status_code=403, detail=EMAIL_NOT_AUTHORIZED)

    allowed = get_allowed_emails()

    if allowed is not None and normalized not in allowed:

        raise HTTPException(status_code=403, detail=EMAIL_NOT_AUTHORIZED)





def check_email_allowed_for_login(email: str, db: Session) -> None:

    """Login — allowlist OR an account the owner already created in Users."""

    normalized = normalize_auth_email(email)

    if not normalized or "@" not in normalized:

        raise HTTPException(status_code=403, detail=EMAIL_NOT_AUTHORIZED)

    allowed = get_allowed_emails()

    if allowed is None:

        return

    if normalized in allowed:

        return

    if _registered_user_exists(db, normalized):

        return

    raise HTTPException(status_code=403, detail=EMAIL_NOT_AUTHORIZED)





def check_email_allowed(email: str) -> None:

    """Backward-compatible alias for signup-only checks (no database)."""

    check_email_allowed_for_signup(email)





def validate_auth_email_policy() -> None:

    """Log dev warning or refuse startup when production email policy is misconfigured."""

    import logging



    logger = logging.getLogger(__name__)

    allowed = get_allowed_emails()

    if settings.require_allowed_emails and allowed is None:

        raise RuntimeError(

            "REQUIRE_ALLOWED_EMAILS=true but ALLOWED_EMAILS is empty. "

            "Set a comma-separated allowlist in .env before starting the backend."

        )

    if allowed is None:

        logger.warning(

            "ALLOWED_EMAILS is not set — any email can sign up and log in (development only). "

            "Set ALLOWED_EMAILS in .env for production signup lockdown (Spec v15.1)."

        )

    else:

        logger.info("Signup lockdown active — %d allowlisted email(s).", len(allowed))





def get_token_from_request(request: Request) -> str | None:

    token = request.cookies.get(COOKIE_NAME)

    if token:

        return token

    auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.lower().startswith("bearer "):

        return auth_header[7:].strip()

    return None





def get_current_user(

    request: Request,

    db: Session = Depends(get_db),

) -> User:

    token = get_token_from_request(request)

    if not token:

        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED)

    user_id = decode_access_token(token, db)

    user = db.get(User, user_id)

    if not user:

        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED)

    if not user.is_active:

        raise HTTPException(status_code=401, detail=ACCOUNT_DISABLED)

    return user

