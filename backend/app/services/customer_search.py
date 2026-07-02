"""Customer list search by name and phone numbers."""

from sqlalchemy import func, or_, select
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
