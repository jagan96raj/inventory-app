from datetime import date, datetime
from decimal import Decimal

from app.utils.time import resolve_business_entry, utc_now

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    BagType,
    Bill,
    BillLine,
    BillStatus,
    BillType,
    FulfillmentEntry,
    FulfillmentType,
    Inventory,
    InventoryOwnerType,
    Location,
    StockSource,
    User,
)
from app.services.bills import (
    bags_delivered_count,
    update_bill_delivery_status,
    update_line_delivery_status,
)
from app.services.inventory_lock import (
    get_inventory_row_for_update,
    get_or_create_inventory_row_for_update,
    inventory_row_key,
    lock_inventory_rows,
)
from app.services.bill_lock import lock_bill_for_update
from app.services.bill_concurrency import assert_bill_version, bump_bill_version
from app.utils import calc_quantity_kg, recalc_inventory_row, validate_bags_loose


FULFILLMENT_ALREADY_VOIDED_MSG = "Fulfillment entry already voided."
FULFILLMENT_VOID_RETURNS_FIRST_MSG = "Void returns on this deliver entry first."


def resolve_stock_location(
    bill: Bill,
    entry_type: FulfillmentType,
    location_id: int | None,
) -> int:
    if bill.bill_type == BillType.sales:
        if entry_type == FulfillmentType.return_:
            if location_id is None:
                raise ValueError("location_id is required for sales return")
            return location_id
        if not bill.location_id:
            raise ValueError("Sales bill has no location")
        return bill.location_id
    if entry_type == FulfillmentType.deliver:
        if location_id is None:
            raise ValueError("location_id is required for purchase receive")
        return location_id
    if location_id is None:
        raise ValueError("location_id is required for purchase return")
    return location_id


def _returns_against_parent(db: Session, parent_entry_id: int) -> tuple[Decimal, int]:
    rows = db.scalars(
        select(FulfillmentEntry).where(
            FulfillmentEntry.parent_entry_id == parent_entry_id,
            FulfillmentEntry.entry_type == FulfillmentType.return_,
            FulfillmentEntry.voided_at.is_(None),
        )
    ).all()
    kg = sum((r.quantity_kg for r in rows), Decimal("0"))
    bags = sum((r.bag_count for r in rows), 0)
    return kg, bags


def net_returnable_for_deliver_entry(db: Session, deliver_entry: FulfillmentEntry) -> tuple[Decimal, int]:
    returned_kg, returned_bags = _returns_against_parent(db, deliver_entry.id)
    net_kg = deliver_entry.quantity_kg - returned_kg
    net_bags = deliver_entry.bag_count - returned_bags
    return max(net_kg, Decimal("0")), max(net_bags, 0)


def returnable_deliver_entries_for_line(db: Session, line: BillLine) -> list[dict]:
    """Each purchase deliver event that still has qty available to return."""
    deliver_entries = db.scalars(
        select(FulfillmentEntry)
        .where(
            FulfillmentEntry.bill_line_id == line.id,
            FulfillmentEntry.entry_type == FulfillmentType.deliver,
        )
        .options(joinedload(FulfillmentEntry.location))
        .order_by(FulfillmentEntry.fulfilled_at, FulfillmentEntry.id)
    ).all()
    result: list[dict] = []
    for de in deliver_entries:
        if de.voided_at is not None:
            continue
        net_kg, net_bags = net_returnable_for_deliver_entry(db, de)
        if net_kg <= 0:
            continue
        result.append(
            {
                "entry_id": de.id,
                "location_id": de.location_id,
                "location_name": de.location.name if de.location else f"Location #{de.location_id}",
                "delivered_kg": str(de.quantity_kg),
                "delivered_bags": de.bag_count,
                "returnable_kg": str(net_kg),
                "returnable_bags": net_bags,
                "fulfilled_at": de.fulfilled_at.isoformat() if de.fulfilled_at else None,
            }
        )
    return result


def get_inventory_row(
    db: Session,
    product_id: int,
    brand_id: int,
    location_id: int,
    bag_type_id: int,
    company_id: int,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> Inventory | None:
    ot = owner_type.value if isinstance(owner_type, InventoryOwnerType) else str(owner_type)
    ot_enum = InventoryOwnerType(ot)
    q = select(Inventory).where(
        Inventory.company_id == company_id,
        Inventory.product_id == product_id,
        Inventory.brand_id == brand_id,
        Inventory.location_id == location_id,
        Inventory.bag_type_id == bag_type_id,
        Inventory.owner_type == ot_enum,
    )
    if customer_id is None:
        q = q.where(Inventory.customer_id.is_(None))
    else:
        q = q.where(Inventory.customer_id == customer_id)
    return db.scalar(q)


def _line_stock_owner(line: BillLine, bill: Bill) -> tuple[InventoryOwnerType, int | None]:
    if bill.bill_type == BillType.purchase:
        return InventoryOwnerType.owned, None
    source = line.stock_source or StockSource.owned
    if source == StockSource.job_work:
        return InventoryOwnerType.job_work, bill.customer_id
    return InventoryOwnerType.owned, None


def net_fulfilled_kg(line: BillLine, bill_type: BillType) -> Decimal:
    if bill_type == BillType.sales:
        return line.net_delivered_kg - line.net_returned_kg
    return line.net_received_kg - line.net_returned_kg


def recompute_line_fulfillment(db: Session, line: BillLine, bill: Bill) -> None:
    entries = db.scalars(select(FulfillmentEntry).where(FulfillmentEntry.bill_line_id == line.id)).all()
    delivered = Decimal("0")
    received = Decimal("0")
    returned = Decimal("0")
    for e in entries:
        if e.voided_at is not None:
            continue
        if e.entry_type == FulfillmentType.deliver:
            if bill.bill_type == BillType.sales:
                delivered += e.quantity_kg
            else:
                received += e.quantity_kg
        elif e.entry_type == FulfillmentType.return_:
            returned += e.quantity_kg
    line.net_delivered_kg = delivered
    line.net_received_kg = received
    line.net_returned_kg = returned
    update_line_delivery_status(line, bill.bill_type)


def _resolve_bag_type(db: Session, line: BillLine) -> BagType:
    if line.bag_type:
        return line.bag_type
    bt = db.get(BagType, line.bag_type_id)
    if not bt:
        raise ValueError("Bag type not found for bill line")
    line.bag_type = bt
    return bt


def _normalize_fulfillment_bags(
    bag_type: BagType, quantity_kg: Decimal, bag_count: int, loose_kg: Decimal
) -> tuple[int, Decimal]:
    if bag_type.is_loose:
        return 0, quantity_kg
    return bag_count, Decimal("0")


def apply_stock_change(
    db: Session,
    bill: Bill,
    line: BillLine,
    entry_type: FulfillmentType,
    quantity_kg: Decimal,
    bag_count: int,
    loose_kg: Decimal,
    location_id: int,
) -> None:
    bag_type = _resolve_bag_type(db, line)
    bag_count, loose_kg = _normalize_fulfillment_bags(bag_type, quantity_kg, bag_count, loose_kg)
    owner_type, customer_id = _line_stock_owner(line, bill)

    try:
        if entry_type == FulfillmentType.deliver:
            if bill.bill_type == BillType.sales:
                inv = get_inventory_row_for_update(
                    db,
                    line.product_id,
                    line.brand_id,
                    location_id,
                    line.bag_type_id,
                    owner_type,
                    customer_id,
                    company_id=bill.company_id,
                )
                if not inv or inv.total_quantity_kg < quantity_kg:
                    raise ValueError("Insufficient stock for delivery")
                if bag_type.is_loose:
                    inv.loose_kg -= quantity_kg
                else:
                    inv.bag_count -= bag_count
                recalc_inventory_row(inv, bag_type)
            else:
                inv = get_or_create_inventory_row_for_update(
                    db,
                    line.product_id,
                    line.brand_id,
                    location_id,
                    line.bag_type_id,
                    InventoryOwnerType.owned,
                    None,
                    company_id=bill.company_id,
                )
                if bag_type.is_loose:
                    inv.loose_kg += quantity_kg
                else:
                    inv.bag_count += bag_count
                recalc_inventory_row(inv, bag_type)

        elif entry_type == FulfillmentType.return_:
            if bill.bill_type == BillType.sales:
                inv = get_or_create_inventory_row_for_update(
                    db,
                    line.product_id,
                    line.brand_id,
                    location_id,
                    line.bag_type_id,
                    owner_type,
                    customer_id,
                    company_id=bill.company_id,
                )
                if bag_type.is_loose:
                    inv.loose_kg += quantity_kg
                else:
                    inv.bag_count += bag_count
                recalc_inventory_row(inv, bag_type)
            else:
                inv = get_inventory_row_for_update(
                    db,
                    line.product_id,
                    line.brand_id,
                    location_id,
                    line.bag_type_id,
                    InventoryOwnerType.owned,
                    None,
                    company_id=bill.company_id,
                )
                if not inv:
                    raise ValueError("Insufficient stock for purchase return")
                if bag_type.is_loose:
                    if inv.loose_kg < quantity_kg:
                        raise ValueError("Insufficient loose stock for purchase return")
                    inv.loose_kg -= quantity_kg
                else:
                    if inv.bag_count < bag_count:
                        raise ValueError("Insufficient bag stock for purchase return")
                    inv.bag_count -= bag_count
                recalc_inventory_row(inv, bag_type)
        db.flush()
    except IntegrityError as e:
        if entry_type == FulfillmentType.deliver and bill.bill_type == BillType.sales:
            raise ValueError("Insufficient stock for delivery") from e
        if entry_type == FulfillmentType.return_ and bill.bill_type == BillType.purchase:
            raise ValueError("Insufficient stock for purchase return") from e
        raise ValueError("Insufficient stock") from e


def reverse_stock_change(
    db: Session,
    bill: Bill,
    line: BillLine,
    entry: FulfillmentEntry,
) -> None:
    """Undo inventory effect of an active fulfillment entry (Spec v12.5)."""
    entry_type = entry.entry_type
    quantity_kg = entry.quantity_kg
    bag_count = entry.bag_count
    loose_kg = entry.loose_kg
    location_id = entry.location_id
    if location_id is None:
        raise ValueError("Entry has no stock location")

    bag_type = _resolve_bag_type(db, line)
    bag_count, loose_kg = _normalize_fulfillment_bags(bag_type, quantity_kg, bag_count, loose_kg)
    owner_type, customer_id = _line_stock_owner(line, bill)

    try:
        if entry_type == FulfillmentType.deliver:
            if bill.bill_type == BillType.sales:
                inv = get_or_create_inventory_row_for_update(
                    db,
                    line.product_id,
                    line.brand_id,
                    location_id,
                    line.bag_type_id,
                    owner_type,
                    customer_id,
                    company_id=bill.company_id,
                )
                if bag_type.is_loose:
                    inv.loose_kg += quantity_kg
                else:
                    inv.bag_count += bag_count
                recalc_inventory_row(inv, bag_type)
            else:
                inv = get_inventory_row_for_update(
                    db,
                    line.product_id,
                    line.brand_id,
                    location_id,
                    line.bag_type_id,
                    InventoryOwnerType.owned,
                    None,
                    company_id=bill.company_id,
                )
                if not inv:
                    raise ValueError("Insufficient stock")
                if bag_type.is_loose:
                    if inv.loose_kg < quantity_kg:
                        raise ValueError("Insufficient stock")
                    inv.loose_kg -= quantity_kg
                else:
                    if inv.bag_count < bag_count:
                        raise ValueError("Insufficient stock")
                    inv.bag_count -= bag_count
                recalc_inventory_row(inv, bag_type)

        elif entry_type == FulfillmentType.return_:
            if bill.bill_type == BillType.sales:
                inv = get_inventory_row_for_update(
                    db,
                    line.product_id,
                    line.brand_id,
                    location_id,
                    line.bag_type_id,
                    owner_type,
                    customer_id,
                    company_id=bill.company_id,
                )
                if not inv:
                    raise ValueError("Insufficient stock")
                if bag_type.is_loose:
                    if inv.loose_kg < quantity_kg:
                        raise ValueError("Insufficient stock")
                    inv.loose_kg -= quantity_kg
                else:
                    if inv.bag_count < bag_count:
                        raise ValueError("Insufficient stock")
                    inv.bag_count -= bag_count
                recalc_inventory_row(inv, bag_type)
            else:
                inv = get_or_create_inventory_row_for_update(
                    db,
                    line.product_id,
                    line.brand_id,
                    location_id,
                    line.bag_type_id,
                    InventoryOwnerType.owned,
                    None,
                    company_id=bill.company_id,
                )
                if bag_type.is_loose:
                    inv.loose_kg += quantity_kg
                else:
                    inv.bag_count += bag_count
                recalc_inventory_row(inv, bag_type)
        db.flush()
    except IntegrityError as e:
        if entry_type == FulfillmentType.deliver and bill.bill_type == BillType.purchase:
            raise ValueError("Insufficient stock") from e
        if entry_type == FulfillmentType.return_ and bill.bill_type == BillType.sales:
            raise ValueError("Insufficient stock") from e
        raise ValueError("Insufficient stock") from e


def _has_active_child_returns(db: Session, deliver_entry_id: int) -> bool:
    child_id = db.scalar(
        select(FulfillmentEntry.id)
        .where(
            FulfillmentEntry.parent_entry_id == deliver_entry_id,
            FulfillmentEntry.entry_type == FulfillmentType.return_,
            FulfillmentEntry.voided_at.is_(None),
        )
        .limit(1)
    )
    return child_id is not None


def void_fulfillment_entry(
    db: Session,
    entry_id: int,
    *,
    expected_version: int | None,
    actor: User | None = None,
    company_id: int | None = None,
) -> FulfillmentEntry:
    entry = db.scalar(
        select(FulfillmentEntry)
        .where(FulfillmentEntry.id == entry_id)
        .options(
            joinedload(FulfillmentEntry.bill_line).joinedload(BillLine.bill),
            joinedload(FulfillmentEntry.bill_line).joinedload(BillLine.bag_type),
            joinedload(FulfillmentEntry.location),
        )
    )
    if not entry:
        raise ValueError("Fulfillment entry not found")
    if entry.voided_at is not None:
        raise ValueError(FULFILLMENT_ALREADY_VOIDED_MSG)

    line = entry.bill_line
    if not line or not line.bill:
        raise ValueError("Bill line not found")
    bill = line.bill
    if company_id is not None and int(getattr(bill, "company_id", company_id) or company_id) != int(company_id):
        raise ValueError("Fulfillment entry not found")
    locked_bill = lock_bill_for_update(db, bill.id)
    if not locked_bill:
        raise ValueError("Bill not found")
    assert_bill_version(locked_bill, expected_version)

    if (
        bill.bill_type == BillType.purchase
        and entry.entry_type == FulfillmentType.deliver
        and _has_active_child_returns(db, entry.id)
    ):
        raise ValueError(FULFILLMENT_VOID_RETURNS_FIRST_MSG)

    reverse_stock_change(db, bill, line, entry)
    entry.voided_at = utc_now()
    db.flush()
    recompute_line_fulfillment(db, line, bill)
    update_bill_delivery_status(db, bill)
    bump_bill_version(bill)
    db.commit()
    db.refresh(entry)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.FULFILLMENT_VOIDED,
            entity_type=AuditEntityType.FULFILLMENT_ENTRY,
            entity_id=entry.id,
            entity_label=bill.bill_number,
            metadata={
                "bill_id": bill.id,
                "entry_type": entry.entry_type.value,
                "quantity_kg": str(entry.quantity_kg),
            },
        )
    return entry


def fulfillment_entry_to_out(entry: FulfillmentEntry) -> dict:
    loc_name = entry.location.name if entry.location else None
    if not loc_name and entry.location_id:
        loc_name = f"Location #{entry.location_id}"
    return {
        "id": entry.id,
        "bill_line_id": entry.bill_line_id,
        "entry_type": entry.entry_type,
        "quantity_kg": entry.quantity_kg,
        "bag_count": entry.bag_count,
        "loose_kg": entry.loose_kg,
        "location_id": entry.location_id,
        "location_name": loc_name,
        "parent_entry_id": entry.parent_entry_id,
        "notes": entry.notes,
        "vehicle_no": entry.vehicle_no,
        "fulfilled_at": entry.fulfilled_at,
        "created_at": entry.created_at,
        "voided_at": entry.voided_at,
    }


def fulfillment_audit_to_out(entry: FulfillmentEntry) -> dict:
    data = fulfillment_entry_to_out(entry)
    line = entry.bill_line
    bill = line.bill
    bag_type = line.bag_type
    data.update(
        {
            "bill_id": bill.id,
            "bill_number": bill.bill_number,
            "bill_type": bill.bill_type,
            "bill_version": bill.version,
            "customer_name": bill.customer.name if bill.customer else None,
            "product_name": line.product.product_name if line.product else None,
            "brand_name": line.brand.name if line.brand else None,
            "bag_type_name": bag_type.name if bag_type else None,
            "is_loose": bag_type.is_loose if bag_type else False,
            "bill_location_name": bill.location.name if bill.location else None,
            "stock_source": line.stock_source if bill.bill_type == BillType.sales else None,
        }
    )
    return data


def fulfillment_audit_query():
    return (
        select(FulfillmentEntry)
        .join(BillLine, FulfillmentEntry.bill_line_id == BillLine.id)
        .join(Bill, BillLine.bill_id == Bill.id)
        .options(
            joinedload(FulfillmentEntry.location),
            joinedload(FulfillmentEntry.bill_line).joinedload(BillLine.product),
            joinedload(FulfillmentEntry.bill_line).joinedload(BillLine.brand),
            joinedload(FulfillmentEntry.bill_line).joinedload(BillLine.bag_type),
            joinedload(FulfillmentEntry.bill_line).joinedload(BillLine.bill).joinedload(Bill.customer),
            joinedload(FulfillmentEntry.bill_line).joinedload(BillLine.bill).joinedload(Bill.location),
        )
        .order_by(FulfillmentEntry.fulfilled_at.desc(), FulfillmentEntry.id.desc())
    )


def _prepare_line_qty(
    db: Session, line: BillLine, bag_count: int, loose_kg: Decimal
) -> tuple[Decimal, int, Decimal, BagType]:
    bag_type = _resolve_bag_type(db, line)
    loose = Decimal(loose_kg)
    bags = bag_count
    quantity_kg = calc_quantity_kg(bag_type, bags, loose)
    bags, loose = _normalize_fulfillment_bags(bag_type, quantity_kg, bags, loose)
    return quantity_kg, bags, loose, bag_type


def _validate_purchase_return_parent(
    db: Session,
    line: BillLine,
    parent_entry_id: int | None,
    quantity_kg: Decimal,
    bag_count: int,
    bag_type: BagType,
    client_location_id: int | None = None,
) -> int:
    if parent_entry_id is None:
        raise ValueError("parent_entry_id is required for purchase return")
    parent = db.get(FulfillmentEntry, parent_entry_id)
    if not parent or parent.bill_line_id != line.id:
        raise ValueError("Invalid parent deliver entry for this line")
    if parent.entry_type != FulfillmentType.deliver:
        raise ValueError("Parent entry must be a deliver event")
    if parent.location_id is None:
        raise ValueError("Parent deliver entry has no location")
    if client_location_id is not None and client_location_id != parent.location_id:
        raise ValueError("location_id must match the parent deliver entry for purchase return")
    net_kg, net_bags = net_returnable_for_deliver_entry(db, parent)
    if quantity_kg > net_kg:
        raise ValueError("Return cannot exceed quantity from this deliver entry")
    if not bag_type.is_loose and bag_count > net_bags:
        raise ValueError("Return cannot exceed bags from this deliver entry")
    return parent.location_id


def _validate_fulfillment_line(
    db: Session,
    bill: Bill,
    line: BillLine,
    entry_type: FulfillmentType,
    quantity_kg: Decimal,
    bag_count: int,
    loose_kg: Decimal,
    bag_type: BagType,
    location_id: int | None = None,
    parent_entry_id: int | None = None,
) -> int | None:
    if entry_type == FulfillmentType.return_ and quantity_kg <= 0:
        raise ValueError("Return quantity must be positive")
    if entry_type == FulfillmentType.deliver and quantity_kg <= 0:
        raise ValueError("Deliver quantity must be positive")
    try:
        validate_bags_loose(bag_type, bag_count, loose_kg)
    except ValueError as e:
        raise ValueError(str(e)) from e
    expected_kg = calc_quantity_kg(bag_type, bag_count, loose_kg)
    if expected_kg != quantity_kg:
        raise ValueError("quantity_kg must match bag count / loose kg for this bag type")

    net = net_fulfilled_kg(line, bill.bill_type)
    if entry_type == FulfillmentType.deliver:
        if net + quantity_kg > line.ordered_quantity_kg:
            raise ValueError(f"Line {line.id}: cannot exceed ordered quantity")
        return location_id
    if bill.bill_type == BillType.purchase:
        return _validate_purchase_return_parent(
            db,
            line,
            parent_entry_id,
            quantity_kg,
            bag_count,
            bag_type,
            client_location_id=location_id,
        )
    if location_id is None:
        raise ValueError("location_id is required for sales return")
    if not db.get(Location, location_id):
        raise ValueError("Invalid location")
    if quantity_kg > net:
        raise ValueError(f"Line {line.id}: return cannot exceed net fulfilled quantity")
    return location_id


def _apply_fulfillment_to_line(
    db: Session,
    bill: Bill,
    line: BillLine,
    entry_type: FulfillmentType,
    quantity_kg: Decimal,
    bag_count: int,
    loose_kg: Decimal,
    vehicle_no: str | None,
    fulfilled_at: datetime,
    location_id: int | None = None,
    parent_entry_id: int | None = None,
    notes: str | None = None,
) -> FulfillmentEntry:
    bag_type = _resolve_bag_type(db, line)
    bag_count, loose_kg = _normalize_fulfillment_bags(bag_type, quantity_kg, bag_count, loose_kg)
    validated_location = _validate_fulfillment_line(
        db,
        bill,
        line,
        entry_type,
        quantity_kg,
        bag_count,
        loose_kg,
        bag_type,
        location_id=location_id,
        parent_entry_id=parent_entry_id,
    )
    stock_location_id = resolve_stock_location(bill, entry_type, validated_location)
    apply_stock_change(
        db, bill, line, entry_type, quantity_kg, bag_count, loose_kg, stock_location_id
    )
    entry = FulfillmentEntry(
        bill_line_id=line.id,
        entry_type=entry_type,
        quantity_kg=quantity_kg,
        bag_count=bag_count,
        loose_kg=loose_kg,
        location_id=stock_location_id,
        parent_entry_id=parent_entry_id if entry_type == FulfillmentType.return_ else None,
        notes=notes,
        vehicle_no=vehicle_no,
        fulfilled_at=fulfilled_at,
    )
    db.add(entry)
    db.flush()
    recompute_line_fulfillment(db, line, bill)
    return entry


def create_fulfillment(
    db: Session,
    bill_line_id: int,
    entry_type: FulfillmentType,
    quantity_kg: Decimal,
    bag_count: int = 0,
    loose_kg: Decimal = Decimal("0"),
    location_id: int | None = None,
    parent_entry_id: int | None = None,
    notes: str | None = None,
    vehicle_no: str | None = None,
    *,
    expected_version: int | None = None,
    fulfilled_date: date | None = None,
    company_id: int | None = None,
) -> FulfillmentEntry:
    line = db.scalar(
        select(BillLine)
        .where(BillLine.id == bill_line_id)
        .options(joinedload(BillLine.bill), joinedload(BillLine.bag_type))
    )
    if not line or not line.bill:
        raise ValueError("Bill line not found")
    bill = line.bill
    if company_id is not None and int(getattr(bill, "company_id", company_id) or company_id) != int(company_id):
        raise ValueError("Bill line not found")
    if bill.status != BillStatus.finalized:
        raise ValueError("Bill must be finalized for fulfillment")
    locked_bill = lock_bill_for_update(db, bill.id)
    if not locked_bill:
        raise ValueError("Bill not found")
    assert_bill_version(locked_bill, expected_version)

    _, at = resolve_business_entry(fulfilled_date)
    entry = _apply_fulfillment_to_line(
        db,
        bill,
        line,
        entry_type,
        quantity_kg,
        bag_count,
        loose_kg,
        vehicle_no,
        at,
        location_id=location_id,
        parent_entry_id=parent_entry_id,
        notes=notes,
    )
    bill = db.scalar(select(Bill).where(Bill.id == bill.id).options(joinedload(Bill.lines)))
    if bill:
        update_bill_delivery_status(db, bill)
        bump_bill_version(bill)
    db.commit()
    db.refresh(entry)
    return entry


def create_bill_fulfillment_event(
    db: Session,
    bill_id: int,
    entry_type: FulfillmentType,
    fulfilled_at: datetime,
    vehicle_no: str | None,
    line_items: list[tuple[int, int, Decimal]],
    location_id: int | None = None,
    *,
    expected_version: int | None = None,
    company_id: int | None = None,
) -> dict:
    """Apply deliver/return for all lines with qty > 0 in one transaction."""
    q = (
        select(Bill)
        .where(Bill.id == bill_id)
        .options(
            joinedload(Bill.lines).joinedload(BillLine.bag_type),
            joinedload(Bill.lines).joinedload(BillLine.product),
            joinedload(Bill.lines).joinedload(BillLine.brand),
        )
    )
    if company_id is not None:
        q = q.where(Bill.company_id == company_id)
    bill = db.scalar(q)
    if not bill:
        raise ValueError("Bill not found")
    locked_bill = lock_bill_for_update(db, bill.id)
    if not locked_bill:
        raise ValueError("Bill not found")
    assert_bill_version(locked_bill, expected_version)
    if bill.status != BillStatus.finalized:
        raise ValueError("Bill must be finalized for fulfillment")

    seen_lines: set[int] = set()
    line_map: dict[int, BillLine] = {}
    for ln in bill.lines:
        if ln.id in seen_lines:
            continue
        seen_lines.add(ln.id)
        line_map[ln.id] = ln

    prepared: list[tuple[BillLine, Decimal, int, Decimal, BagType]] = []
    for bill_line_id, bag_count, loose_kg in line_items:
        line = line_map.get(bill_line_id)
        if not line:
            raise ValueError(f"Line {bill_line_id} not on this bill")
        quantity_kg, bags, loose, bag_type = _prepare_line_qty(db, line, bag_count, loose_kg)
        if quantity_kg <= 0:
            continue
        prepared.append((line, quantity_kg, bags, loose, bag_type))

    if not prepared:
        raise ValueError("No lines with quantity greater than zero")

    stock_location_id = resolve_stock_location(bill, entry_type, location_id)

    # Validate all lines before any stock change
    sales_deliver_demand: dict[tuple[int, int, int], Decimal] = {}
    for line, quantity_kg, bag_count, loose_kg, bag_type in prepared:
        _validate_fulfillment_line(
            db,
            bill,
            line,
            entry_type,
            quantity_kg,
            bag_count,
            loose_kg,
            bag_type,
            location_id=stock_location_id,
        )
        if entry_type == FulfillmentType.deliver and bill.bill_type == BillType.sales:
            key = (line.product_id, line.brand_id, line.bag_type_id)
            sales_deliver_demand[key] = sales_deliver_demand.get(key, Decimal("0")) + quantity_kg

    locked_rows: dict[tuple[int, int, int, int], Inventory | None] = {}
    if sales_deliver_demand:
        lock_keys = [
            inventory_row_key(pid, bid, stock_location_id, btid)
            for pid, bid, btid in sales_deliver_demand.keys()
        ]
        locked_rows = lock_inventory_rows(db, bill.company_id, lock_keys)

    for key, demand in sales_deliver_demand.items():
        pid, bid, btid = key
        full_key = inventory_row_key(pid, bid, stock_location_id, btid)
        inv = locked_rows[full_key]
        if not inv or inv.total_quantity_kg < demand:
            raise ValueError("Insufficient stock for delivery on one or more lines")

    entries: list[FulfillmentEntry] = []
    try:
        for line, quantity_kg, bag_count, loose_kg, _bag_type in prepared:
            entry = _apply_fulfillment_to_line(
                db,
                bill,
                line,
                entry_type,
                quantity_kg,
                bag_count,
                loose_kg,
                vehicle_no,
                fulfilled_at,
                location_id=stock_location_id,
            )
            entries.append(entry)
        update_bill_delivery_status(db, bill)
        bump_bill_version(bill)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"bill_id": bill_id, "entry_type": entry_type.value, "entries_created": len(entries)}


def load_fulfillment_line(
    db: Session, line_id: int, company_id: int | None = None
) -> BillLine | None:
    line = db.scalar(
        select(BillLine)
        .where(BillLine.id == line_id)
        .options(
            joinedload(BillLine.bill).joinedload(Bill.customer),
            joinedload(BillLine.bill).joinedload(Bill.location),
            joinedload(BillLine.product),
            joinedload(BillLine.brand),
            joinedload(BillLine.bag_type),
        )
    )
    if line is None:
        return None
    if company_id is not None:
        bill = line.bill
        if bill is None or int(getattr(bill, "company_id", company_id) or company_id) != int(company_id):
            return None
    return line


def serialize_fulfillment_line(
    db: Session,
    b: Bill,
    ln: BillLine,
    context_parent_entry_id: int | None = None,
) -> dict:
    net = net_fulfilled_kg(ln, b.bill_type)
    bags_ordered = ln.ordered_bags if not ln.bag_type.is_loose else 0
    bags_delivered = bags_delivered_count(ln, b.bill_type)
    stock_bags = 0
    stock_kg = Decimal("0")
    if b.bill_type == BillType.sales and b.location_id:
        owner_type, customer_id = _line_stock_owner(ln, b)
        inv = get_inventory_row(
            db,
            ln.product_id,
            ln.brand_id,
            b.location_id,
            ln.bag_type_id,
            b.company_id,
            owner_type,
            customer_id,
        )
        if inv:
            stock_kg = inv.total_quantity_kg
            stock_bags = inv.bag_count if not ln.bag_type.is_loose else 0
    loc_name: str | None = None
    loc_id: int | None = None
    returnable_kg = Decimal("0")
    returnable_bags = 0
    parent_entry_summary: dict | None = None
    bill_location_id: int | None = None
    bill_location_name: str | None = None
    if b.bill_type == BillType.sales:
        bill_location_id = b.location_id
        bill_location_name = b.location.name if b.location else None
        loc_id = bill_location_id
        loc_name = bill_location_name
        if not loc_name and bill_location_id:
            loc = db.get(Location, bill_location_id)
            loc_name = loc.name if loc else f"Location #{bill_location_id}"
        returnable_kg = net
        returnable_bags = bags_delivered
    deliver_entries = (
        returnable_deliver_entries_for_line(db, ln) if b.bill_type == BillType.purchase else []
    )
    if context_parent_entry_id and b.bill_type == BillType.purchase:
        parent = db.scalar(
            select(FulfillmentEntry)
            .where(FulfillmentEntry.id == context_parent_entry_id)
            .options(joinedload(FulfillmentEntry.location))
        )
        if parent and parent.bill_line_id == ln.id and parent.entry_type == FulfillmentType.deliver:
            net_kg, net_bags = net_returnable_for_deliver_entry(db, parent)
            loc_id = parent.location_id
            loc_name = parent.location.name if parent.location else None
            returnable_kg = net_kg
            returnable_bags = net_bags
            parent_entry_summary = {
                "entry_id": parent.id,
                "delivered_kg": str(parent.quantity_kg),
                "delivered_bags": parent.bag_count,
                "returnable_kg": str(net_kg),
                "returnable_bags": net_bags,
                "fulfilled_at": parent.fulfilled_at.isoformat() if parent.fulfilled_at else None,
                "location_name": loc_name,
            }
    return {
        "line_id": ln.id,
        "bill_id": b.id,
        "bill_version": b.version,
        "bill_number": b.bill_number,
        "bill_type": b.bill_type.value,
        "customer_name": b.customer.name,
        "location_id": loc_id,
        "location_name": loc_name,
        "bill_location_id": bill_location_id,
        "bill_location_name": bill_location_name,
        "parent_entry_id": context_parent_entry_id,
        "parent_entry": parent_entry_summary,
        "return_deliver_entries": deliver_entries,
        "returnable_kg": str(returnable_kg),
        "returnable_bags": returnable_bags,
        "product_name": ln.product.product_name,
        "brand_name": ln.brand.name,
        "bag_type_name": ln.bag_type.name,
        "bag_type_id": ln.bag_type_id,
        "is_loose": ln.bag_type.is_loose,
        "weight_per_bag_kg": str(ln.bag_type.weight_per_bag_kg),
        "ordered_bags": bags_ordered,
        "bags_delivered": bags_delivered,
        "ordered_kg": str(ln.ordered_quantity_kg),
        "fulfilled_kg": str(net),
        "remaining_kg": str(ln.ordered_quantity_kg - net),
        "remaining_bags": max(bags_ordered - bags_delivered, 0),
        "line_delivery_status": ln.line_delivery_status.value,
        "order_delivery_status": b.order_delivery_status.value,
        "stock_bags": stock_bags,
        "stock_kg": str(stock_kg),
    }


def serialize_fulfillment_bill(db: Session, b: Bill) -> dict:
    seen: set[int] = set()
    lines = []
    for ln in b.lines:
        if ln.id in seen:
            continue
        seen.add(ln.id)
        net = net_fulfilled_kg(ln, b.bill_type)
        bags_ordered = ln.ordered_bags if not ln.bag_type.is_loose else 0
        bags_delivered = bags_delivered_count(ln, b.bill_type)
        line_data = {
            "line_id": ln.id,
            "product_name": ln.product.product_name,
            "brand_name": ln.brand.name,
            "bag_type_name": ln.bag_type.name,
            "bag_type_id": ln.bag_type_id,
            "is_loose": ln.bag_type.is_loose,
            "weight_per_bag_kg": str(ln.bag_type.weight_per_bag_kg),
            "ordered_bags": bags_ordered,
            "bags_delivered": bags_delivered,
            "ordered_kg": str(ln.ordered_quantity_kg),
            "fulfilled_kg": str(net),
            "remaining_kg": str(ln.ordered_quantity_kg - net),
            "remaining_bags": max(bags_ordered - bags_delivered, 0),
            "line_delivery_status": ln.line_delivery_status.value,
        }
        if b.bill_type == BillType.purchase:
            line_data["return_deliver_entries"] = returnable_deliver_entries_for_line(db, ln)
        lines.append(line_data)
    payload: dict = {
        "bill_id": b.id,
        "bill_version": b.version,
        "bill_number": b.bill_number,
        "bill_date": b.bill_date.isoformat(),
        "bill_type": b.bill_type.value,
        "customer_name": b.customer.name,
        "order_delivery_status": b.order_delivery_status.value,
        "lines": lines,
    }
    if b.bill_type == BillType.sales:
        payload["location_name"] = b.location.name if b.location else None
    return payload


def bill_is_actionable(bill_data: dict, tab: str) -> bool:
    if tab == "deliver":
        return any(Decimal(ln["remaining_kg"]) > 0 for ln in bill_data["lines"])
    for ln in bill_data["lines"]:
        if Decimal(ln["fulfilled_kg"]) > 0:
            if bill_data.get("bill_type") == "purchase":
                if ln.get("return_deliver_entries"):
                    return True
            else:
                return True
    return False
