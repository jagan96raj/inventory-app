from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.auth import get_current_user
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.permissions import Permission, require_permission, require_void_user
from app.core.void_auth import VOID_AUTH_HEADER, verify_void_authorization
from app.core.pagination import (
    DEFAULT_LIMIT,
    clamp_limit,
    clamp_offset,
    paginate_select,
)
from app.database import get_db
from app.models.entities import (
    BagType,
    Bill,
    BillLine,
    BillStatus,
    BillType,
    Customer,
    DeliveryStatus,
    PaymentStatus,
    User,
)
from app.services.idempotency import hash_empty_body, hash_pydantic_body
from app.utils.time import business_today
from app.schemas import (
    BillEditFinalized,
    BillFinalizeCreate,
    BillLineIn,
    BillLineOut,
    BillListItemOut,
    BillOut,
    BillPickerItemOut,
    BillPickerPageOut,
    BillsListSummaryOut,
    BillsPageOut,
    BillVoidLinkedInfoOut,
    CashBookEntryOut,
    CashBookEntryPageOut,
)
from app.services.accounts import (
    count_active_linked_entries,
    list_linked_cash_book_entries_query,
)
from app.services.cash_book import serialize_entry
from app.services.bills import (
    apply_balance_on_edit_replace,
    bags_delivered_count,
    finalize_bill,
    load_bill,
    next_bill_number,
    preview_bill_number,
    recalc_bill_totals,
    recalc_delivery_status_after_edit,
    recalc_line,
    validate_edit_bill,
    bill_void_blockers,
    void_bill,
)
from app.services.fulfillment import net_fulfilled_kg
from app.services.bill_lock import lock_bill_for_update
from app.services.bill_concurrency import (
    assert_bill_version,
    bump_bill_version,
    EXPECTED_BILL_VERSION_HEADER,
    http_exception_for_value_error,
)
from app.services.payments import opposite_bills_due_total, update_bill_payment_status
from app.routers.payments import payment_to_out
from app.utils import validate_bags_loose

router = APIRouter(
    tags=["bills"],
    dependencies=[Depends(require_permission(Permission.BILLS_MANAGE))],
)


def line_to_out(line: BillLine, bill_type: BillType) -> BillLineOut:
    net = net_fulfilled_kg(line, bill_type)
    remaining = line.ordered_quantity_kg - net
    return BillLineOut(
        id=line.id,
        product_id=line.product_id,
        brand_id=line.brand_id,
        bag_type_id=line.bag_type_id,
        ordered_bags=line.ordered_bags,
        ordered_loose_kg=line.ordered_loose_kg,
        ordered_quantity_kg=line.ordered_quantity_kg,
        rate_per_kg=line.rate_per_kg,
        line_total=line.line_total,
        line_delivery_status=line.line_delivery_status.value,
        net_delivered_kg=line.net_delivered_kg,
        net_received_kg=line.net_received_kg,
        net_returned_kg=line.net_returned_kg,
        bags_purchased=line.ordered_bags if bill_type == BillType.purchase else None,
        bags_sold=line.ordered_bags if bill_type == BillType.sales else None,
        bags_delivered=bags_delivered_count(line, bill_type),
        quantity_kg=line.ordered_quantity_kg,
        delivered_quantity_kg=net,
        product_name=line.product.product_name if line.product else None,
        brand_name=line.brand.name if line.brand else None,
        bag_type_name=line.bag_type.name if line.bag_type else None,
        is_loose=line.bag_type.is_loose if line.bag_type else None,
        remaining_kg=remaining,
    )


def _unique_bill_lines(bill: Bill) -> list[BillLine]:
    seen: set[int] = set()
    out: list[BillLine] = []
    for ln in bill.lines:
        if ln.id in seen:
            continue
        seen.add(ln.id)
        out.append(ln)
    return out


def bill_list_item_to_out(bill: Bill) -> BillListItemOut:
    due = bill.grand_total - bill.amount_paid
    return BillListItemOut(
        id=bill.id,
        bill_number=bill.bill_number,
        bill_type=bill.bill_type,
        bill_date=bill.bill_date,
        customer_id=bill.customer_id,
        customer_name=bill.customer.name if bill.customer else None,
        location_id=bill.location_id,
        location_name=bill.location.name if bill.location else None,
        grand_total=bill.grand_total,
        final_payable=bill.grand_total,
        amount_paid=bill.amount_paid,
        amount_due=due,
        due_amount=due,
        payment_status=bill.payment_status.value,
        order_delivery_status=bill.order_delivery_status.value,
        version=bill.version,
    )


def _apply_bill_list_filters(
    q,
    *,
    bill_type: BillType | None,
    payment_status: str | None,
    delivery_status: str | None,
    search: str | None,
):
    q = q.where(Bill.status == BillStatus.finalized)
    if bill_type is not None:
        q = q.where(Bill.bill_type == bill_type)
    if payment_status:
        q = q.where(Bill.payment_status == PaymentStatus(payment_status))
    if delivery_status:
        q = q.where(Bill.order_delivery_status == DeliveryStatus(delivery_status))
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.outerjoin(Customer, Bill.customer_id == Customer.id).where(
            or_(
                func.lower(Bill.bill_number).like(term),
                func.lower(Customer.name).like(term),
            )
        )
    return q


def _bills_list_summary(db: Session, base_q) -> BillsListSummaryOut:
    agg_q = base_q.with_only_columns(
        Bill.payment_status,
        Bill.order_delivery_status,
        Bill.grand_total,
        Bill.amount_paid,
    )
    sub = agg_q.subquery()
    due_expr = sub.c.grand_total - sub.c.amount_paid
    row = db.execute(
        select(
            func.count(),
            func.sum(case((sub.c.payment_status != PaymentStatus.paid, 1), else_=0)),
            func.coalesce(
                func.sum(case((due_expr > 0, due_expr), else_=0)),
                0,
            ),
            func.sum(case((sub.c.order_delivery_status != DeliveryStatus.delivered, 1), else_=0)),
        ).select_from(sub)
    ).one()
    return BillsListSummaryOut(
        total_count=int(row[0] or 0),
        unpaid_count=int(row[1] or 0),
        total_due=Decimal(str(row[2] or 0)),
        pending_delivery_count=int(row[3] or 0),
    )


def bill_to_out(bill: Bill, db: Session | None = None, *, include_payments: bool = False) -> BillOut:
    lines = _unique_bill_lines(bill)
    due = bill.grand_total - bill.amount_paid
    payment_rows = []
    if include_payments:
        payment_rows = sorted(
            [payment_to_out(p, bill) for p in bill.payments],
            key=lambda row: row.paid_at,
        )
    return BillOut(
        id=bill.id,
        bill_number=bill.bill_number,
        bill_type=bill.bill_type,
        status=bill.status.value,
        bill_date=bill.bill_date,
        customer_id=bill.customer_id,
        location_id=bill.location_id,
        discount_percent=bill.discount_percent,
        discount_amount=bill.discount_amount,
        adjustment=bill.adjustment,
        total_amount=bill.subtotal,
        final_payable=bill.grand_total,
        subtotal=bill.subtotal,
        grand_total=bill.grand_total,
        amount_paid=bill.amount_paid,
        payment_status=bill.payment_status.value,
        order_delivery_status=bill.order_delivery_status.value,
        version=bill.version,
        customer_name=bill.customer.name if bill.customer else None,
        customer_address_line=bill.customer.address_line if bill.customer else None,
        customer_district=bill.customer.district if bill.customer else None,
        customer_state=bill.customer.state if bill.customer else None,
        customer_pin_code=bill.customer.pin_code if bill.customer else None,
        customer_phone=bill.customer.phone if bill.customer else None,
        location_name=bill.location.name if bill.location else None,
        lines=[line_to_out(ln, bill.bill_type) for ln in lines],
        due_amount=due,
        amount_due=due,
        customer_credit_balance=bill.customer.credit_balance if bill.customer else None,
        customer_debit_balance=bill.customer.debit_balance if bill.customer else None,
        opposite_due_total=(
            opposite_bills_due_total(db, bill.customer_id, bill.bill_type)
            if db is not None and bill.customer_id
            else None
        ),
        payments=payment_rows,
    )


def validate_lines(db: Session, bill: Bill, lines_in: list[BillLineIn]) -> None:
    seen: set[tuple[int, int, int]] = set()
    for li in lines_in:
        key = (li.product_id, li.brand_id, li.bag_type_id)
        if key in seen:
            raise HTTPException(400, "Duplicate line: same product, brand, and bag type on this bill")
        seen.add(key)


def build_lines(db: Session, bill: Bill, lines_in: list[BillLineIn]) -> None:
    if lines_in:
        validate_lines(db, bill, lines_in)
    if bill.id:
        db.execute(delete(BillLine).where(BillLine.bill_id == bill.id))
        db.flush()
    bill.lines.clear()
    for li in lines_in:
        bt = db.get(BagType, li.bag_type_id)
        if not bt:
            raise HTTPException(400, f"Invalid bag type {li.bag_type_id}")
        try:
            validate_bags_loose(bt, li.ordered_bags, li.ordered_loose_kg)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        line = BillLine(
            bill=bill,
            product_id=li.product_id,
            brand_id=li.brand_id,
            bag_type_id=li.bag_type_id,
            ordered_bags=li.ordered_bags,
            ordered_loose_kg=li.ordered_loose_kg,
            rate_per_kg=li.rate_per_kg,
            stock_source=li.stock_source,
            job_work_order_id=li.job_work_order_id,
            line_charge_type=li.line_charge_type,
        )
        recalc_line(line, bt)
        bill.lines.append(line)
    if lines_in:
        db.flush()


@router.get("/bills/next-number")
def preview_next_bill_number(bill_type: BillType, db: Session = Depends(get_db)):
    return {"bill_number": preview_bill_number(db, bill_type)}


@router.get("/bills/picker", response_model=BillPickerPageOut)
def bills_picker(
    search: str | None = None,
    bill_type: BillType | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Lightweight bills listing for the cash-book link picker."""
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = (
        select(Bill)
        .options(joinedload(Bill.customer))
        .where(Bill.status == BillStatus.finalized)
        .order_by(Bill.id.desc())
    )
    if bill_type is not None:
        q = q.where(Bill.bill_type == bill_type)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.outerjoin(Customer, Bill.customer_id == Customer.id).where(
            or_(
                func.lower(Bill.bill_number).like(term),
                func.lower(Customer.name).like(term),
            )
        )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [
        BillPickerItemOut(
            id=b.id,
            bill_number=b.bill_number,
            bill_type=b.bill_type,
            customer_id=b.customer_id,
            customer_name=b.customer.name if b.customer else None,
            bill_date=b.bill_date,
            grand_total=b.grand_total,
        )
        for b in rows
    ]
    return BillPickerPageOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/bills", response_model=BillsPageOut)
def list_bills(
    bill_type: BillType | None = None,
    payment_status: str | None = None,
    delivery_status: str | None = None,
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    if payment_status is not None and payment_status not in ("unpaid", "partial", "paid"):
        raise HTTPException(400, "Invalid payment_status")
    if delivery_status is not None and delivery_status not in ("not_delivered", "partial", "delivered"):
        raise HTTPException(400, "Invalid delivery_status")
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)

    base_q = _apply_bill_list_filters(
        select(Bill),
        bill_type=bill_type,
        payment_status=payment_status,
        delivery_status=delivery_status,
        search=search,
    )
    summary = _bills_list_summary(db, base_q)

    items_q = _apply_bill_list_filters(
        select(Bill).options(
            joinedload(Bill.customer),
            joinedload(Bill.location),
        ),
        bill_type=bill_type,
        payment_status=payment_status,
        delivery_status=delivery_status,
        search=search,
    ).order_by(Bill.id.desc())

    bills, total = paginate_select(db, items_q, limit=limit, offset=offset)
    items = [bill_list_item_to_out(b) for b in bills]
    return BillsPageOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        summary=summary,
    )


@router.get("/bills/{bid}", response_model=BillOut)
def get_bill(bid: int, db: Session = Depends(get_db)):
    bill = load_bill(db, bid)
    if not bill:
        raise HTTPException(404, "Not found")
    return bill_to_out(bill, db, include_payments=True)


@router.post("/bills", response_model=BillOut, status_code=201)
def create_finalized_bill(
    body: BillFinalizeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/bills"
    request_hash = hash_pydantic_body(body)

    def execute():
        bill = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                bill = Bill(
                    bill_number=next_bill_number(db, body.bill_type),
                    bill_type=body.bill_type,
                    bill_date=body.bill_date if body.bill_date is not None else business_today(),
                    customer_id=body.customer_id,
                    location_id=body.location_id if body.bill_type == BillType.sales else None,
                    discount_percent=body.discount_percent,
                    adjustment=body.adjustment,
                )
                db.add(bill)
                db.flush()
                build_lines(db, bill, body.lines)
                db.flush()
                finalize_bill(db, bill)
                break
            except ValueError as e:
                db.rollback()
                raise HTTPException(400, str(e)) from e
            except HTTPException:
                db.rollback()
                raise
            except IntegrityError as e:
                db.rollback()
                last_error = e
                if attempt == 2:
                    raise HTTPException(500, "Bill submit failed: duplicate bill number") from e
                continue
            except Exception as e:
                db.rollback()
                raise HTTPException(500, f"Bill submit failed: {e}") from e
        else:
            raise HTTPException(500, f"Bill submit failed: {last_error}") from last_error

        bill = load_bill(db, bill.id)
        out = bill_to_out(bill, db)
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.patch("/bills/{bid}", response_model=BillOut)
def edit_finalized_bill(
    bid: int,
    body: BillEditFinalized,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = f"PATCH /api/bills/{bid}"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            locked = lock_bill_for_update(db, bid)
        except ValueError as e:
            raise http_exception_for_value_error(e) from e
        if not locked:
            raise HTTPException(404, "Not found")
        try:
            assert_bill_version(locked, body.expected_version)
        except ValueError as e:
            raise http_exception_for_value_error(e) from e
        bill = load_bill(db, bid)
        if not bill:
            raise HTTPException(404, "Not found")
        if bill.status == BillStatus.voided:
            raise HTTPException(400, "Cannot edit a voided bill")
        if bill.status != BillStatus.finalized:
            raise HTTPException(400, "Only finalized bills can be edited")

        customer = bill.customer
        if not customer:
            raise HTTPException(400, "Customer not found")

        try:
            previous_grand_total = bill.grand_total

            if body.discount_percent is not None:
                if body.discount_percent < 0 or body.discount_percent > 100:
                    raise HTTPException(400, "discount_percent must be 0-100")
                bill.discount_percent = body.discount_percent
            if body.adjustment is not None:
                bill.adjustment = body.adjustment

            if body.lines:
                line_map = {ln.id: ln for ln in _unique_bill_lines(bill)}
                for item in body.lines:
                    line = line_map.get(item.id)
                    if not line:
                        raise HTTPException(400, f"Line {item.id} not found on this bill")
                    bt = line.bag_type
                    if not bt:
                        raise HTTPException(400, f"Bag type missing on line {item.id}")
                    if item.rate_per_kg is not None:
                        if item.rate_per_kg < 0:
                            raise HTTPException(400, "rate_per_kg must be >= 0")
                        line.rate_per_kg = item.rate_per_kg
                    new_bags = line.ordered_bags if item.ordered_bags is None else item.ordered_bags
                    new_loose = line.ordered_loose_kg if item.ordered_loose_kg is None else item.ordered_loose_kg
                    validate_bags_loose(bt, new_bags, new_loose)
                    line.ordered_bags = new_bags
                    line.ordered_loose_kg = new_loose
                    recalc_line(line, bt)

            recalc_bill_totals(db, bill)
            db_lines = _unique_bill_lines(bill)
            validate_edit_bill(bill, db_lines)
            apply_balance_on_edit_replace(db, customer, bill, previous_grand_total)
            recalc_delivery_status_after_edit(db, bill, db_lines)
            update_bill_payment_status(bill)
            bump_bill_version(bill)
            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except ValueError as e:
            db.rollback()
            raise http_exception_for_value_error(e) from e
        except Exception as e:
            db.rollback()
            raise HTTPException(500, f"Bill edit failed: {e}") from e

        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        bill_after = load_bill(db, bid)
        if bill_after:
            record_audit_event(
                db,
                user=user,
                action=AuditAction.BILL_EDITED,
                entity_type=AuditEntityType.BILL,
                entity_id=bill_after.id,
                entity_label=bill_after.bill_number,
            )

        bill = bill_after
        out = bill_to_out(bill, db)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.get("/bills/{bid}/linked-entries", response_model=CashBookEntryPageOut)
def list_bill_linked_entries(
    bid: int,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Spec v12.21 — paginated cash book entries linked to this bill."""
    bill = db.get(Bill, bid)
    if not bill:
        raise HTTPException(404, "Bill not found")
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = list_linked_cash_book_entries_query(db, bid)
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [CashBookEntryOut.model_validate(serialize_entry(r)) for r in rows]
    return CashBookEntryPageOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/bills/{bid}/void-precheck", response_model=BillVoidLinkedInfoOut)
def bill_void_precheck(bid: int, db: Session = Depends(get_db)):
    """Spec v15.9 — preflight for voiding a bill: eligibility + linked cash book entries."""
    bill = db.get(Bill, bid)
    if not bill:
        raise HTTPException(404, "Bill not found")
    count, total_amount = count_active_linked_entries(db, bid)
    block_reasons = bill_void_blockers(db, bill)
    return BillVoidLinkedInfoOut(
        bill_id=bid,
        can_void=len(block_reasons) == 0,
        block_reasons=block_reasons,
        linked_active_entries_count=count,
        linked_active_entries_amount=total_amount,
    )


@router.post("/bills/{bid}/void", response_model=BillOut)
def void_bill_endpoint(
    bid: int,
    expected_bill_version: int | None = Header(None, alias=EXPECTED_BILL_VERSION_HEADER),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/bills/{bid}/void"
    request_hash = hash_empty_body()

    def execute():
        try:
            bill = void_bill(db, bid, expected_version=expected_bill_version, actor=user)
        except ValueError as e:
            raise http_exception_for_value_error(e) from e
        out = bill_to_out(load_bill(db, bill.id), db, include_payments=True)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)
