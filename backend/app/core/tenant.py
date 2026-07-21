"""Spec v17.0.2 — multi-tenant helpers (Phase 3: tenant-scoped reads + write stamps)."""

from __future__ import annotations

from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import User
from app.services.companies import DEFAULT_COMPANY_ID

CROSS_COMPANY_MSG = "belongs to another company"

T = TypeVar("T")


def company_id_for_user(user: User | None) -> int:
    if user is None:
        return DEFAULT_COMPANY_ID
    cid = getattr(user, "company_id", None)
    if cid is None:
        return DEFAULT_COMPANY_ID
    return int(cid)


def company_filter(model: Any, company_id: int):
    """SQLAlchemy filter clause: model.company_id == company_id."""
    return model.company_id == company_id


def scope_query(q: Any, model: Any, company_id: int):
    """Apply company_id filter to a SQLAlchemy query/select."""
    return q.where(company_filter(model, company_id))


def apply_company_on_create(entity: Any, company_id: int) -> Any:
    if hasattr(entity, "company_id"):
        entity.company_id = company_id
    return entity


def assert_entity_company(entity: Any | None, company_id: int, label: str) -> None:
    if entity is None:
        raise ValueError(f"{label} not found")
    entity_cid = getattr(entity, "company_id", None)
    if entity_cid is None:
        entity_cid = DEFAULT_COMPANY_ID
    if int(entity_cid) != int(company_id):
        raise ValueError(f"{label} {CROSS_COMPANY_MSG}")


def get_for_company(
    db: Session,
    model: type[T],
    entity_id: int,
    company_id: int,
) -> T | None:
    """Load by primary key only if the row belongs to company_id."""
    entity = db.get(model, entity_id)
    if entity is None:
        return None
    entity_cid = getattr(entity, "company_id", None)
    if entity_cid is None:
        entity_cid = DEFAULT_COMPANY_ID
    if int(entity_cid) != int(company_id):
        return None
    return entity


def require_for_company(
    db: Session,
    model: type[T],
    entity_id: int,
    company_id: int,
    *,
    label: str = "Record",
) -> T:
    """Load by PK+company; raise HTTP 404 if missing or cross-company (no existence leak)."""
    entity = get_for_company(db, model, entity_id, company_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return entity


def require_entity_company(entity: Any | None, company_id: int, *, label: str = "Record") -> Any:
    """Assert an already-loaded entity belongs to company_id; 404 otherwise."""
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    entity_cid = getattr(entity, "company_id", None)
    if entity_cid is None:
        entity_cid = DEFAULT_COMPANY_ID
    if int(entity_cid) != int(company_id):
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return entity
