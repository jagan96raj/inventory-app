"""Spec v12.21 / v17.2.0 — bank account master CRUD with default + delete protection."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.entities import BankAccount, BankAccountKind, CashBookEntry, Payment, PaymentMode
from app.utils.time import business_today


BANK_NAME_REQUIRED_MSG = "Bank account name is required"
BANK_NAME_DUPLICATE_MSG = "Bank account name already exists"
BANK_NOT_FOUND_MSG = "Bank account not found"
BANK_IN_USE_MSG = "Bank account is in use and cannot be deleted"
CASH_ACCOUNT_NAME = "Cash"


def _normalize_name(name: str) -> str:
    return (name or "").strip()


def _name_exists(db: Session, name: str, company_id: int, exclude_id: int | None = None) -> bool:
    q = select(BankAccount.id).where(
        BankAccount.company_id == company_id,
        func.lower(func.trim(BankAccount.name)) == name.lower(),
    )
    if exclude_id is not None:
        q = q.where(BankAccount.id != exclude_id)
    return db.scalar(q) is not None


def _clear_other_defaults(db: Session, keep_id: int | None, *, company_id: int) -> None:
    stmt = (
        update(BankAccount)
        .where(
            BankAccount.is_default.is_(True),
            BankAccount.company_id == company_id,
            BankAccount.kind == BankAccountKind.bank,
        )
        .values(is_default=False)
    )
    if keep_id is not None:
        stmt = stmt.where(BankAccount.id != keep_id)
    db.execute(stmt)


def seed_company_cash_account(
    db: Session,
    company_id: int,
    *,
    opening_balance: Decimal | None = None,
    opening_balance_at: date | None = None,
) -> BankAccount:
    """Idempotent Cash row for a company (kind=cash, never default). No mid-transaction commit."""
    existing = db.scalar(
        select(BankAccount).where(
            BankAccount.company_id == company_id,
            BankAccount.kind == BankAccountKind.cash,
        )
    )
    if existing:
        return existing

    named = db.scalar(
        select(BankAccount).where(
            BankAccount.company_id == company_id,
            func.lower(func.trim(BankAccount.name)) == CASH_ACCOUNT_NAME.lower(),
        )
    )
    if named:
        if named.is_default:
            other = db.scalar(
                select(BankAccount)
                .where(
                    BankAccount.company_id == company_id,
                    BankAccount.kind == BankAccountKind.bank,
                    BankAccount.is_active.is_(True),
                    BankAccount.id != named.id,
                )
                .order_by(BankAccount.id)
                .limit(1)
            )
            named.is_default = False
            if other:
                other.is_default = True
        named.kind = BankAccountKind.cash
        if opening_balance is not None:
            named.opening_balance = opening_balance
        if opening_balance_at is not None:
            named.opening_balance_at = opening_balance_at
        db.flush()
        return named

    record = BankAccount(
        company_id=company_id,
        name=CASH_ACCOUNT_NAME,
        kind=BankAccountKind.cash,
        account_number_last4=None,
        ifsc=None,
        opening_balance=opening_balance if opening_balance is not None else Decimal("0"),
        opening_balance_at=opening_balance_at if opening_balance_at is not None else business_today(),
        is_default=False,
        is_active=True,
    )
    db.add(record)
    db.flush()
    return record


def list_bank_accounts(
    db: Session, *, company_id: int | None = None, active: str = "true"
) -> list[BankAccount]:
    # Phase 1: only expose kind=bank so Cash stays out of bank master/pickers.
    q = (
        select(BankAccount)
        .where(BankAccount.kind == BankAccountKind.bank)
        .order_by(BankAccount.is_default.desc(), BankAccount.name)
    )
    if company_id is not None:
        q = q.where(BankAccount.company_id == company_id)
    if active == "true":
        q = q.where(BankAccount.is_active.is_(True))
    elif active == "false":
        q = q.where(BankAccount.is_active.is_(False))
    return list(db.scalars(q).all())


def get_default_bank_account(db: Session, *, company_id: int) -> BankAccount | None:
    return db.scalar(
        select(BankAccount)
        .where(
            BankAccount.is_default.is_(True),
            BankAccount.company_id == company_id,
            BankAccount.kind == BankAccountKind.bank,
        )
        .limit(1)
    )


def create_bank_account(
    db: Session,
    *,
    company_id: int = 1,
    name: str,
    account_number_last4: str | None,
    ifsc: str | None,
    opening_balance: Decimal,
    is_default: bool,
) -> BankAccount:
    name = _normalize_name(name)
    if not name:
        raise ValueError(BANK_NAME_REQUIRED_MSG)
    if _name_exists(db, name, company_id):
        raise ValueError(BANK_NAME_DUPLICATE_MSG)
    # Auto-default only when no bank-kind accounts exist yet (Cash does not count).
    any_bank = db.scalar(
        select(func.count(BankAccount.id)).where(
            BankAccount.company_id == company_id,
            BankAccount.kind == BankAccountKind.bank,
        )
    ) or 0
    if any_bank == 0:
        is_default = True
    if is_default:
        _clear_other_defaults(db, keep_id=None, company_id=company_id)
    record = BankAccount(
        company_id=company_id,
        name=name,
        kind=BankAccountKind.bank,
        account_number_last4=account_number_last4,
        ifsc=ifsc,
        opening_balance=opening_balance or Decimal("0"),
        opening_balance_at=business_today(),
        is_default=is_default,
        is_active=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def edit_bank_account(
    db: Session,
    bank_id: int,
    *,
    company_id: int | None = None,
    name: str | None,
    account_number_last4: str | None,
    ifsc: str | None,
    is_active: bool | None,
) -> BankAccount:
    record = db.get(BankAccount, bank_id)
    if not record or record.kind != BankAccountKind.bank:
        raise ValueError(BANK_NOT_FOUND_MSG)
    if company_id is not None and int(record.company_id) != int(company_id):
        raise ValueError(BANK_NOT_FOUND_MSG)
    if name is not None:
        clean = _normalize_name(name)
        if not clean:
            raise ValueError(BANK_NAME_REQUIRED_MSG)
        if _name_exists(db, clean, record.company_id, exclude_id=bank_id):
            raise ValueError(BANK_NAME_DUPLICATE_MSG)
        record.name = clean
    if account_number_last4 is not None:
        record.account_number_last4 = account_number_last4 or None
    if ifsc is not None:
        record.ifsc = ifsc or None
    if is_active is not None:
        if not is_active and record.is_default:
            raise ValueError("Cannot deactivate the default bank account")
        record.is_active = is_active
    db.commit()
    db.refresh(record)
    return record


def make_default_bank_account(
    db: Session, bank_id: int, *, company_id: int | None = None
) -> BankAccount:
    record = db.get(BankAccount, bank_id)
    if not record or record.kind != BankAccountKind.bank:
        raise ValueError(BANK_NOT_FOUND_MSG)
    if company_id is not None and int(record.company_id) != int(company_id):
        raise ValueError(BANK_NOT_FOUND_MSG)
    if not record.is_active:
        raise ValueError("Cannot make an inactive bank account the default")
    _clear_other_defaults(db, keep_id=bank_id, company_id=record.company_id)
    record.is_default = True
    db.commit()
    db.refresh(record)
    return record


def assert_bank_account_deletable(db: Session, bank_id: int) -> None:
    payment_used = db.scalar(
        select(func.count(Payment.id)).where(Payment.bank_account_id == bank_id)
    ) or 0
    cb_used = db.scalar(
        select(func.count(CashBookEntry.id)).where(
            (CashBookEntry.source_bank_account_id == bank_id)
            | (CashBookEntry.dest_bank_account_id == bank_id)
        )
    ) or 0
    if payment_used or cb_used:
        raise ValueError(
            f"Bank account in use: {payment_used} payment(s), {cb_used} cash book entry(ies)"
        )


def delete_bank_account(db: Session, bank_id: int, *, company_id: int | None = None) -> None:
    record = db.get(BankAccount, bank_id)
    if not record or record.kind != BankAccountKind.bank:
        raise ValueError(BANK_NOT_FOUND_MSG)
    if company_id is not None and int(record.company_id) != int(company_id):
        raise ValueError(BANK_NOT_FOUND_MSG)
    assert_bank_account_deletable(db, bank_id)
    if record.is_default:
        raise ValueError("Cannot delete the default bank account; promote another bank first")
    # soft delete: deactivate
    record.is_active = False
    db.commit()
