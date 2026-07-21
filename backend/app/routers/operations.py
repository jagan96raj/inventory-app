from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.auth import get_current_user
from app.core.permissions import Permission, require_permission, require_void_user
from app.core.void_auth import VOID_AUTH_HEADER, verify_void_authorization
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.database import get_db
from app.models.entities import (
    BagChange,
    BagChangeToLine,
    ProcessingJob,
    ProcessingJobStatus,
    ProductTransfer,
    StockDisposal,
    User,
)
from app.schemas import (
    BagChangeCreate,
    BagChangeOut,
    BagChangePageOut,
    ProcessingBatchSubmit,
    ProcessingJobCreate,
    ProcessingJobOut,
    ProcessingJobPageOut,
    ProductTransferCreate,
    ProductTransferOut,
    ProductTransferPageOut,
    StockDisposalCreate,
    StockDisposalOut,
    StockDisposalPageOut,
)
from app.core.tenant import company_id_for_user, require_for_company
from app.services.idempotency import hash_empty_body, hash_pydantic_body
from app.services.operations import (
    create_bag_change,
    create_product_transfer,
    create_stock_disposal,
    serialize_bag_change,
    serialize_product_transfer,
    serialize_stock_disposal,
    void_bag_change,
    void_product_transfer,
    void_stock_disposal,
)
from app.services.processing import (
    complete_job,
    create_job,
    fetch_processing_list_summaries,
    load_processing_job,
    serialize_processing_job,
    serialize_processing_job_list_item,
    submit_batch,
    void_processing_batch,
)

router = APIRouter(prefix="/operations", tags=["operations"])

BAG_CHANGE_VIEW = [Depends(require_permission(Permission.BAG_CHANGE_VIEW))]
BAG_CHANGE_WRITE = [Depends(require_permission(Permission.BAG_CHANGE_WRITE))]
PRODUCT_TRANSFER_VIEW = [Depends(require_permission(Permission.PRODUCT_TRANSFER_VIEW))]
PRODUCT_TRANSFER_WRITE = [Depends(require_permission(Permission.PRODUCT_TRANSFER_WRITE))]
STOCK_DISPOSAL_VIEW = [Depends(require_permission(Permission.STOCK_DISPOSAL_VIEW))]
STOCK_DISPOSAL_WRITE = [Depends(require_permission(Permission.STOCK_DISPOSAL_WRITE))]
PROCESSING_VIEW = [Depends(require_permission(Permission.PROCESSING_VIEW))]
PROCESSING_MANAGE = [Depends(require_permission(Permission.PROCESSING_MANAGE))]


@router.get("/bag-change", response_model=BagChangePageOut, dependencies=BAG_CHANGE_VIEW)
def list_bag_changes(
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    company_id = company_id_for_user(user)
    q = (
        select(BagChange)
        .where(BagChange.company_id == company_id)
        .options(
            joinedload(BagChange.location),
            joinedload(BagChange.product),
            joinedload(BagChange.brand),
            joinedload(BagChange.from_bag_type),
            joinedload(BagChange.customer),
            joinedload(BagChange.to_lines).joinedload(BagChangeToLine.to_bag_type),
        )
        .order_by(BagChange.operation_at.desc(), BagChange.id.desc())
    )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [serialize_bag_change(r) for r in rows]
    return BagChangePageOut(**page_dict(items, total, limit, offset))


@router.post("/bag-change", response_model=BagChangeOut, status_code=201, dependencies=BAG_CHANGE_WRITE)
def post_bag_change(
    body: BagChangeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/operations/bag-change"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            record = create_bag_change(
            db,
            company_id=company_id_for_user(user),
            location_id=body.location_id,
            product_id=body.product_id,
            brand_id=body.brand_id,
            from_bag_type_id=body.from_bag_type_id,
            from_bag_count=body.from_bag_count,
            from_loose_kg=body.from_loose_kg,
            quantity_loss_kg=body.quantity_loss_kg,
            to_lines=[line.model_dump() for line in body.to_lines],
            notes=body.notes,
            owner_type=body.owner_type,
            customer_id=body.customer_id,
        )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = serialize_bag_change(record)
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/bag-change/{record_id}/void", response_model=BagChangeOut)
def void_bag_change_endpoint(
    record_id: int,
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/operations/bag-change/{record_id}/void"
    request_hash = hash_empty_body()

    def execute():
        require_for_company(db, BagChange, record_id, company_id_for_user(user), label="Bag change")
        try:
            record = void_bag_change(db, record_id, actor=user)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = serialize_bag_change(record)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.get("/product-transfer", response_model=ProductTransferPageOut, dependencies=PRODUCT_TRANSFER_VIEW)
def list_product_transfers(
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    company_id = company_id_for_user(user)
    q = (
        select(ProductTransfer)
        .where(ProductTransfer.company_id == company_id)
        .options(
            joinedload(ProductTransfer.product),
            joinedload(ProductTransfer.brand),
            joinedload(ProductTransfer.bag_type),
            joinedload(ProductTransfer.from_location),
            joinedload(ProductTransfer.to_location),
            joinedload(ProductTransfer.customer),
        )
        .order_by(ProductTransfer.operation_at.desc(), ProductTransfer.id.desc())
    )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [serialize_product_transfer(r) for r in rows]
    return ProductTransferPageOut(**page_dict(items, total, limit, offset))


@router.post("/product-transfer", response_model=ProductTransferOut, status_code=201, dependencies=PRODUCT_TRANSFER_WRITE)
def post_product_transfer(
    body: ProductTransferCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/operations/product-transfer"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            record = create_product_transfer(
            db,
            company_id=company_id_for_user(user),
            product_id=body.product_id,
            brand_id=body.brand_id,
            bag_type_id=body.bag_type_id,
            from_location_id=body.from_location_id,
            to_location_id=body.to_location_id,
            bag_count=body.bag_count,
            loose_kg=body.loose_kg,
            notes=body.notes,
            owner_type=body.owner_type,
            customer_id=body.customer_id,
        )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = serialize_product_transfer(record)
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/product-transfer/{record_id}/void", response_model=ProductTransferOut)
def void_product_transfer_endpoint(
    record_id: int,
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/operations/product-transfer/{record_id}/void"
    request_hash = hash_empty_body()

    def execute():
        require_for_company(
            db, ProductTransfer, record_id, company_id_for_user(user), label="Product transfer"
        )
        try:
            record = void_product_transfer(db, record_id, actor=user)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = serialize_product_transfer(record)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.get("/stock-disposal", response_model=StockDisposalPageOut, dependencies=STOCK_DISPOSAL_VIEW)
def list_stock_disposals(
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    company_id = company_id_for_user(user)
    q = (
        select(StockDisposal)
        .where(StockDisposal.company_id == company_id)
        .options(
            joinedload(StockDisposal.location),
            joinedload(StockDisposal.product),
            joinedload(StockDisposal.brand),
            joinedload(StockDisposal.bag_type),
            joinedload(StockDisposal.customer),
        )
        .order_by(StockDisposal.operation_at.desc(), StockDisposal.id.desc())
    )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [serialize_stock_disposal(r) for r in rows]
    return StockDisposalPageOut(**page_dict(items, total, limit, offset))


@router.post("/stock-disposal", response_model=StockDisposalOut, status_code=201, dependencies=STOCK_DISPOSAL_WRITE)
def post_stock_disposal(
    body: StockDisposalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/operations/stock-disposal"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            record = create_stock_disposal(
            db,
            company_id=company_id_for_user(user),
            location_id=body.location_id,
            product_id=body.product_id,
            brand_id=body.brand_id,
            bag_type_id=body.bag_type_id,
            bag_count=body.bag_count,
            loose_kg=body.loose_kg,
            reason=body.reason,
            notes=body.notes,
            owner_type=body.owner_type,
            customer_id=body.customer_id,
        )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = serialize_stock_disposal(record)
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/stock-disposal/{record_id}/void", response_model=StockDisposalOut)
def void_stock_disposal_endpoint(
    record_id: int,
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/operations/stock-disposal/{record_id}/void"
    request_hash = hash_empty_body()

    def execute():
        require_for_company(
            db, StockDisposal, record_id, company_id_for_user(user), label="Stock disposal"
        )
        try:
            record = void_stock_disposal(db, record_id, actor=user)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = serialize_stock_disposal(record)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


def _batch_payload(body: ProcessingBatchSubmit) -> dict:
    return {
        "input_lines": [line.model_dump() for line in body.input_lines],
        "output_lines": [line.model_dump() for line in body.output_lines],
        "balance_return_lines": [line.model_dump() for line in body.balance_return_lines],
        "dust_kg": body.dust_kg,
        "stone_kg": body.stone_kg,
        "sack_weight_waste_kg": body.sack_weight_waste_kg,
        "powder_kg": body.powder_kg,
        "powder_line": body.powder_line.model_dump() if body.powder_line else None,
        "miscellaneous_waste_kg": body.miscellaneous_waste_kg,
        "output_allocation_mode": body.output_allocation_mode,
        "single_allocation_owner_type": body.single_allocation_owner_type,
        "single_allocation_customer_id": body.single_allocation_customer_id,
    }


@router.get("/processing", response_model=ProcessingJobPageOut, dependencies=PROCESSING_VIEW)
def get_processing_jobs(
    status: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if status is not None and status not in ("open", "completed"):
        raise HTTPException(status_code=400, detail="Invalid status")
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    company_id = company_id_for_user(user)
    order_by = (
        (ProcessingJob.completed_at.desc(), ProcessingJob.id.desc())
        if status == "completed"
        else (ProcessingJob.opened_at.desc(), ProcessingJob.id.desc())
    )
    q = (
        select(ProcessingJob)
        .where(ProcessingJob.company_id == company_id)
        .options(
            joinedload(ProcessingJob.input_product),
            joinedload(ProcessingJob.input_brand),
        )
        .order_by(*order_by)
    )
    if status is not None:
        q = q.where(ProcessingJob.status == ProcessingJobStatus(status))
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    summaries = fetch_processing_list_summaries(db, [r.id for r in rows])
    items = [
        serialize_processing_job_list_item(r, db, summary=summaries.get(r.id))
        for r in rows
    ]
    return ProcessingJobPageOut(**page_dict(items, total, limit, offset))


@router.post("/processing", response_model=ProcessingJobOut, status_code=201, dependencies=PROCESSING_MANAGE)
def post_processing_job(
    body: ProcessingJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/operations/processing"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            job = create_job(
            db,
            company_id=company_id_for_user(user),
            input_product_id=body.input_product_id,
            input_brand_id=body.input_brand_id,
        )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out = serialize_processing_job(job, db=db)
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.get("/processing/{job_id}", response_model=ProcessingJobOut, dependencies=PROCESSING_VIEW)
def get_processing_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        job = load_processing_job(db, job_id, company_id=company_id_for_user(user))
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return serialize_processing_job(job, db=db)


@router.post("/processing/{job_id}/batches", response_model=ProcessingJobOut, dependencies=PROCESSING_MANAGE)
def post_processing_batch(
    job_id: int,
    body: ProcessingBatchSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = f"POST /api/operations/processing/{job_id}/batches"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            job = submit_batch(
                db, job_id, company_id=company_id_for_user(user), **_batch_payload(body)
            )
        except ValueError as e:
            msg = str(e)
            raise HTTPException(404 if "not found" in msg.lower() else 400, msg) from e
        out = serialize_processing_job(job, db=db)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/processing/{job_id}/complete", response_model=ProcessingJobOut, dependencies=PROCESSING_MANAGE)
def post_processing_complete(
    job_id: int,
    body: ProcessingBatchSubmit,
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/operations/processing/{job_id}/complete"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            job = complete_job(
                db, job_id, company_id=company_id_for_user(user), **_batch_payload(body)
            )
        except ValueError as e:
            msg = str(e)
            raise HTTPException(404 if "not found" in msg.lower() else 400, msg) from e
        out = serialize_processing_job(job, db=db)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/processing/batches/{batch_id}/void", response_model=ProcessingJobOut)
def void_processing_batch_endpoint(
    batch_id: int,
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/operations/processing/batches/{batch_id}/void"
    request_hash = hash_empty_body()

    def execute():
        try:
            job = void_processing_batch(
                db, batch_id, actor=user, company_id=company_id_for_user(user)
            )
        except ValueError as e:
            msg = str(e)
            raise HTTPException(404 if "not found" in msg.lower() else 400, msg) from e
        out = serialize_processing_job(job, db=db)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)
