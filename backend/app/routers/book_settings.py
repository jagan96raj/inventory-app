"""Spec v12.21 / v17.0.3 — book settings (per-company cash opening, print header, powder)."""
from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.permissions import Permission, require_permission
from app.core.tenant import company_id_for_user
from app.database import get_db
from app.models.entities import User
from app.schemas import BookSettingsOut, BookSettingsUpdate
from app.services.accounts import get_book_settings, serialize_book_settings, update_book_settings
from app.services.idempotency import hash_pydantic_body

router = APIRouter(prefix="/book-settings", tags=["book-settings"])

VIEW = [Depends(require_permission(Permission.BOOK_SETTINGS_VIEW))]
EDIT = [Depends(require_permission(Permission.BOOK_SETTINGS_EDIT))]


@router.get("", response_model=BookSettingsOut, dependencies=VIEW)
def get_book_settings_endpoint(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = company_id_for_user(user)
    return BookSettingsOut.model_validate(serialize_book_settings(get_book_settings(db, company_id)))


@router.patch("", response_model=BookSettingsOut, dependencies=EDIT)
def patch_book_settings_endpoint(
    body: BookSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "PATCH /api/book-settings"
    request_hash = hash_pydantic_body(body)

    def execute():
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(400, "No fields to update")
        try:
            record = update_book_settings(db, company_id_for_user(user), updates)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = BookSettingsOut.model_validate(serialize_book_settings(record))
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)
