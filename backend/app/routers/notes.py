"""Spec v17.3.22 — company notes board API."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import Permission, require_permission
from app.database import get_db
from app.models.entities import User
from app.services import notes as notes_svc

router = APIRouter(prefix="/notes", tags=["notes"])

VIEW = [Depends(require_permission(Permission.NOTES_VIEW))]


class NoteCreateIn(BaseModel):
    title: str | None = Field(None, max_length=255)
    body: str = Field(..., min_length=1)
    note_date: date | None = None
    viewer_roles: list[str] = Field(default_factory=list)


class NoteUpdateIn(BaseModel):
    title: str | None = Field(None, max_length=255)
    body: str | None = Field(None, min_length=1)
    note_date: date | None = None
    viewer_roles: list[str] | None = None


class NoteOut(BaseModel):
    id: int
    company_id: int
    title: str | None = None
    body: str
    note_date: date
    viewer_roles: list[str]
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    updated_by_user_id: int | None = None
    updated_by_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


def _http_from_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc) or notes_svc.OWNER_ONLY_NOTES_MSG)
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc) or notes_svc.NOTE_NOT_FOUND_MSG)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("", response_model=list[NoteOut], dependencies=VIEW)
def list_notes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return notes_svc.list_notes(db, user)


@router.post("", response_model=NoteOut, status_code=201, dependencies=VIEW)
def create_note(
    body: NoteCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return notes_svc.create_note(
            db,
            user,
            body=body.body,
            title=body.title,
            note_date=body.note_date,
            viewer_roles=body.viewer_roles,
        )
    except Exception as exc:
        raise _http_from_exc(exc) from exc


@router.patch("/{note_id}", response_model=NoteOut, dependencies=VIEW)
def update_note(
    note_id: int,
    body: NoteUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = body.model_dump(exclude_unset=True)
    try:
        return notes_svc.update_note(
            db,
            user,
            note_id,
            body=payload.get("body"),
            title=payload["title"] if "title" in payload else ...,
            note_date=payload.get("note_date"),
            viewer_roles=payload["viewer_roles"] if "viewer_roles" in payload else ...,
        )
    except Exception as exc:
        raise _http_from_exc(exc) from exc


@router.delete("/{note_id}", status_code=204, dependencies=VIEW)
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        notes_svc.delete_note(db, user, note_id)
    except Exception as exc:
        raise _http_from_exc(exc) from exc
