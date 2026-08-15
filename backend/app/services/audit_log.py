"""Spec v16.0.5 — central audit log service."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, User

logger = logging.getLogger(__name__)


class AuditAction:
    PAYMENT_VOIDED = "payment_voided"
    FULFILLMENT_VOIDED = "fulfillment_voided"
    BILL_VOIDED = "bill_voided"
    BILL_EDITED = "bill_edited"
    INVENTORY_QTY_EDITED = "inventory_qty_edited"
    MASTER_DELETED = "master_deleted"
    BAG_CHANGE_VOIDED = "bag_change_voided"
    PRODUCT_TRANSFER_VOIDED = "product_transfer_voided"
    STOCK_DISPOSAL_VOIDED = "stock_disposal_voided"
    PROCESSING_BATCH_VOIDED = "processing_batch_voided"
    CASH_BOOK_VOIDED = "cash_book_voided"
    JOB_WORK_ORDER_VOIDED = "job_work_order_voided"
    JOB_WORK_RECEIPT_VOIDED = "job_work_receipt_voided"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DISABLED = "user_disabled"
    USER_ENABLED = "user_enabled"
    COMPANY_REGISTERED = "company_registered"
    BACKUP_DOWNLOADED = "backup_downloaded"


class AuditEntityType:
    PAYMENT = "payment"
    BILL = "bill"
    FULFILLMENT_ENTRY = "fulfillment_entry"
    INVENTORY = "inventory"
    PRODUCT = "product"
    BRAND = "brand"
    CUSTOMER = "customer"
    LOCATION = "location"
    BAG_TYPE = "bag_type"
    BAG_CHANGE = "bag_change"
    PRODUCT_TRANSFER = "product_transfer"
    STOCK_DISPOSAL = "stock_disposal"
    PROCESSING_BATCH = "processing_batch"
    CASH_BOOK_ENTRY = "cash_book_entry"
    JOB_WORK_ORDER = "job_work_order"
    JOB_WORK_RECEIPT = "job_work_receipt"
    USER = "user"
    COMPANY = "company"
    DATABASE = "database"


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    blocked = {"password", "new_password", "password_hash", "password_plain", "void_password"}
    return {k: v for k, v in metadata.items() if k not in blocked}


def record_audit_event(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    entity_label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append an audit row. Never raises — failures are logged only."""
    try:
        row = AuditEvent(
            company_id=user.company_id if user else 1,
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label,
            metadata_json=_sanitize_metadata(metadata),
        )
        db.add(row)
        db.commit()
    except Exception:
        logger.warning(
            "Failed to record audit event action=%s entity_type=%s entity_id=%s",
            action,
            entity_type,
            entity_id,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass


def audit_event_to_out(row: AuditEvent) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "user_email": row.user_email,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "entity_label": row.entity_label,
        "metadata": row.metadata_json,
        "created_at": row.created_at,
    }
