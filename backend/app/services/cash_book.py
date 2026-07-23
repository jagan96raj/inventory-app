"""Spec v12.21 — cash book entry service (create/edit/void)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    BankAccount,
    BankAccountKind,
    Bill,
    CashBookEntry,
    CashBookEntryType,
    CashBookSourceMode,
    ExpenseCategory,
    ExpenseCategoryKind,
    User,
)
from app.core.tenant import assert_entity_company
from app.services.bank_accounts import resolve_money_account_id
from app.utils.time import resolve_business_entry, utc_now


CASH_BOOK_NOT_FOUND_MSG = "Cash book entry not found"
CASH_BOOK_ALREADY_VOIDED_MSG = "Cash book entry already voided"
CASH_BOOK_STALE_MSG = "Cash book entry was updated by another user. Refresh and try again."
CASH_BOOK_EXPECTED_VERSION_REQUIRED_MSG = "expected_version required"
CASH_BOOK_CATEGORY_KIND_MISMATCH_MSG = "Category kind does not match entry type"


def _kind_for_entry_type(entry_type: CashBookEntryType) -> ExpenseCategoryKind:
    if entry_type == CashBookEntryType.expense:
        return ExpenseCategoryKind.expense
    if entry_type == CashBookEntryType.income:
        return ExpenseCategoryKind.income
    return ExpenseCategoryKind.transfer


def _validate_category(db: Session, category_id: int, entry_type: CashBookEntryType, company_id: int) -> ExpenseCategory:
    category = db.get(ExpenseCategory, category_id)
    if not category or not category.is_active:
        raise ValueError("Category not found or inactive")
    assert_entity_company(category, company_id, "Category")
    expected = _kind_for_entry_type(entry_type)
    if category.kind != expected:
        raise ValueError(CASH_BOOK_CATEGORY_KIND_MISMATCH_MSG)
    return category


def _validate_bank_refs(
    db: Session,
    *,
    company_id: int,
    source_mode: CashBookSourceMode | None,
    source_bank_id: int | None,
    dest_mode: CashBookSourceMode | None,
    dest_bank_id: int | None,
) -> None:
    for bank_id, side in ((source_bank_id, "source"), (dest_bank_id, "destination")):
        if bank_id is None:
            continue
        bank = db.get(BankAccount, bank_id)
        if not bank or not bank.is_active:
            raise ValueError(f"{side.capitalize()} bank account not found or inactive")
        assert_entity_company(bank, company_id, f"{side.capitalize()} bank account")
        if bank.kind != BankAccountKind.bank:
            raise ValueError(f"{side.capitalize()} bank account not found or inactive")
    # consistency checks already performed in pydantic; recheck cheap rules
    if source_mode == CashBookSourceMode.cash and source_bank_id is not None:
        raise ValueError("source bank id must be null when source is cash")
    if dest_mode == CashBookSourceMode.cash and dest_bank_id is not None:
        raise ValueError("destination bank id must be null when destination is cash")


def _validate_bill(db: Session, bill_id: int | None, company_id: int) -> Bill | None:
    if bill_id is None:
        return None
    bill = db.get(Bill, bill_id)
    if not bill:
        raise ValueError("Linked bill not found")
    assert_entity_company(bill, company_id, "Bill")
    return bill


def _normalize_payload(
    entry_type: CashBookEntryType,
    *,
    source_mode: CashBookSourceMode | None,
    source_bank_id: int | None,
    dest_mode: CashBookSourceMode | None,
    dest_bank_id: int | None,
) -> tuple[CashBookSourceMode | None, int | None, CashBookSourceMode | None, int | None]:
    if entry_type in (CashBookEntryType.expense, CashBookEntryType.income):
        return source_mode, source_bank_id, None, None
    return source_mode, source_bank_id, dest_mode, dest_bank_id


def create_cash_book_entry(
    db: Session,
    *,
    company_id: int = 1,
    entry_type: CashBookEntryType,
    category_id: int,
    amount: Decimal,
    description: str | None,
    reference_no: str | None,
    bill_id: int | None,
    source_payment_mode: CashBookSourceMode | None,
    source_bank_account_id: int | None,
    dest_payment_mode: CashBookSourceMode | None,
    dest_bank_account_id: int | None,
    entry_date: date | None = None,
) -> CashBookEntry:
    _validate_category(db, category_id, entry_type, company_id)
    src_mode, src_bank, dst_mode, dst_bank = _normalize_payload(
        entry_type,
        source_mode=source_payment_mode,
        source_bank_id=source_bank_account_id,
        dest_mode=dest_payment_mode,
        dest_bank_id=dest_bank_account_id,
    )
    _validate_bank_refs(
        db,
        company_id=company_id,
        source_mode=src_mode,
        source_bank_id=src_bank,
        dest_mode=dst_mode,
        dest_bank_id=dst_bank,
    )
    _validate_bill(db, bill_id, company_id)
    resolved_date, entry_at = resolve_business_entry(entry_date)
    source_account_id = resolve_money_account_id(
        db, company_id, mode=src_mode, bank_account_id=src_bank
    )
    dest_account_id = resolve_money_account_id(
        db, company_id, mode=dst_mode, bank_account_id=dst_bank
    )
    entry = CashBookEntry(
        company_id=company_id,
        entry_type=entry_type,
        category_id=category_id,
        amount=amount,
        description=description,
        reference_no=reference_no,
        bill_id=bill_id,
        source_payment_mode=src_mode,
        source_bank_account_id=src_bank,
        dest_payment_mode=dst_mode,
        dest_bank_account_id=dst_bank,
        source_account_id=source_account_id,
        dest_account_id=dest_account_id,
        entry_date=resolved_date,
        entry_at=entry_at,
        version=1,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def edit_cash_book_entry(
    db: Session,
    entry_id: int,
    *,
    company_id: int | None = None,
    expected_version: int | None,
    entry_type: CashBookEntryType,
    category_id: int,
    amount: Decimal,
    description: str | None,
    reference_no: str | None,
    bill_id: int | None,
    source_payment_mode: CashBookSourceMode | None,
    source_bank_account_id: int | None,
    dest_payment_mode: CashBookSourceMode | None,
    dest_bank_account_id: int | None,
) -> CashBookEntry:
    entry = db.get(CashBookEntry, entry_id)
    if not entry:
        raise ValueError(CASH_BOOK_NOT_FOUND_MSG)
    if company_id is not None and int(entry.company_id) != int(company_id):
        raise ValueError(CASH_BOOK_NOT_FOUND_MSG)
    if entry.voided_at is not None:
        raise ValueError(CASH_BOOK_ALREADY_VOIDED_MSG)
    if expected_version is None:
        raise ValueError(CASH_BOOK_EXPECTED_VERSION_REQUIRED_MSG)
    if expected_version != entry.version:
        raise ValueError(CASH_BOOK_STALE_MSG)
    _validate_category(db, category_id, entry_type, entry.company_id)
    src_mode, src_bank, dst_mode, dst_bank = _normalize_payload(
        entry_type,
        source_mode=source_payment_mode,
        source_bank_id=source_bank_account_id,
        dest_mode=dest_payment_mode,
        dest_bank_id=dest_bank_account_id,
    )
    _validate_bank_refs(
        db,
        company_id=entry.company_id,
        source_mode=src_mode,
        source_bank_id=src_bank,
        dest_mode=dst_mode,
        dest_bank_id=dst_bank,
    )
    _validate_bill(db, bill_id, entry.company_id)

    entry.entry_type = entry_type
    entry.category_id = category_id
    entry.amount = amount
    entry.description = description
    entry.reference_no = reference_no
    entry.bill_id = bill_id
    entry.source_payment_mode = src_mode
    entry.source_bank_account_id = src_bank
    entry.dest_payment_mode = dst_mode
    entry.dest_bank_account_id = dst_bank
    entry.source_account_id = resolve_money_account_id(
        db, entry.company_id, mode=src_mode, bank_account_id=src_bank
    )
    entry.dest_account_id = resolve_money_account_id(
        db, entry.company_id, mode=dst_mode, bank_account_id=dst_bank
    )
    entry.version = entry.version + 1
    db.commit()
    db.refresh(entry)
    return entry


def void_cash_book_entry(
    db: Session,
    entry_id: int,
    *,
    expected_version: int | None,
    actor: User | None = None,
    company_id: int | None = None,
) -> CashBookEntry:
    entry = db.get(CashBookEntry, entry_id)
    if not entry:
        raise ValueError(CASH_BOOK_NOT_FOUND_MSG)
    if company_id is not None and int(entry.company_id) != int(company_id):
        raise ValueError(CASH_BOOK_NOT_FOUND_MSG)
    if entry.voided_at is not None:
        raise ValueError(CASH_BOOK_ALREADY_VOIDED_MSG)
    if expected_version is None:
        raise ValueError(CASH_BOOK_EXPECTED_VERSION_REQUIRED_MSG)
    if expected_version != entry.version:
        raise ValueError(CASH_BOOK_STALE_MSG)
    entry.voided_at = utc_now()
    entry.version = entry.version + 1
    db.commit()
    db.refresh(entry)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        label = entry.description or f"Cash book entry #{entry.id}"
        record_audit_event(
            db,
            user=actor,
            action=AuditAction.CASH_BOOK_VOIDED,
            entity_type=AuditEntityType.CASH_BOOK_ENTRY,
            entity_id=entry.id,
            entity_label=label[:255],
            metadata={"amount": str(entry.amount), "bill_id": entry.bill_id},
        )
    return entry


def list_cash_book(
    db: Session,
    *,
    company_id: int | None = None,
    entry_type: CashBookEntryType | None = None,
    category_id: int | None = None,
    source_payment_mode: CashBookSourceMode | None = None,
    source_bank_account_id: int | None = None,
    account_id: int | None = None,
    bill_id: int | None = None,
    voided: str = "false",
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
):
    from sqlalchemy import or_, func

    q = (
        select(CashBookEntry)
        .options(
            joinedload(CashBookEntry.category),
            joinedload(CashBookEntry.bill),
            joinedload(CashBookEntry.source_bank_account),
            joinedload(CashBookEntry.dest_bank_account),
        )
        .order_by(CashBookEntry.entry_date.desc(), CashBookEntry.id.desc())
    )
    if company_id is not None:
        q = q.where(CashBookEntry.company_id == company_id)
    if entry_type is not None:
        q = q.where(CashBookEntry.entry_type == entry_type)
    if category_id is not None:
        q = q.where(CashBookEntry.category_id == category_id)
    if source_payment_mode is not None:
        q = q.where(CashBookEntry.source_payment_mode == source_payment_mode)
    if source_bank_account_id is not None:
        q = q.where(
            (CashBookEntry.source_bank_account_id == source_bank_account_id)
            | (CashBookEntry.dest_bank_account_id == source_bank_account_id)
        )
    if account_id is not None:
        from sqlalchemy import and_

        account = db.get(BankAccount, account_id)
        if account is None or (
            company_id is not None and int(account.company_id) != int(company_id)
        ):
            q = q.where(CashBookEntry.id == -1)
        elif account.kind == BankAccountKind.cash:
            q = q.where(
                or_(
                    CashBookEntry.source_account_id == account_id,
                    CashBookEntry.dest_account_id == account_id,
                    and_(
                        CashBookEntry.source_account_id.is_(None),
                        CashBookEntry.source_payment_mode == CashBookSourceMode.cash,
                    ),
                    and_(
                        CashBookEntry.dest_account_id.is_(None),
                        CashBookEntry.dest_payment_mode == CashBookSourceMode.cash,
                    ),
                )
            )
        else:
            q = q.where(
                or_(
                    CashBookEntry.source_account_id == account_id,
                    CashBookEntry.dest_account_id == account_id,
                    CashBookEntry.source_bank_account_id == account_id,
                    CashBookEntry.dest_bank_account_id == account_id,
                )
            )
    if bill_id is not None:
        q = q.where(CashBookEntry.bill_id == bill_id)
    if voided == "false":
        q = q.where(CashBookEntry.voided_at.is_(None))
    elif voided == "true":
        q = q.where(CashBookEntry.voided_at.isnot(None))
    if date_from is not None:
        q = q.where(CashBookEntry.entry_date >= date_from)
    if date_to is not None:
        q = q.where(CashBookEntry.entry_date <= date_to)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(
            or_(
                func.lower(CashBookEntry.description).like(term),
                func.lower(CashBookEntry.reference_no).like(term),
            )
        )
    return q


def serialize_entry(entry: CashBookEntry) -> dict:
    return {
        "id": entry.id,
        "entry_type": entry.entry_type,
        "category_id": entry.category_id,
        "category_name": entry.category.name if entry.category else None,
        "category_kind": entry.category.kind if entry.category else None,
        "amount": entry.amount,
        "description": entry.description,
        "reference_no": entry.reference_no,
        "bill_id": entry.bill_id,
        "bill_number": entry.bill.bill_number if entry.bill else None,
        "source_payment_mode": entry.source_payment_mode,
        "source_bank_account_id": entry.source_bank_account_id,
        "source_bank_account_name": (
            entry.source_bank_account.name if entry.source_bank_account else None
        ),
        "dest_payment_mode": entry.dest_payment_mode,
        "dest_bank_account_id": entry.dest_bank_account_id,
        "dest_bank_account_name": (
            entry.dest_bank_account.name if entry.dest_bank_account else None
        ),
        "entry_date": entry.entry_date,
        "entry_at": entry.entry_at,
        "voided_at": entry.voided_at,
        "version": entry.version,
        "created_at": entry.created_at,
    }
