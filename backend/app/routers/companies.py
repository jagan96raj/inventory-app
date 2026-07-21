"""Spec v17.0.0+ — company endpoints (multi-tenant)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import get_current_user, set_auth_cookie
from app.core.permissions import require_company_owner
from app.core.tenant import company_id_for_user
from app.database import get_db
from app.models.entities import User
from app.routers.auth import _client_meta, _raise_login_rate_limited, user_to_out
from app.schemas import CompanyOut, CompanyRegisterIn, CompanyUpdate, RegistrationStatusOut, UserOut
from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event
from app.services.companies import (
    COMPANY_REGISTRATION_CLOSED,
    EMAIL_ALREADY_REGISTERED,
    get_company_for_user,
    register_company_with_owner,
    update_company_profile,
)
from app.services.login_history import record_login_event
from app.services.login_rate_limit import record_successful_login

# Authenticated company endpoints (mounted under protected_router).
router = APIRouter(prefix="/companies", tags=["companies"])

# Public registration endpoints (mounted on api_router without auth).
public_router = APIRouter(prefix="/companies", tags=["companies"])


@public_router.get("/registration-status", response_model=RegistrationStatusOut)
def registration_status():
    """Public — whether ALLOW_COMPANY_REGISTRATION is enabled (Spec v17.0.4)."""
    return RegistrationStatusOut(allowed=bool(settings.allow_company_registration))


@public_router.post("/register", response_model=UserOut, status_code=201)
def register_company(
    body: CompanyRegisterIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Public company + owner signup. Not subject to ALLOWED_EMAILS (Spec v17.0.4)."""
    if not settings.allow_company_registration:
        raise HTTPException(status_code=403, detail=COMPANY_REGISTRATION_CLOSED)

    email = body.email.strip().lower()
    _raise_login_rate_limited(db, email, request)

    try:
        user = register_company_with_owner(
            db,
            company_name=body.company_name,
            company_address_line=body.company_address_line,
            company_address_line_2=body.company_address_line_2,
            company_district=body.company_district,
            company_state=body.company_state,
            company_pin_code=body.company_pin_code,
            company_gstin=body.company_gstin,
            company_phone=body.company_phone,
            owner_name=body.owner_name,
            email=email,
            password=body.password,
        )
    except ValueError as exc:
        if str(exc) == EMAIL_ALREADY_REGISTERED:
            raise HTTPException(status_code=409, detail=EMAIL_ALREADY_REGISTERED) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)

    record_successful_login(db, email)
    record_login_event(
        db,
        email=email,
        user_id=user.id,
        success=True,
        **_client_meta(request),
    )
    record_audit_event(
        db,
        user=user,
        action=AuditAction.COMPANY_REGISTERED,
        entity_type=AuditEntityType.COMPANY,
        entity_id=user.company_id,
        entity_label=user.company.name if user.company else body.company_name,
        metadata={"owner_email": email},
    )

    set_auth_cookie(response, user.id)
    return user_to_out(user)


@router.get("/me", response_model=CompanyOut)
def get_my_company(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = get_company_for_user(db, user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.patch("/me", response_model=CompanyOut)
def patch_my_company(
    body: CompanyUpdate,
    user: User = Depends(require_company_owner),
    db: Session = Depends(get_db),
):
    """Spec v17.0.5 — owner-only company profile update; syncs book_settings header."""
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        company = get_company_for_user(db, company_id_for_user(user))
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        return company

    try:
        from app.services.companies import _UNSET

        company = update_company_profile(
            db,
            company_id_for_user(user),
            name=payload.get("name"),
            address_line=payload["address_line"] if "address_line" in payload else _UNSET,
            address_line_2=payload["address_line_2"] if "address_line_2" in payload else _UNSET,
            district=payload["district"] if "district" in payload else _UNSET,
            state=payload["state"] if "state" in payload else _UNSET,
            pin_code=payload["pin_code"] if "pin_code" in payload else _UNSET,
            gstin=payload["gstin"] if "gstin" in payload else _UNSET,
            phone=payload["phone"] if "phone" in payload else _UNSET,
        )
    except ValueError as exc:
        if str(exc) == "Company not found":
            raise HTTPException(status_code=404, detail="Company not found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not save company details. Check address fields and try again.",
        ) from exc
    return company
