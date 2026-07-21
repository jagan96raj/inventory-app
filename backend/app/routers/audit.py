"""Spec v16.0.5 — central audit log API (owner only)."""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.pagination import clamp_limit, clamp_offset, page_dict, paginate_select
from app.core.permissions import Permission, require_permission
from app.core.tenant import company_id_for_user
from app.database import get_db
from app.models.entities import AuditEvent, User
from app.schemas import AuditEventOut, AuditEventPageOut
from app.services.audit_log import audit_event_to_out
from app.utils.time import business_tz

router = APIRouter(prefix="/audit", tags=["audit"])

AUDIT_VIEW = [Depends(require_permission(Permission.AUDIT_VIEW))]


@router.get("/events", response_model=AuditEventPageOut, dependencies=AUDIT_VIEW)
def list_audit_events(
    user_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    company_id = company_id_for_user(user)
    q = (
        select(AuditEvent)
        .where(AuditEvent.company_id == company_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
    if user_id is not None:
        q = q.where(AuditEvent.user_id == user_id)
    if action and action.strip():
        q = q.where(AuditEvent.action == action.strip())
    if entity_type and entity_type.strip():
        q = q.where(AuditEvent.entity_type == entity_type.strip())
    if date_from is not None:
        start = datetime.combine(date_from, time.min, tzinfo=business_tz()).astimezone(timezone.utc)
        q = q.where(AuditEvent.created_at >= start)
    if date_to is not None:
        end = datetime.combine(date_to, time.max, tzinfo=business_tz()).astimezone(timezone.utc)
        q = q.where(AuditEvent.created_at <= end)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(
            or_(
                func.lower(AuditEvent.entity_label).like(term),
                func.lower(AuditEvent.user_email).like(term),
            )
        )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [AuditEventOut(**audit_event_to_out(r)) for r in rows]
    return AuditEventPageOut(**page_dict(items, total, limit, offset))
