"""Spec v16.0.6 — login history API (owner only)."""

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.pagination import clamp_limit, clamp_offset, page_dict, paginate_select
from app.core.permissions import Permission, require_permission
from app.database import get_db
from app.models.entities import LoginEvent
from app.schemas import LoginEventOut, LoginEventPageOut
from app.services.login_history import login_event_to_out

router = APIRouter(prefix="/login-history", tags=["login-history"])

AUDIT_VIEW = [Depends(require_permission(Permission.AUDIT_VIEW))]


@router.get("/events", response_model=LoginEventPageOut, dependencies=AUDIT_VIEW)
def list_login_events(
    email: str | None = None,
    user_id: int | None = None,
    success: str | None = Query(None, description="true, false, or all"),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = select(LoginEvent).order_by(LoginEvent.created_at.desc(), LoginEvent.id.desc())
    if email and email.strip():
        q = q.where(LoginEvent.email == email.strip().lower())
    if user_id is not None:
        q = q.where(LoginEvent.user_id == user_id)
    if success and success.strip().lower() not in ("", "all"):
        normalized = success.strip().lower()
        if normalized == "true":
            q = q.where(LoginEvent.success.is_(True))
        elif normalized == "false":
            q = q.where(LoginEvent.success.is_(False))
    if date_from is not None:
        start = datetime.combine(date_from, time.min)
        q = q.where(LoginEvent.created_at >= start)
    if date_to is not None:
        end = datetime.combine(date_to, time.max)
        q = q.where(LoginEvent.created_at <= end)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(func.lower(LoginEvent.email).like(term))
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [LoginEventOut(**login_event_to_out(r)) for r in rows]
    return LoginEventPageOut(**page_dict(items, total, limit, offset))
