"""Customer list search by name and phone numbers."""

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.models.entities import Customer


def apply_customer_search(q: Select, search: str | None) -> Select:
    if not search or not search.strip():
        return q
    raw = search.strip()
    term = f"%{raw.lower()}%"
    phone_term = f"%{raw}%"
    return q.where(
        or_(
            func.lower(Customer.name).like(term),
            func.lower(func.coalesce(Customer.phone, "")).like(term),
            func.lower(func.coalesce(Customer.alternate_phone, "")).like(term),
            func.coalesce(Customer.phone, "").like(phone_term),
            func.coalesce(Customer.alternate_phone, "").like(phone_term),
        )
    )


def sum_customer_balances(
    db: Session,
    *,
    company_id: int,
    search: str | None = None,
    has_balance: str | None = None,
) -> tuple[Decimal, Decimal]:
    """SUM credit (I owe) and debit (they owe) over the filtered company set, not one page."""
    q = select(
        func.coalesce(func.sum(Customer.credit_balance), 0),
        func.coalesce(func.sum(Customer.debit_balance), 0),
    ).where(Customer.company_id == company_id)
    if has_balance == "positive":
        q = q.where((Customer.credit_balance > 0) | (Customer.debit_balance > 0))
    elif has_balance == "zero":
        q = q.where((Customer.credit_balance == 0) & (Customer.debit_balance == 0))
    q = apply_customer_search(q, search)
    credit_raw, debit_raw = db.execute(q).one()
    credit = Decimal(str(credit_raw or 0)).quantize(Decimal("0.01"))
    debit = Decimal(str(debit_raw or 0)).quantize(Decimal("0.01"))
    return credit, debit
