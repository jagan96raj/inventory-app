"""Spec v14.0 — Job Work HTTP API."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict
from app.core.permissions import (
    Permission,
    require_any_permission,
    require_permission,
    require_void_user,
)
from app.core.void_auth import VOID_AUTH_HEADER, verify_backdate_authorization, verify_void_authorization
from app.database import get_db
from app.models.entities import JobWorkOrderStatus, User
from app.schemas import (
    JobWorkFulfillmentOrderOut,
    JobWorkFulfillmentOrderPageOut,
    JobWorkOrderCreate,
    JobWorkOrderOut,
    JobWorkOrderPageOut,
    JobWorkReceiveIn,
    JobWorkReceiptOut,
    JobWorkReturnIn,
    JobWorkStatementOut,
)
from app.services.idempotency import hash_pydantic_body
from app.services.job_work import (
    create_job_work_order,
    get_customer_job_work_statement,
    list_job_work_orders,
    list_jw_fulfillment_orders,
    load_job_work_order,
    preview_job_number,
    receive_job_work,
    return_job_work_to_customer,
    serialize_job_work_order,
    void_job_work_order,
    void_job_work_receipt,
    _serialize_receipt_summary,
)

router = APIRouter(tags=["job-work"])

MANAGE = [Depends(require_permission(Permission.JOB_WORK_MANAGE))]
FULFILLMENT = [
    Depends(
        require_any_permission(
            Permission.JOB_WORK_MANAGE,
            Permission.JOB_WORK_FULFILLMENT_WRITE,
        )
    )
]
FULFILLMENT_WRITE = [Depends(require_permission(Permission.JOB_WORK_FULFILLMENT_WRITE))]


@router.get("/job-work/next-number", dependencies=MANAGE)
def preview_next_job_number(db: Session = Depends(get_db)):
    return {"job_number": preview_job_number(db)}


@router.get("/job-work", response_model=JobWorkOrderPageOut, dependencies=MANAGE)
def list_orders(
    customer_id: int | None = None,
    status: JobWorkOrderStatus | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    rows, total = list_job_work_orders(
        db, customer_id=customer_id, status=status, limit=limit, offset=offset
    )
    items = [JobWorkOrderOut.model_validate(serialize_job_work_order(r)) for r in rows]
    return JobWorkOrderPageOut(**page_dict(items, total, limit, offset))


@router.post("/job-work", response_model=JobWorkOrderOut, status_code=201, dependencies=MANAGE)
def create_order(
    body: JobWorkOrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_backdate_authorization(body.job_date, void_password, user)
    route_key = "POST /api/job-work"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            order = create_job_work_order(
                db,
                customer_id=body.customer_id,
                job_date=body.job_date,
                notes=body.notes,
                lines=[ln.model_dump() for ln in body.lines],
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = JobWorkOrderOut.model_validate(serialize_job_work_order(order))
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.get("/job-work/fulfillment/orders", response_model=JobWorkFulfillmentOrderPageOut, dependencies=FULFILLMENT)
def list_fulfillment_orders(
    tab: str = Query("all", pattern="^(all|receive|return)$"),
    visibility: str = Query("actionable", pattern="^(actionable|all)$"),
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Open JW orders with bill-like receive/return lines (unified list; tab receive/return for legacy filters)."""
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    rows, total = list_jw_fulfillment_orders(
        db, tab=tab, visibility=visibility, limit=limit, offset=offset
    )
    items = [JobWorkFulfillmentOrderOut.model_validate(r) for r in rows]
    return JobWorkFulfillmentOrderPageOut(**page_dict(items, total, limit, offset))


@router.get("/job-work/{order_id}", response_model=JobWorkOrderOut, dependencies=MANAGE)
def get_order(order_id: int, db: Session = Depends(get_db)):
    try:
        order = load_job_work_order(db, order_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return JobWorkOrderOut.model_validate(serialize_job_work_order(order))


@router.post("/job-work/{order_id}/void", response_model=JobWorkOrderOut, dependencies=MANAGE)
def void_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    route_key = f"POST /api/job-work/{order_id}/void"
    request_hash = ""

    def execute():
        verify_void_authorization(void_password, user)
        try:
            order = void_job_work_order(db, order_id, actor=user)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = JobWorkOrderOut.model_validate(serialize_job_work_order(order))
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/job-work/receive", response_model=JobWorkReceiptOut, status_code=201, dependencies=FULFILLMENT_WRITE)
def receive_material(
    body: JobWorkReceiveIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_backdate_authorization(body.received_date, void_password, user)
    route_key = "POST /api/job-work/receive"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            receipt = receive_job_work(
                db,
                line_id=body.line_id,
                location_id=body.location_id,
                bag_count=body.bag_count,
                loose_kg=body.loose_kg,
                vehicle_no=body.vehicle_no,
                notes=body.notes,
                received_date=body.received_date,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = JobWorkReceiptOut.model_validate(_serialize_receipt_summary(receipt))
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/job-work/receipts/{receipt_id}/void", response_model=JobWorkReceiptOut)
def void_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    route_key = f"POST /api/job-work/receipts/{receipt_id}/void"
    request_hash = ""

    def execute():
        verify_void_authorization(void_password, user)
        try:
            receipt = void_job_work_receipt(db, receipt_id, actor=user)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = JobWorkReceiptOut.model_validate(_serialize_receipt_summary(receipt))
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/job-work/return", response_model=JobWorkOrderOut, dependencies=FULFILLMENT_WRITE)
def return_to_customer(
    body: JobWorkReturnIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_backdate_authorization(body.received_date, void_password, user)
    route_key = "POST /api/job-work/return"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            return_job_work_to_customer(
                db,
                line_id=body.line_id,
                location_id=body.location_id,
                bag_count=body.bag_count,
                loose_kg=body.loose_kg,
                notes=body.notes,
                received_date=body.received_date,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        from app.models.entities import JobWorkLine

        line = db.get(JobWorkLine, body.line_id)
        if not line:
            raise HTTPException(404, "Line not found")
        order = load_job_work_order(db, line.order_id)
        out = JobWorkOrderOut.model_validate(serialize_job_work_order(order))
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.get("/job-work/customers/{customer_id}/statement", response_model=JobWorkStatementOut, dependencies=MANAGE)
def customer_statement(
    customer_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
):
    try:
        data = get_customer_job_work_statement(
            db, customer_id, from_date=from_date, to_date=to_date
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return JobWorkStatementOut.model_validate(data)
