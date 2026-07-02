import logging
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.auth import get_current_user
from app.core.permissions import Permission, require_permission, require_void_user
from app.core.void_auth import VOID_AUTH_HEADER, verify_void_authorization
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.database import get_db
from app.models.entities import Bill, BillLine, BillStatus, BillType, FulfillmentEntry, FulfillmentType, User
from app.services.idempotency import hash_empty_body, hash_pydantic_body
from app.schemas import (
    FulfillmentAuditPageOut,
    FulfillmentBillEventCreate,
    FulfillmentCreate,
    FulfillmentEntryPageOut,
    FulfillmentOut,
    FulfillmentAuditOut,
)
from app.services.fulfillment import (
    bill_is_actionable,
    create_bill_fulfillment_event,
    create_fulfillment,
    fulfillment_audit_query,
    fulfillment_audit_to_out,
    fulfillment_entry_to_out,
    load_fulfillment_line,
    serialize_fulfillment_bill,
    serialize_fulfillment_line,
    void_fulfillment_entry,
)
from app.services.bill_concurrency import EXPECTED_BILL_VERSION_HEADER, http_exception_for_value_error
from app.utils.time import utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["fulfillment"])

VIEW = [Depends(require_permission(Permission.FULFILLMENT_VIEW))]
WRITE = [Depends(require_permission(Permission.FULFILLMENT_WRITE))]


@router.get("/fulfillment/lines/{line_id}", dependencies=VIEW)
def get_fulfillment_line(
    line_id: int,
    parent_entry_id: int | None = None,
    db: Session = Depends(get_db),
):
    line = load_fulfillment_line(db, line_id)
    if not line or not line.bill:
        raise HTTPException(404, "Bill line not found")
    if line.bill.status != BillStatus.finalized:
        raise HTTPException(400, "Bill must be finalized")
    return serialize_fulfillment_line(db, line.bill, line, context_parent_entry_id=parent_entry_id)


@router.get("/fulfillment/bills", dependencies=VIEW)
def list_fulfillment_bills(
    bill_type: str = Query("all", pattern="^(purchase|sales|all)$"),
    visibility: str = Query("actionable", pattern="^(actionable|all)$"),
    tab: str = Query("deliver", pattern="^(deliver|return)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(400, "date_from must be on or before date_to")
    q = (
        select(Bill)
        .where(Bill.status == BillStatus.finalized)
        .options(
            joinedload(Bill.lines).joinedload(BillLine.product),
            joinedload(Bill.lines).joinedload(BillLine.brand),
            joinedload(Bill.lines).joinedload(BillLine.bag_type),
            joinedload(Bill.customer),
            joinedload(Bill.location),
        )
        .order_by(Bill.id.desc())
    )
    if bill_type == "purchase":
        q = q.where(Bill.bill_type == BillType.purchase)
    elif bill_type == "sales":
        q = q.where(Bill.bill_type == BillType.sales)
    if date_from is not None:
        q = q.where(Bill.bill_date >= date_from)
    if date_to is not None:
        q = q.where(Bill.bill_date <= date_to)

    bills = db.scalars(q).unique().all()
    result = []
    for b in bills:
        data = serialize_fulfillment_bill(db, b)
        if visibility == "actionable" and not bill_is_actionable(data, tab):
            continue
        result.append(data)
    total = len(result)
    page_items = result[offset : offset + limit]
    return page_dict(page_items, total, limit, offset)


@router.get("/fulfillment/entries", response_model=FulfillmentEntryPageOut, dependencies=VIEW)
def list_entries(
    bill_line_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = (
        select(FulfillmentEntry)
        .options(joinedload(FulfillmentEntry.location))
        .order_by(FulfillmentEntry.fulfilled_at.desc(), FulfillmentEntry.id.desc())
    )
    if bill_line_id:
        q = q.where(FulfillmentEntry.bill_line_id == bill_line_id)
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [FulfillmentOut(**fulfillment_entry_to_out(r)) for r in rows]
    return FulfillmentEntryPageOut(**page_dict(items, total, limit, offset))


@router.get("/fulfillment/audit", response_model=FulfillmentAuditPageOut, dependencies=VIEW)
def list_fulfillment_audit(
    bill_type: str = Query("all", pattern="^(purchase|sales|all)$"),
    entry_type: str = Query("all", pattern="^(deliver|return|all)$"),
    status: str = Query("all", pattern="^(all|active|voided)$"),
    bill_number: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = fulfillment_audit_query()
    q = q.where(Bill.status == BillStatus.finalized)
    if bill_type == "purchase":
        q = q.where(Bill.bill_type == BillType.purchase)
    elif bill_type == "sales":
        q = q.where(Bill.bill_type == BillType.sales)
    if entry_type == "deliver":
        q = q.where(FulfillmentEntry.entry_type == FulfillmentType.deliver)
    elif entry_type == "return":
        q = q.where(FulfillmentEntry.entry_type == FulfillmentType.return_)
    if status == "active":
        q = q.where(FulfillmentEntry.voided_at.is_(None))
    elif status == "voided":
        q = q.where(FulfillmentEntry.voided_at.isnot(None))
    if bill_number and bill_number.strip():
        q = q.where(Bill.bill_number.ilike(f"%{bill_number.strip()}%"))
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [FulfillmentAuditOut(**fulfillment_audit_to_out(r)) for r in rows]
    return FulfillmentAuditPageOut(**page_dict(items, total, limit, offset))


@router.post("/fulfillment/{entry_id}/void", response_model=FulfillmentOut)
def void_fulfillment_endpoint(
    entry_id: int,
    expected_bill_version: int | None = Header(None, alias=EXPECTED_BILL_VERSION_HEADER),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/fulfillment/{entry_id}/void"
    request_hash = hash_empty_body()

    def execute():
        try:
            entry = void_fulfillment_entry(
                db, entry_id, expected_version=expected_bill_version, actor=user
            )
        except ValueError as e:
            raise http_exception_for_value_error(e) from e
        entry = db.scalar(
            select(FulfillmentEntry)
            .where(FulfillmentEntry.id == entry.id)
            .options(joinedload(FulfillmentEntry.location))
        )
        if not entry:
            raise HTTPException(404, "Fulfillment entry not found")
        out = FulfillmentOut(**fulfillment_entry_to_out(entry))
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/fulfillment/bill-event", status_code=201, dependencies=WRITE)
def add_bill_fulfillment_event(
    body: FulfillmentBillEventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/fulfillment/bill-event"
    request_hash = hash_pydantic_body(body)

    def execute():
        line_items = [(ln.bill_line_id, ln.bag_count, ln.loose_kg) for ln in body.lines]
        try:
            result = create_bill_fulfillment_event(
                db,
                body.bill_id,
                body.entry_type,
                utc_now(),
                body.vehicle_no,
                line_items,
                location_id=body.location_id,
                expected_version=body.expected_version,
            )
        except ValueError as e:
            raise http_exception_for_value_error(e) from e
        except Exception as e:
            logger.exception("Bill fulfillment event failed")
            raise HTTPException(500, f"Fulfillment failed: {e}") from e
        return result, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/fulfillment", response_model=FulfillmentOut, status_code=201, dependencies=WRITE)
def add_fulfillment(
    body: FulfillmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/fulfillment"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            entry = create_fulfillment(
                db,
                body.bill_line_id,
                body.entry_type,
                body.quantity_kg,
                body.bag_count,
                body.loose_kg,
                location_id=body.location_id,
                parent_entry_id=body.parent_entry_id,
                notes=body.notes,
                vehicle_no=body.vehicle_no,
                expected_version=body.expected_version,
            )
        except ValueError as e:
            raise http_exception_for_value_error(e) from e
        except Exception as e:
            logger.exception("Fulfillment create failed")
            raise HTTPException(500, f"Fulfillment failed: {e}") from e
        out = FulfillmentOut(**fulfillment_entry_to_out(entry))
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)
