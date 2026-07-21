"""Spec v17.0.0+ — company helpers (multi-tenant)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import hash_password
from app.models.entities import (
    BillNumberCounter,
    BillType,
    BookSettings,
    Company,
    JWNumberCounter,
    User,
    UserRole,
)
from app.utils.time import business_today

DEFAULT_COMPANY_ID = 1

EMAIL_ALREADY_REGISTERED = "Email already registered"
COMPANY_REGISTRATION_CLOSED = "Company registration is closed"

_UNSET = object()


def get_default_company_id(db: Session) -> int:
    company = db.get(Company, DEFAULT_COMPANY_ID)
    if company is None:
        raise ValueError("Default company not configured")
    return company.id


def get_company_for_user(db: Session, company_id: int) -> Company | None:
    return db.get(Company, company_id)


def format_company_address(company: Company) -> str | None:
    """Single-line address join (legacy helpers / tests)."""
    parts = [
        company.address_line,
        company.address_line_2,
        company.district,
        company.state,
        company.pin_code,
    ]
    joined = ", ".join(p.strip().rstrip(",") for p in parts if p and str(p).strip())
    return joined or None


def update_company_profile(
    db: Session,
    company_id: int,
    *,
    name: str | None = None,
    address_line: Any = _UNSET,
    address_line_2: Any = _UNSET,
    district: Any = _UNSET,
    state: Any = _UNSET,
    pin_code: Any = _UNSET,
    gstin: Any = _UNSET,
    phone: Any = _UNSET,
) -> Company:
    """Update companies row (bill-print header reads companies only)."""
    company = db.get(Company, company_id)
    if company is None:
        raise ValueError("Company not found")

    if name is not None:
        company.name = name
    if address_line is not _UNSET:
        company.address_line = address_line
    if address_line_2 is not _UNSET:
        company.address_line_2 = address_line_2
    if district is not _UNSET:
        company.district = district
    if state is not _UNSET:
        company.state = state
    if pin_code is not _UNSET:
        company.pin_code = pin_code
    if gstin is not _UNSET:
        company.gstin = gstin
    if phone is not _UNSET:
        company.phone = phone

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(company)
    return company


def _seed_tenant_defaults(
    db: Session,
    *,
    company: Company,
) -> None:
    """Book settings + bill/JW counters for a new company (no mid-transaction commit)."""
    db.add(
        BookSettings(
            company_id=company.id,
            cash_opening_balance=Decimal("0"),
            cash_opening_balance_at=business_today(),
        )
    )
    db.add(BillNumberCounter(company_id=company.id, bill_type=BillType.sales, last_number=0))
    db.add(BillNumberCounter(company_id=company.id, bill_type=BillType.purchase, last_number=0))
    db.add(JWNumberCounter(company_id=company.id, last_number=0))
    db.flush()


def register_company_with_owner(
    db: Session,
    *,
    company_name: str,
    company_address_line: str | None,
    company_address_line_2: str | None = None,
    company_district: str | None = None,
    company_state: str | None = None,
    company_pin_code: str | None = None,
    company_gstin: str | None = None,
    company_phone: str | None,
    owner_name: str | None,
    email: str,
    password: str,
) -> User:
    """
    Spec v17.0.4 / v17.0.6 — atomically create company + owner + settings/counters.

    Caller must enforce ALLOW_COMPANY_REGISTRATION and rate limits.
    Raises ValueError with EMAIL_ALREADY_REGISTERED on duplicate email.
    """
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise ValueError(EMAIL_ALREADY_REGISTERED)

    company = Company(
        name=company_name,
        address_line=company_address_line,
        address_line_2=company_address_line_2,
        district=company_district,
        state=company_state,
        pin_code=company_pin_code,
        gstin=company_gstin,
        phone=company_phone,
        is_active=True,
    )
    db.add(company)
    db.flush()

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=owner_name,
        company_id=company.id,
        role=UserRole.owner,
        is_active=True,
    )
    db.add(user)
    db.flush()

    _seed_tenant_defaults(db, company=company)
    db.commit()
    db.refresh(user)
    if user.company is None:
        db.refresh(user, attribute_names=["company"])
    return user
