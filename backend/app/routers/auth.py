from datetime import UTC, datetime



from fastapi import APIRouter, Depends, HTTPException, Request, Response

from sqlalchemy import select

from sqlalchemy.orm import Session



from app.core.auth import (

    ACCOUNT_DISABLED_LOGIN,

    INVALID_CREDENTIALS,

    check_email_allowed_for_login,

    check_email_allowed_for_signup,

    clear_auth_cookie,

    get_current_user,

    get_token_from_request,

    hash_password,

    revoke_access_token,

    set_auth_cookie,

    verify_google_id_token,

    verify_password,

)

from app.database import get_db

from app.models.entities import User

from app.schemas import GoogleAuthIn, LoginIn, LoginOtpIn, SignupIn, UserOut

from app.services.companies import get_default_company_id

from app.services.login_history import LoginFailureReason, record_login_event

from app.services.login_otp import INVALID_OTP, login_with_otp

from app.services.login_rate_limit import (

    check_login_allowed,

    record_failed_login,

    record_successful_login,

)



router = APIRouter(tags=["auth"])





def _client_meta(request: Request) -> dict[str, str | None]:

    ip_address = request.client.host if request.client else None

    return {"ip_address": ip_address, "user_agent": request.headers.get("user-agent")}





def _reject_if_disabled(user: User | None) -> None:

    if user is not None and not user.is_active:

        raise HTTPException(status_code=403, detail=ACCOUNT_DISABLED_LOGIN)





def _raise_login_rate_limited(db: Session, email: str, request: Request) -> None:

    try:

        check_login_allowed(db, email)

    except ValueError as exc:

        record_login_event(

            db,

            email=email,

            success=False,

            failure_reason=LoginFailureReason.RATE_LIMITED,

            **_client_meta(request),

        )

        raise HTTPException(status_code=429, detail=str(exc)) from exc





def _guard_signup_email(email: str, db: Session, request: Request) -> None:

    try:

        check_email_allowed_for_signup(email)

    except HTTPException as exc:

        if exc.status_code == 403:

            record_login_event(

                db,

                email=email,

                success=False,

                failure_reason=LoginFailureReason.NOT_ALLOWED,

                **_client_meta(request),

            )

        raise





def _guard_login_email(email: str, db: Session, request: Request) -> None:

    try:

        check_email_allowed_for_login(email, db)

    except HTTPException as exc:

        if exc.status_code == 403:

            record_login_event(

                db,

                email=email,

                success=False,

                failure_reason=LoginFailureReason.NOT_ALLOWED,

                **_client_meta(request),

            )

        raise





def user_to_out(user: User) -> UserOut:

    return UserOut(

        id=user.id,

        email=user.email,

        name=user.name,

        picture_url=user.picture_url,

        role=user.role.value if user.role else None,

        company_id=user.company_id,

        company_name=user.company.name if user.company else None,

    )





@router.post("/signup", response_model=UserOut, status_code=201)

def signup(

    body: SignupIn,

    request: Request,

    response: Response,

    db: Session = Depends(get_db),

):

    email = body.email.strip().lower()

    _raise_login_rate_limited(db, email, request)

    _guard_signup_email(email, db, request)



    existing = db.scalar(select(User).where(User.email == email))

    if existing:

        raise HTTPException(status_code=409, detail="Email already registered")



    now = datetime.now(UTC)

    default_company_id = get_default_company_id(db)

    user = User(

        email=email,

        password_hash=hash_password(body.password),

        name=body.name.strip() if body.name else None,

        company_id=default_company_id,

        last_login_at=now,

    )

    db.add(user)

    db.commit()

    db.refresh(user)



    record_login_event(

        db,

        email=email,

        user_id=user.id,

        success=True,

        **_client_meta(request),

    )

    set_auth_cookie(response, user.id)

    return user_to_out(user)





@router.post("/login", response_model=UserOut)

def login(

    body: LoginIn,

    request: Request,

    response: Response,

    db: Session = Depends(get_db),

):

    email = body.email.strip().lower()

    _raise_login_rate_limited(db, email, request)

    _guard_login_email(email, db, request)



    user = db.scalar(select(User).where(User.email == email))

    _reject_if_disabled(user)

    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):

        record_failed_login(db, email)

        record_login_event(

            db,

            email=email,

            user_id=user.id if user else None,

            success=False,

            failure_reason=LoginFailureReason.INVALID_CREDENTIALS,

            **_client_meta(request),

        )

        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)



    record_successful_login(db, email)



    user.last_login_at = datetime.now(UTC)

    db.commit()

    db.refresh(user)



    record_login_event(

        db,

        email=email,

        user_id=user.id,

        success=True,

        **_client_meta(request),

    )

    set_auth_cookie(response, user.id)

    return user_to_out(user)





@router.post("/otp-login", response_model=UserOut)

def otp_login(

    body: LoginOtpIn,

    request: Request,

    response: Response,

    db: Session = Depends(get_db),

):

    email = body.email.strip().lower()

    _guard_login_email(email, db, request)



    user = db.scalar(select(User).where(User.email == email))

    if not user:

        record_login_event(

            db,

            email=email,

            success=False,

            failure_reason=LoginFailureReason.INVALID_OTP,

            **_client_meta(request),

        )

        raise HTTPException(status_code=401, detail=INVALID_OTP)

    _reject_if_disabled(user)

    try:

        user = login_with_otp(db, user=user, code=body.otp, new_password=body.new_password)

    except ValueError as e:

        record_login_event(

            db,

            email=email,

            user_id=user.id,

            success=False,

            failure_reason=LoginFailureReason.INVALID_OTP,

            **_client_meta(request),

        )

        raise HTTPException(status_code=401, detail=str(e)) from e



    record_login_event(

        db,

        email=email,

        user_id=user.id,

        success=True,

        **_client_meta(request),

    )

    set_auth_cookie(response, user.id)

    return user_to_out(user)





@router.post("/google", response_model=UserOut)

def google_login(

    body: GoogleAuthIn,

    response: Response,

    db: Session = Depends(get_db),

):

    try:

        info = verify_google_id_token(body.id_token)

    except (ValueError, Exception):

        raise HTTPException(status_code=400, detail="Invalid Google token") from None



    email = str(info["email"]).lower()

    now = datetime.now(UTC)

    user = db.scalar(select(User).where(User.google_sub == info["sub"]))

    if user:

        check_email_allowed_for_login(email, db)

        _reject_if_disabled(user)

        user.email = email

        user.name = info.get("name") or user.name

        user.picture_url = info.get("picture") or user.picture_url

        user.last_login_at = now

    else:

        check_email_allowed_for_signup(email)

        default_company_id = get_default_company_id(db)

        user = User(

            google_sub=str(info["sub"]),

            email=email,

            name=info.get("name"),

            picture_url=info.get("picture"),

            company_id=default_company_id,

            last_login_at=now,

        )

        db.add(user)

    db.commit()

    db.refresh(user)



    set_auth_cookie(response, user.id)

    return user_to_out(user)





@router.post("/logout")

def logout(request: Request, response: Response, db: Session = Depends(get_db)):

    token = get_token_from_request(request)

    if token:

        revoke_access_token(db, token)

    clear_auth_cookie(response)

    return {"ok": True}





@router.get("/me", response_model=UserOut)

def me(user: User = Depends(get_current_user)):

    return user_to_out(user)

