"""Spec v12.21 — expense category master CRUD with system + in-use guards."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import CashBookEntry, ExpenseCategory, ExpenseCategoryKind


CATEGORY_NOT_FOUND_MSG = "Expense category not found"
CATEGORY_DUPLICATE_MSG = "Expense category name already exists"
CATEGORY_NAME_REQUIRED_MSG = "Expense category name is required"
CATEGORY_SYSTEM_LOCKED_MSG = "System category cannot be modified"
CATEGORY_TRANSFER_KIND_FORBIDDEN_MSG = "Transfer categories are system-managed"

DEFAULT_EXPENSE_CATEGORY_SEED: list[tuple[str, ExpenseCategoryKind, bool]] = [
    ("Rent", ExpenseCategoryKind.expense, False),
    ("Wages", ExpenseCategoryKind.expense, False),
    ("Salary", ExpenseCategoryKind.expense, False),
    ("Loan Repayment", ExpenseCategoryKind.expense, False),
    ("EB Bill", ExpenseCategoryKind.expense, False),
    ("Freight Charges", ExpenseCategoryKind.expense, False),
    ("Other Expenses", ExpenseCategoryKind.expense, False),
    ("Self Withdrawal", ExpenseCategoryKind.expense, False),
    ("Capital Increase", ExpenseCategoryKind.income, False),
    ("Transfer", ExpenseCategoryKind.transfer, True),
]


def _normalize_name(name: str) -> str:
    return (name or "").strip()


def _name_exists_active(db: Session, name: str, company_id: int, exclude_id: int | None = None) -> bool:
    q = select(ExpenseCategory.id).where(
        ExpenseCategory.company_id == company_id,
        func.lower(func.trim(ExpenseCategory.name)) == name.lower(),
        ExpenseCategory.is_active.is_(True),
    )
    if exclude_id is not None:
        q = q.where(ExpenseCategory.id != exclude_id)
    return db.scalar(q) is not None


def seed_default_expense_categories(db: Session, company_id: int) -> None:
    existing = {
        row[0]
        for row in db.execute(
            select(func.lower(func.trim(ExpenseCategory.name))).where(
                ExpenseCategory.company_id == company_id
            )
        ).all()
        if row[0]
    }
    for name, kind, is_system in DEFAULT_EXPENSE_CATEGORY_SEED:
        normalized = name.lower()
        if normalized in existing:
            continue
        db.add(
            ExpenseCategory(
                company_id=company_id,
                name=name,
                kind=kind,
                is_system=is_system,
                is_active=True,
            )
        )
        existing.add(normalized)


def list_categories(
    db: Session,
    *,
    company_id: int | None = None,
    active: str = "true",
    kind: ExpenseCategoryKind | None = None,
) -> list[ExpenseCategory]:
    q = select(ExpenseCategory).order_by(
        ExpenseCategory.kind, ExpenseCategory.is_system.desc(), ExpenseCategory.name
    )
    if company_id is not None:
        q = q.where(ExpenseCategory.company_id == company_id)
    if active == "true":
        q = q.where(ExpenseCategory.is_active.is_(True))
    elif active == "false":
        q = q.where(ExpenseCategory.is_active.is_(False))
    if kind is not None:
        q = q.where(ExpenseCategory.kind == kind)
    return list(db.scalars(q).all())


def create_category(
    db: Session, *, company_id: int = 1, name: str, kind: ExpenseCategoryKind
) -> ExpenseCategory:
    if kind == ExpenseCategoryKind.transfer:
        raise ValueError(CATEGORY_TRANSFER_KIND_FORBIDDEN_MSG)
    clean = _normalize_name(name)
    if not clean:
        raise ValueError(CATEGORY_NAME_REQUIRED_MSG)
    if _name_exists_active(db, clean, company_id):
        raise ValueError(CATEGORY_DUPLICATE_MSG)
    record = ExpenseCategory(name=clean, kind=kind, is_system=False, is_active=True, company_id=company_id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def edit_category(
    db: Session,
    category_id: int,
    *,
    company_id: int | None = None,
    name: str | None,
    is_active: bool | None,
) -> ExpenseCategory:
    record = db.get(ExpenseCategory, category_id)
    if not record:
        raise ValueError(CATEGORY_NOT_FOUND_MSG)
    if company_id is not None and int(record.company_id) != int(company_id):
        raise ValueError(CATEGORY_NOT_FOUND_MSG)
    if record.is_system:
        raise ValueError(CATEGORY_SYSTEM_LOCKED_MSG)
    if name is not None:
        clean = _normalize_name(name)
        if not clean:
            raise ValueError(CATEGORY_NAME_REQUIRED_MSG)
        if _name_exists_active(db, clean, record.company_id, exclude_id=category_id):
            raise ValueError(CATEGORY_DUPLICATE_MSG)
        record.name = clean
    if is_active is not None:
        record.is_active = is_active
    db.commit()
    db.refresh(record)
    return record


def assert_category_deletable(db: Session, category_id: int) -> None:
    record = db.get(ExpenseCategory, category_id)
    if not record:
        raise ValueError(CATEGORY_NOT_FOUND_MSG)
    if record.is_system:
        raise ValueError("System category cannot be deleted")
    in_use = db.scalar(
        select(func.count(CashBookEntry.id)).where(CashBookEntry.category_id == category_id)
    ) or 0
    if in_use:
        raise ValueError(f"Category in use by {in_use} cash book entry(ies)")


def delete_category(db: Session, category_id: int, *, company_id: int | None = None) -> None:
    record = db.get(ExpenseCategory, category_id)
    if not record:
        raise ValueError(CATEGORY_NOT_FOUND_MSG)
    if company_id is not None and int(record.company_id) != int(company_id):
        raise ValueError(CATEGORY_NOT_FOUND_MSG)
    assert_category_deletable(db, category_id)
    record.is_active = False
    db.commit()
