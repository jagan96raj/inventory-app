"""Spec v14.0 — Job Work orders (receive for processing)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    BagType,
    BillLine,
    Customer,
    Inventory,
    InventoryOwnerType,
    JobWorkLine,
    JobWorkOrder,
    JobWorkOrderStatus,
    JobWorkReceipt,
    JobWorkReceiptEntryType,
    JWNumberCounter,
    ProcessingInputLine,
    User,
)
from app.services.operations import add_inventory, prune_zero_inventory, subtract_inventory
from app.utils import calc_quantity_kg, recalc_inventory_row, validate_bags_loose
from app.utils.time import resolve_business_entry, utc_now

JW_ALREADY_VOIDED_MSG = "Receipt already voided"
JW_ORDER_NOT_OPEN_MSG = "Job work order is not open"
JW_ORDER_ALREADY_CANCELLED_MSG = "Job work order already cancelled"
JW_VOID_CUSTODY_MSG = (
    "Cannot void job work order while material is still received — return to customer first"
)
JW_VOID_LINKED_MSG = "Cannot void job work order linked to bills or processing"
JW_RETURN_LOCATION_MSG = "Return must be from a location where material was received"
JW_VOID_RETURN_MSG = "Return events cannot be voided"


def _jw_line_progress(line: JobWorkLine, bt: BagType | None) -> dict:
    """Bags/loose remainders for bagged vs loose lines (receive + custody)."""
    is_loose = bool(bt and bt.is_loose)
    # Returns undo progress toward the order — still need to receive returned qty again.
    remaining_receive_kg = max(
        line.ordered_quantity_kg - line.received_quantity_kg + line.returned_quantity_kg,
        Decimal("0"),
    )
    custody_kg = max(line.received_quantity_kg - line.returned_quantity_kg, Decimal("0"))
    if is_loose:
        remaining_receive_bags = 0
        remaining_receive_loose_kg = max(
            line.ordered_loose_kg - line.received_loose_kg + line.returned_loose_kg,
            Decimal("0"),
        )
        custody_bags = 0
        custody_loose_kg = max(line.received_loose_kg - line.returned_loose_kg, Decimal("0"))
    else:
        remaining_receive_bags = max(
            line.ordered_bags - line.received_bags + line.returned_bags,
            0,
        )
        remaining_receive_loose_kg = Decimal("0")
        custody_bags = max(line.received_bags - line.returned_bags, 0)
        custody_loose_kg = Decimal("0")
        if bt and bt.weight_per_bag_kg > 0:
            weight = bt.weight_per_bag_kg
            if line.ordered_bags == 0 and line.ordered_quantity_kg > 0:
                ordered_bags_eff = int(line.ordered_quantity_kg / weight)
                received_bags_eff = int(line.received_quantity_kg / weight)
                returned_bags_eff = line.returned_bags
                remaining_receive_bags = max(
                    ordered_bags_eff - received_bags_eff + returned_bags_eff,
                    0,
                )
                custody_bags = max(received_bags_eff - returned_bags_eff, 0)
            else:
                if remaining_receive_bags == 0 and remaining_receive_kg > 0:
                    remaining_receive_bags = int(remaining_receive_kg / weight)
                if custody_bags == 0 and custody_kg > 0:
                    custody_bags = int(custody_kg / weight)
    net_received_kg = max(line.received_quantity_kg - line.returned_quantity_kg, Decimal("0"))
    net_received_bags = max(line.received_bags - line.returned_bags, 0)
    if is_loose:
        net_received_loose_kg = net_received_kg
    else:
        net_received_loose_kg = Decimal("0")
    return {
        "is_loose": is_loose,
        "remaining_receive_kg": remaining_receive_kg,
        "remaining_receive_bags": remaining_receive_bags,
        "remaining_receive_loose_kg": remaining_receive_loose_kg,
        "custody_kg": custody_kg,
        "custody_bags": custody_bags,
        "custody_loose_kg": custody_loose_kg,
        "net_received_kg": net_received_kg,
        "net_received_bags": net_received_bags,
        "net_received_loose_kg": net_received_loose_kg,
    }


def _jw_line_has_remaining_receive(progress: dict) -> bool:
    if progress["is_loose"]:
        return progress["remaining_receive_loose_kg"] > 0
    if progress["remaining_receive_bags"] > 0:
        return True
    return progress["remaining_receive_kg"] > 0


def _jw_line_has_custody(progress: dict) -> bool:
    if progress["is_loose"]:
        return progress["custody_loose_kg"] > 0
    if progress["custody_bags"] > 0:
        return True
    return progress["custody_kg"] > 0


def _jw_line_is_actionable(progress: dict) -> bool:
    return _jw_line_has_remaining_receive(progress) or _jw_line_has_custody(progress)


def _jw_return_locations(
    db: Session, line: JobWorkLine, order: JobWorkOrder, bt: BagType | None
) -> list[dict]:
    """Locations with job-work custody stock from active receipts only."""
    is_loose = bool(bt and bt.is_loose)
    seen: set[int] = set()
    result: list[dict] = []
    for receipt in sorted(line.receipts or [], key=lambda r: (r.received_at, r.id)):
        if receipt.voided_at is not None:
            continue
        if receipt.entry_type != JobWorkReceiptEntryType.receive:
            continue
        if receipt.location_id in seen:
            continue
        seen.add(receipt.location_id)
        inv = db.scalar(
            select(Inventory).where(
                Inventory.product_id == line.product_id,
                Inventory.brand_id == line.brand_id,
                Inventory.location_id == receipt.location_id,
                Inventory.bag_type_id == line.bag_type_id,
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.customer_id == order.customer_id,
            )
        )
        if not inv or inv.total_quantity_kg <= 0:
            continue
        result.append(
            {
                "location_id": receipt.location_id,
                "location_name": receipt.location.name if receipt.location else None,
                "returnable_bags": 0 if is_loose else inv.bag_count,
                "returnable_loose_kg": inv.loose_kg if is_loose else Decimal("0"),
                "returnable_kg": inv.total_quantity_kg,
            }
        )
    return result


def _format_job_number(seq: int) -> str:
    return f"JW-{seq:06d}"


def _get_jw_counter_for_update(db: Session) -> JWNumberCounter:
    row = db.scalar(select(JWNumberCounter).where(JWNumberCounter.id == 1).with_for_update())
    if row:
        return row
    try:
        with db.begin_nested():
            row = JWNumberCounter(id=1, last_number=0)
            db.add(row)
            db.flush()
    except IntegrityError:
        pass
    row = db.scalar(select(JWNumberCounter).where(JWNumberCounter.id == 1).with_for_update())
    if not row:
        raise ValueError("Could not initialize JW number counter")
    return row


def preview_job_number(db: Session) -> str:
    row = db.scalar(select(JWNumberCounter).where(JWNumberCounter.id == 1))
    next_seq = (row.last_number + 1) if row else 1
    return _format_job_number(next_seq)


def next_job_number(db: Session) -> str:
    counter = _get_jw_counter_for_update(db)
    counter.last_number += 1
    db.flush()
    return _format_job_number(counter.last_number)


def _load_order_options():
    return (
        joinedload(JobWorkOrder.customer),
        joinedload(JobWorkOrder.lines).joinedload(JobWorkLine.product),
        joinedload(JobWorkOrder.lines).joinedload(JobWorkLine.brand),
        joinedload(JobWorkOrder.lines).joinedload(JobWorkLine.bag_type),
        joinedload(JobWorkOrder.lines)
        .joinedload(JobWorkLine.receipts)
        .joinedload(JobWorkReceipt.location),
    )


def load_job_work_order(db: Session, order_id: int) -> JobWorkOrder:
    row = db.scalar(
        select(JobWorkOrder).where(JobWorkOrder.id == order_id).options(*_load_order_options())
    )
    if not row:
        raise ValueError("Job work order not found")
    return row


def create_job_work_order(
    db: Session,
    *,
    customer_id: int,
    job_date: date,
    notes: str | None,
    lines: list[dict],
) -> JobWorkOrder:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise ValueError("Customer not found")
    if not lines:
        raise ValueError("At least one line is required")

    order = JobWorkOrder(
        job_number=next_job_number(db),
        customer_id=customer_id,
        job_date=job_date,
        notes=notes,
        status=JobWorkOrderStatus.open,
    )
    db.add(order)
    db.flush()

    for idx, line_in in enumerate(lines):
        bt = db.get(BagType, line_in["bag_type_id"])
        if not bt:
            raise ValueError("Invalid bag type")
        bags = line_in["ordered_bags"]
        loose = Decimal(str(line_in["ordered_loose_kg"]))
        validate_bags_loose(bt, bags, loose)
        qty = calc_quantity_kg(bt, bags, loose)
        db.add(
            JobWorkLine(
                order_id=order.id,
                product_id=line_in["product_id"],
                brand_id=line_in["brand_id"],
                bag_type_id=line_in["bag_type_id"],
                ordered_bags=bags,
                ordered_loose_kg=loose,
                ordered_quantity_kg=qty,
                line_index=idx,
            )
        )
    db.commit()
    return load_job_work_order(db, order.id)


def _recalc_line_received(line: JobWorkLine, db: Session) -> None:
    total_bags = 0
    total_loose = Decimal("0")
    total_kg = Decimal("0")
    bt = line.bag_type or db.get(BagType, line.bag_type_id)
    for rcpt in line.receipts or []:
        if rcpt.voided_at is not None:
            continue
        if rcpt.entry_type != JobWorkReceiptEntryType.receive:
            continue
        total_bags += rcpt.bag_count
        total_loose += rcpt.loose_kg
        total_kg += rcpt.quantity_kg
    line.received_bags = total_bags
    line.received_loose_kg = total_loose
    line.received_quantity_kg = total_kg
    if bt and not bt.is_loose:
        line.received_loose_kg = Decimal("0")


def _recalc_line_returned(line: JobWorkLine, db: Session) -> None:
    total_bags = 0
    total_loose = Decimal("0")
    total_kg = Decimal("0")
    bt = line.bag_type or db.get(BagType, line.bag_type_id)
    for rcpt in line.receipts or []:
        if rcpt.entry_type != JobWorkReceiptEntryType.return_:
            continue
        total_bags += rcpt.bag_count
        total_loose += rcpt.loose_kg
        total_kg += rcpt.quantity_kg
    line.returned_bags = total_bags
    line.returned_loose_kg = total_loose
    line.returned_quantity_kg = total_kg
    if bt and not bt.is_loose:
        line.returned_loose_kg = Decimal("0")


def _recalc_line_aggregates(line: JobWorkLine, db: Session) -> None:
    _recalc_line_received(line, db)
    _recalc_line_returned(line, db)


def _sort_receipts_newest_first(receipts: list[JobWorkReceipt]) -> list[JobWorkReceipt]:
    return sorted(receipts or [], key=lambda r: (r.received_at, r.id), reverse=True)


def receive_job_work(
    db: Session,
    *,
    line_id: int,
    location_id: int,
    bag_count: int,
    loose_kg: Decimal,
    vehicle_no: str | None = None,
    notes: str | None = None,
    received_date: date | None = None,
) -> JobWorkReceipt:
    line = db.scalar(
        select(JobWorkLine)
        .where(JobWorkLine.id == line_id)
        .options(
            joinedload(JobWorkLine.order),
            joinedload(JobWorkLine.bag_type),
            joinedload(JobWorkLine.receipts),
        )
        .with_for_update(of=JobWorkLine)
    )
    if not line or not line.order:
        raise ValueError("Job work line not found")
    if line.order.status != JobWorkOrderStatus.open:
        raise ValueError(JW_ORDER_NOT_OPEN_MSG)

    bt = line.bag_type
    if not bt:
        raise ValueError("Invalid bag type")
    validate_bags_loose(bt, bag_count, loose_kg)
    qty = calc_quantity_kg(bt, bag_count, loose_kg)
    if qty <= 0:
        raise ValueError("Receive quantity must be positive")

    add_inventory(
        db,
        line.product_id,
        line.brand_id,
        location_id,
        line.bag_type_id,
        bag_count,
        loose_kg,
        owner_type=InventoryOwnerType.job_work,
        customer_id=line.order.customer_id,
    )

    _, received_at = resolve_business_entry(received_date)

    receipt = JobWorkReceipt(
        line_id=line.id,
        location_id=location_id,
        bag_count=bag_count,
        loose_kg=loose_kg,
        quantity_kg=qty,
        vehicle_no=vehicle_no,
        notes=notes,
        entry_type=JobWorkReceiptEntryType.receive,
        received_at=received_at,
    )
    db.add(receipt)
    db.flush()
    if line.receipts is None:
        line.receipts = []
    line.receipts.append(receipt)
    _recalc_line_received(line, db)
    db.commit()
    db.refresh(receipt)
    return receipt


def void_job_work_receipt(db: Session, receipt_id: int, *, actor: User | None = None) -> JobWorkReceipt:
    receipt = db.scalar(
        select(JobWorkReceipt)
        .where(JobWorkReceipt.id == receipt_id)
        .options(
            joinedload(JobWorkReceipt.line).joinedload(JobWorkLine.order),
            joinedload(JobWorkReceipt.line).joinedload(JobWorkLine.bag_type),
            joinedload(JobWorkReceipt.line).joinedload(JobWorkLine.receipts),
        )
        .with_for_update(of=JobWorkReceipt)
    )
    if not receipt:
        raise ValueError("Receipt not found")
    if receipt.voided_at is not None:
        raise ValueError(JW_ALREADY_VOIDED_MSG)
    if receipt.entry_type != JobWorkReceiptEntryType.receive:
        raise ValueError(JW_VOID_RETURN_MSG)

    line = receipt.line
    if not line or not line.order:
        raise ValueError("Job work line not found")

    subtract_inventory(
        db,
        line.product_id,
        line.brand_id,
        receipt.location_id,
        line.bag_type_id,
        receipt.bag_count,
        receipt.loose_kg,
        owner_type=InventoryOwnerType.job_work,
        customer_id=line.order.customer_id,
    )

    receipt.voided_at = utc_now()
    _recalc_line_received(line, db)
    db.commit()
    db.refresh(receipt)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.JOB_WORK_RECEIPT_VOIDED,
            entity_type=AuditEntityType.JOB_WORK_RECEIPT,
            entity_id=receipt.id,
            entity_label=f"JW receipt #{receipt.id}",
            metadata={"order_id": line.order.id, "job_number": line.order.job_number},
        )
    return receipt


def _order_has_custody(order: JobWorkOrder) -> bool:
    for ln in order.lines or []:
        if _jw_line_has_custody(_jw_line_progress(ln, ln.bag_type)):
            return True
    return False


def _order_has_activity_links(db: Session, order_id: int) -> bool:
    if db.scalar(select(BillLine.id).where(BillLine.job_work_order_id == order_id).limit(1)):
        return True
    return bool(
        db.scalar(
            select(ProcessingInputLine.id)
            .where(ProcessingInputLine.job_work_order_id == order_id)
            .limit(1)
        )
    )


def void_job_work_order(db: Session, order_id: int, *, actor: User | None = None) -> JobWorkOrder:
    order = db.scalar(
        select(JobWorkOrder)
        .where(JobWorkOrder.id == order_id)
        .options(*_load_order_options())
        .with_for_update(of=JobWorkOrder)
    )
    if not order:
        raise ValueError("Job work order not found")
    if order.status == JobWorkOrderStatus.cancelled:
        raise ValueError(JW_ORDER_ALREADY_CANCELLED_MSG)
    if order.status != JobWorkOrderStatus.open:
        raise ValueError(JW_ORDER_NOT_OPEN_MSG)
    if _order_has_custody(order):
        raise ValueError(JW_VOID_CUSTODY_MSG)
    if _order_has_activity_links(db, order.id):
        raise ValueError(JW_VOID_LINKED_MSG)

    order.status = JobWorkOrderStatus.cancelled
    order.version += 1
    db.commit()
    result = load_job_work_order(db, order.id)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.JOB_WORK_ORDER_VOIDED,
            entity_type=AuditEntityType.JOB_WORK_ORDER,
            entity_id=order.id,
            entity_label=order.job_number,
        )
    return result


def return_job_work_to_customer(
    db: Session,
    *,
    line_id: int,
    location_id: int,
    bag_count: int,
    loose_kg: Decimal,
    notes: str | None = None,
    received_date: date | None = None,
) -> JobWorkReceipt:
    line = db.scalar(
        select(JobWorkLine)
        .where(JobWorkLine.id == line_id)
        .options(
            joinedload(JobWorkLine.order),
            joinedload(JobWorkLine.bag_type),
            joinedload(JobWorkLine.receipts).joinedload(JobWorkReceipt.location),
        )
        .with_for_update(of=JobWorkLine)
    )
    if not line or not line.order:
        raise ValueError("Job work line not found")
    if line.order.status != JobWorkOrderStatus.open:
        raise ValueError(JW_ORDER_NOT_OPEN_MSG)

    bt = line.bag_type
    if not bt:
        raise ValueError("Invalid bag type")
    validate_bags_loose(bt, bag_count, loose_kg)
    qty = calc_quantity_kg(bt, bag_count, loose_kg)

    return_locations = _jw_return_locations(db, line, line.order, bt)
    allowed = next((loc for loc in return_locations if loc["location_id"] == location_id), None)
    if not allowed:
        raise ValueError(JW_RETURN_LOCATION_MSG)
    if bt.is_loose:
        if loose_kg > allowed["returnable_loose_kg"]:
            raise ValueError("Insufficient stock at this location")
    elif bag_count > allowed["returnable_bags"]:
        raise ValueError("Insufficient stock at this location")

    subtract_inventory(
        db,
        line.product_id,
        line.brand_id,
        location_id,
        line.bag_type_id,
        bag_count,
        loose_kg,
        owner_type=InventoryOwnerType.job_work,
        customer_id=line.order.customer_id,
    )

    _, received_at = resolve_business_entry(received_date)

    receipt = JobWorkReceipt(
        line_id=line.id,
        location_id=location_id,
        bag_count=bag_count,
        loose_kg=loose_kg,
        quantity_kg=qty,
        vehicle_no=None,
        notes=notes,
        entry_type=JobWorkReceiptEntryType.return_,
        received_at=received_at,
    )
    db.add(receipt)
    db.flush()
    if line.receipts is None:
        line.receipts = []
    line.receipts.append(receipt)
    _recalc_line_returned(line, db)
    db.commit()
    db.refresh(receipt)
    return receipt


def list_job_work_orders(
    db: Session,
    *,
    customer_id: int | None = None,
    status: JobWorkOrderStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[JobWorkOrder], int]:
    q = select(JobWorkOrder).options(
        joinedload(JobWorkOrder.customer),
        joinedload(JobWorkOrder.lines).joinedload(JobWorkLine.product),
    )
    if customer_id is not None:
        q = q.where(JobWorkOrder.customer_id == customer_id)
    if status is not None:
        q = q.where(JobWorkOrder.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (
        db.scalars(q.order_by(JobWorkOrder.job_date.desc(), JobWorkOrder.id.desc()).limit(limit).offset(offset))
        .unique()
        .all()
    )
    return list(rows), int(total)


def get_customer_job_work_statement(
    db: Session,
    customer_id: int,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise ValueError("Customer not found")

    q = select(JobWorkOrder).where(JobWorkOrder.customer_id == customer_id)
    if from_date:
        q = q.where(JobWorkOrder.job_date >= from_date)
    if to_date:
        q = q.where(JobWorkOrder.job_date <= to_date)
    orders = db.scalars(q.options(*_load_order_options())).unique().all()

    total_ordered_kg = Decimal("0")
    total_received_kg = Decimal("0")
    total_returned_kg = Decimal("0")
    order_rows = []
    for order in orders:
        ordered = sum((ln.ordered_quantity_kg for ln in order.lines), Decimal("0"))
        received = sum((ln.received_quantity_kg for ln in order.lines), Decimal("0"))
        returned = sum((ln.returned_quantity_kg for ln in order.lines), Decimal("0"))
        total_ordered_kg += ordered
        total_received_kg += received
        total_returned_kg += returned
        order_rows.append(
            {
                "job_work_order_id": order.id,
                "job_number": order.job_number,
                "job_date": order.job_date,
                "status": order.status.value,
                "ordered_quantity_kg": ordered,
                "received_quantity_kg": received,
                "returned_quantity_kg": returned,
                "outstanding_quantity_kg": received - returned,
            }
        )

    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "from_date": from_date,
        "to_date": to_date,
        "total_ordered_kg": total_ordered_kg,
        "total_received_kg": total_received_kg,
        "total_returned_kg": total_returned_kg,
        "outstanding_in_custody_kg": total_received_kg - total_returned_kg,
        "orders": order_rows,
    }


def _serialize_receipt_summary(receipt: JobWorkReceipt) -> dict:
    entry = receipt.entry_type.value if receipt.entry_type else "receive"
    return {
        "id": receipt.id,
        "line_id": receipt.line_id,
        "location_id": receipt.location_id,
        "location_name": receipt.location.name if receipt.location else None,
        "bag_count": receipt.bag_count,
        "loose_kg": receipt.loose_kg,
        "quantity_kg": receipt.quantity_kg,
        "vehicle_no": receipt.vehicle_no,
        "notes": receipt.notes,
        "entry_type": entry,
        "received_at": receipt.received_at,
        "voided_at": receipt.voided_at,
    }


def serialize_jw_fulfillment_line(line: JobWorkLine, order: JobWorkOrder, db: Session) -> dict:
    bt = line.bag_type
    progress = _jw_line_progress(line, bt)
    receipts = _sort_receipts_newest_first(line.receipts or [])
    return {
        "line_id": line.id,
        "order_id": order.id,
        "job_number": order.job_number,
        "customer_name": order.customer.name if order.customer else None,
        "product_id": line.product_id,
        "product_name": line.product.product_name if line.product else None,
        "brand_id": line.brand_id,
        "brand_name": line.brand.name if line.brand else None,
        "bag_type_id": line.bag_type_id,
        "bag_type_name": bt.name if bt else None,
        "weight_per_bag_kg": bt.weight_per_bag_kg if bt else None,
        "is_loose": progress["is_loose"],
        "ordered_bags": line.ordered_bags,
        "ordered_loose_kg": line.ordered_loose_kg,
        "received_bags": line.received_bags,
        "received_loose_kg": line.received_loose_kg,
        "returned_bags": line.returned_bags,
        "returned_loose_kg": line.returned_loose_kg,
        "ordered_kg": line.ordered_quantity_kg,
        "received_kg": line.received_quantity_kg,
        "returned_kg": line.returned_quantity_kg,
        "net_received_kg": progress["net_received_kg"],
        "net_received_bags": progress["net_received_bags"],
        "net_received_loose_kg": progress["net_received_loose_kg"],
        "remaining_receive_kg": progress["remaining_receive_kg"],
        "remaining_receive_bags": progress["remaining_receive_bags"],
        "remaining_receive_loose_kg": progress["remaining_receive_loose_kg"],
        "custody_kg": progress["custody_kg"],
        "custody_bags": progress["custody_bags"],
        "custody_loose_kg": progress["custody_loose_kg"],
        "return_locations": _jw_return_locations(db, line, order, bt),
        "receipts": [_serialize_receipt_summary(r) for r in receipts],
    }


def serialize_jw_fulfillment_order(order: JobWorkOrder, db: Session, *, tab: str) -> dict | None:
    if order.status != JobWorkOrderStatus.open:
        return None
    lines: list[dict] = []
    for line in sorted(order.lines or [], key=lambda x: x.line_index):
        row = serialize_jw_fulfillment_line(line, order, db)
        if tab == "all":
            lines.append(row)
        elif tab == "receive" and _jw_line_has_remaining_receive(row):
            lines.append(row)
        elif tab == "return" and _jw_line_has_custody(row):
            lines.append(row)
    if not lines:
        return None
    return {
        "order_id": order.id,
        "job_number": order.job_number,
        "customer_id": order.customer_id,
        "customer_name": order.customer.name if order.customer else None,
        "job_date": order.job_date,
        "status": order.status.value,
        "lines": lines,
    }


def list_jw_fulfillment_orders(
    db: Session,
    *,
    tab: str = "all",
    visibility: str = "actionable",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    orders = (
        db.scalars(
            select(JobWorkOrder)
            .where(JobWorkOrder.status == JobWorkOrderStatus.open)
            .options(*_load_order_options())
            .order_by(JobWorkOrder.job_date.desc(), JobWorkOrder.id.desc())
        )
        .unique()
        .all()
    )
    result: list[dict] = []
    for order in orders:
        data = serialize_jw_fulfillment_order(order, db, tab=tab)
        if not data:
            continue
        if visibility == "actionable":
            data = {
                **data,
                "lines": [ln for ln in data["lines"] if _jw_line_is_actionable(ln)],
            }
        if not data["lines"]:
            continue
        result.append(data)
    total = len(result)
    page = result[offset : offset + limit]
    return page, total


def serialize_job_work_order(order: JobWorkOrder) -> dict:
    lines = []
    for ln in sorted(order.lines or [], key=lambda x: x.line_index):
        bt = ln.bag_type
        progress = _jw_line_progress(ln, bt)
        lines.append(
            {
                "id": ln.id,
                "product_id": ln.product_id,
                "product_name": ln.product.product_name if ln.product else None,
                "brand_id": ln.brand_id,
                "brand_name": ln.brand.name if ln.brand else None,
                "bag_type_id": ln.bag_type_id,
                "bag_type_name": ln.bag_type.name if ln.bag_type else None,
                "weight_per_bag_kg": bt.weight_per_bag_kg if bt else None,
                "is_loose": progress["is_loose"],
                "ordered_bags": ln.ordered_bags,
                "ordered_loose_kg": ln.ordered_loose_kg,
                "ordered_quantity_kg": ln.ordered_quantity_kg,
                "received_bags": ln.received_bags,
                "received_loose_kg": ln.received_loose_kg,
                "received_quantity_kg": ln.received_quantity_kg,
                "returned_bags": ln.returned_bags,
                "returned_loose_kg": ln.returned_loose_kg,
                "returned_quantity_kg": ln.returned_quantity_kg,
                "net_received_bags": progress["net_received_bags"],
                "net_received_loose_kg": progress["net_received_loose_kg"],
                "net_received_kg": progress["net_received_kg"],
                "remaining_receive_bags": progress["remaining_receive_bags"],
                "remaining_receive_loose_kg": progress["remaining_receive_loose_kg"],
                "remaining_receive_kg": progress["remaining_receive_kg"],
                "custody_bags": progress["custody_bags"],
                "custody_loose_kg": progress["custody_loose_kg"],
                "custody_kg": progress["custody_kg"],
                "line_index": ln.line_index,
                "receipts": [_serialize_receipt_summary(r) for r in _sort_receipts_newest_first(ln.receipts or [])],
            }
        )
    return {
        "id": order.id,
        "job_number": order.job_number,
        "customer_id": order.customer_id,
        "customer_name": order.customer.name if order.customer else None,
        "job_date": order.job_date,
        "notes": order.notes,
        "status": order.status.value,
        "version": order.version,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "lines": lines,
    }
