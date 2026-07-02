"""Shared pagination helpers for list endpoints."""
from __future__ import annotations

from typing import Any, Sequence, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
BULK_MAX_LIMIT = 500

T = TypeVar("T")


def clamp_limit(limit: int) -> int:
    """Clamp limit to 1..BULK_MAX_LIMIT (forms may request up to 500)."""
    return max(1, min(limit, BULK_MAX_LIMIT))


def clamp_offset(offset: int) -> int:
    return max(0, offset)


def count_select(db: Session, stmt: Select) -> int:
    """Count rows matching a SELECT (ignores order/limit/offset)."""
    subq = stmt.order_by(None).limit(None).offset(None).subquery()
    return db.scalar(select(func.count()).select_from(subq)) or 0


def paginate_select(
    db: Session,
    stmt: Select,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Any], int]:
    total = count_select(db, stmt)
    rows = db.scalars(stmt.limit(limit).offset(offset)).unique().all()
    return list(rows), total


def page_dict(items: Sequence[T], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {"items": list(items), "total": total, "limit": limit, "offset": offset}
