"""Spec v17.3.19 — owner admin tools (database backup download)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.permissions import (
    Permission,
    require_assigned_role,
    user_has_permission,
)
from app.database import get_db
from app.models.entities import User, UserRole
from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event
from app.services.backup import run_pg_dump

router = APIRouter(prefix="/admin", tags=["admin"])

OWNER_ONLY_BACKUP_MSG = "Only the owner can download a database backup."


def require_backup_user(user: User = Depends(require_assigned_role)) -> User:
    if user.role != UserRole.owner or not user_has_permission(user, Permission.USERS_MANAGE):
        raise HTTPException(status_code=403, detail=OWNER_ONLY_BACKUP_MSG)
    return user


def _unlink_quietly(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("/backup")
def download_backup(
    db: Session = Depends(get_db),
    user: User = Depends(require_backup_user),
):
    try:
        dump_path, filename = run_pg_dump()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    record_audit_event(
        db,
        user=user,
        action=AuditAction.BACKUP_DOWNLOADED,
        entity_type=AuditEntityType.DATABASE,
        entity_label=filename,
        metadata={"filename": filename},
    )
    return FileResponse(
        path=dump_path,
        filename=filename,
        media_type="application/octet-stream",
        background=BackgroundTask(_unlink_quietly, dump_path),
        headers={"Cache-Control": "no-store"},
    )
