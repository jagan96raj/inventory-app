"""Spec v12.11 — bill row locking for concurrent bill writes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.entities import Bill

BILL_IN_USE_MSG = "Bill is in use. Please try again in a moment."


def _is_lock_error(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    if pgcode == "55P03":  # lock_not_available (Postgres NOWAIT)
        return True
    text = str(orig or exc).lower()
    return "could not obtain lock" in text or "database is locked" in text


def lock_bill_for_update(db: Session, bill_id: int) -> Bill | None:
    """Lock one bill row for write workflows; GET paths must not use this."""
    try:
        return db.scalar(select(Bill).where(Bill.id == bill_id).with_for_update(nowait=True))
    except OperationalError as exc:
        if _is_lock_error(exc):
            raise ValueError(BILL_IN_USE_MSG) from exc
        raise


def lock_bills_for_update(db: Session, bill_ids: list[int]) -> dict[int, Bill | None]:
    """Lock multiple bill rows in sorted order to reduce deadlock risk."""
    locked: dict[int, Bill | None] = {}
    for bill_id in sorted(set(bill_ids)):
        locked[bill_id] = lock_bill_for_update(db, bill_id)
    return locked
