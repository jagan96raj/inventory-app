"""Spec v17.3.22 — company notes board service."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import CompanyNote, CompanyNoteRoleAccess, User, UserRole
from app.utils.time import business_today, utc_now
from app.core.tenant import company_id_for_user

OWNER_ONLY_NOTES_MSG = "Only the owner can create, edit, or delete notes."
NOTE_NOT_FOUND_MSG = "Note not found."
INVALID_VIEWER_ROLE_MSG = "viewer_roles may only include writer, stock_manager, or factory_manager."

SHAREABLE_ROLES: frozenset[str] = frozenset(
    {
        UserRole.writer.value,
        UserRole.stock_manager.value,
        UserRole.factory_manager.value,
    }
)


def _normalize_viewer_roles(roles: list[str] | None) -> list[str]:
    if not roles:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in roles:
        role = (raw or "").strip().lower()
        if not role:
            continue
        if role not in SHAREABLE_ROLES:
            raise ValueError(INVALID_VIEWER_ROLE_MSG)
        if role not in seen:
            seen.add(role)
            cleaned.append(role)
    return cleaned


def _viewer_roles_for_note(note: CompanyNote) -> list[str]:
    return sorted({row.role for row in (note.role_access or []) if row.role in SHAREABLE_ROLES})


def note_visible_to_user(note: CompanyNote, user: User) -> bool:
    if user.role == UserRole.owner:
        return True
    if user.role is None:
        return False
    role_val = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    return any(row.role == role_val for row in (note.role_access or []))


def serialize_note(note: CompanyNote) -> dict:
    created_by = note.created_by
    updated_by = note.updated_by
    viewer_roles = _viewer_roles_for_note(note)
    return {
        "id": note.id,
        "company_id": note.company_id,
        "title": note.title,
        "body": note.body,
        "note_date": note.note_date,
        "viewer_roles": viewer_roles,
        "created_by_user_id": note.created_by_user_id,
        "created_by_name": created_by.name if created_by else None,
        "updated_by_user_id": note.updated_by_user_id,
        "updated_by_name": updated_by.name if updated_by else None,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def _set_role_access(db: Session, note: CompanyNote, viewer_roles: list[str]) -> None:
    note.role_access.clear()
    db.flush()
    for role in viewer_roles:
        note.role_access.append(CompanyNoteRoleAccess(role=role))


def list_notes(db: Session, user: User) -> list[dict]:
    company_id = company_id_for_user(user)
    q = (
        select(CompanyNote)
        .where(CompanyNote.company_id == company_id)
        .options(
            selectinload(CompanyNote.role_access),
            selectinload(CompanyNote.created_by),
            selectinload(CompanyNote.updated_by),
        )
        .order_by(CompanyNote.note_date.desc(), CompanyNote.created_at.desc())
    )
    rows = list(db.scalars(q).unique().all())
    if user.role != UserRole.owner:
        rows = [n for n in rows if note_visible_to_user(n, user)]
    return [serialize_note(n) for n in rows]


def get_note_for_user(db: Session, note_id: int, user: User) -> CompanyNote:
    note = db.scalar(
        select(CompanyNote)
        .where(CompanyNote.id == note_id, CompanyNote.company_id == company_id_for_user(user))
        .options(
            selectinload(CompanyNote.role_access),
            selectinload(CompanyNote.created_by),
            selectinload(CompanyNote.updated_by),
        )
    )
    if note is None or not note_visible_to_user(note, user):
        raise LookupError(NOTE_NOT_FOUND_MSG)
    return note


def create_note(
    db: Session,
    user: User,
    *,
    body: str,
    title: str | None = None,
    note_date: date | None = None,
    viewer_roles: list[str] | None = None,
) -> dict:
    if user.role != UserRole.owner:
        raise PermissionError(OWNER_ONLY_NOTES_MSG)
    text = (body or "").strip()
    if not text:
        raise ValueError("Note body is required.")
    title_clean = (title or "").strip() or None
    roles = _normalize_viewer_roles(viewer_roles)
    note = CompanyNote(
        company_id=company_id_for_user(user),
        title=title_clean,
        body=text,
        note_date=note_date or business_today(),
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add(note)
    db.flush()
    _set_role_access(db, note, roles)
    db.commit()
    return serialize_note(get_note_for_user(db, note.id, user))


def update_note(
    db: Session,
    user: User,
    note_id: int,
    *,
    body: str | None = None,
    title: str | None = ...,  # type: ignore[assignment]
    note_date: date | None = None,
    viewer_roles: list[str] | None = ...,  # type: ignore[assignment]
) -> dict:
    note = get_note_for_user(db, note_id, user)
    if user.role != UserRole.owner:
        raise PermissionError(OWNER_ONLY_NOTES_MSG)
    if body is not None:
        text = body.strip()
        if not text:
            raise ValueError("Note body is required.")
        note.body = text
    if title is not ...:
        note.title = (title or "").strip() or None
    if note_date is not None:
        note.note_date = note_date
    if viewer_roles is not ...:
        roles = _normalize_viewer_roles(viewer_roles)
        _set_role_access(db, note, roles)
    note.updated_by_user_id = user.id
    note.updated_at = utc_now()
    db.commit()
    return serialize_note(get_note_for_user(db, note.id, user))


def delete_note(db: Session, user: User, note_id: int) -> None:
    note = get_note_for_user(db, note_id, user)
    if user.role != UserRole.owner:
        raise PermissionError(OWNER_ONLY_NOTES_MSG)
    db.delete(note)
    db.commit()
