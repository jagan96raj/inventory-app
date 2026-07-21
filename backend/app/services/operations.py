from app.utils.time import utc_now

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload



from app.models.entities import (

    BagChange,

    BagChangeToLine,

    BagType,

    Brand,

    Customer,

    Inventory,

    InventoryOwnerType,

    Location,

    Product,

    ProductTransfer,

    StockDisposal,

    User,

)

from app.core.tenant import assert_entity_company

from app.services.inventory_lock import (

    get_inventory_row_for_update,

    get_or_create_inventory_row_for_update,

    inventory_row_key,

    lock_inventory_rows,

)

from app.utils import calc_quantity_kg, recalc_inventory_row, validate_bags_loose


OPERATION_ALREADY_VOIDED_MSG = "Operation already voided"
OPERATION_VOID_INSUFFICIENT_STOCK_MSG = "Cannot void — stock no longer available to reverse"


def _assert_stock_masters(
    db: Session,
    company_id: int = 1,
    *,
    product_id: int,
    brand_id: int,
    location_ids: list[int],
    bag_type_ids: list[int],
    customer_id: int | None = None,
) -> None:
    for bt_id in bag_type_ids:
        bt = db.get(BagType, bt_id)
        if not bt:
            raise ValueError("Invalid bag type")
        assert_entity_company(bt, company_id, "Bag type")
    assert_entity_company(db.get(Product, product_id), company_id, "Product")
    assert_entity_company(db.get(Brand, brand_id), company_id, "Brand")
    for loc_id in location_ids:
        assert_entity_company(db.get(Location, loc_id), company_id, "Location")
    if customer_id is not None:
        assert_entity_company(db.get(Customer, customer_id), company_id, "Customer")


def _get_bag_type(db: Session, bag_type_id: int) -> BagType:
    bt = db.get(BagType, bag_type_id)
    if not bt:
        raise ValueError("Invalid bag type")
    return bt


def _resolve_stock_owner(
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> tuple[InventoryOwnerType, int | None]:
    ot = (
        owner_type
        if isinstance(owner_type, InventoryOwnerType)
        else InventoryOwnerType(str(owner_type))
    )
    if ot == InventoryOwnerType.job_work:
        if customer_id is None:
            raise ValueError("customer_id is required for job_work stock")
        return ot, customer_id
    if customer_id is not None:
        raise ValueError("customer_id must be null for owned stock")
    return ot, None


def prune_zero_inventory(db: Session, inv: Inventory) -> None:
    """Remove inventory rows with no stock left."""
    if inv.total_quantity_kg <= 0:
        db.delete(inv)
        db.flush()

def subtract_inventory(

    db: Session,

    product_id: int,

    brand_id: int,

    location_id: int,

    bag_type_id: int,

    bag_count: int,

    loose_kg: Decimal,

    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,

    customer_id: int | None = None,

    company_id: int = 1,

) -> Decimal:

    bt = _get_bag_type(db, bag_type_id)

    validate_bags_loose(bt, bag_count, loose_kg)

    qty = calc_quantity_kg(bt, bag_count, loose_kg)

    inv = get_inventory_row_for_update(
        db, product_id, brand_id, location_id, bag_type_id, owner_type, customer_id, company_id
    )

    if not inv:

        raise ValueError("Insufficient stock")

    try:

        if bt.is_loose:

            if inv.loose_kg < loose_kg:

                raise ValueError("Insufficient stock")

            inv.loose_kg -= loose_kg

        else:

            if inv.bag_count < bag_count:

                raise ValueError("Insufficient stock")

            inv.bag_count -= bag_count

        recalc_inventory_row(inv, bt)

        db.flush()
        prune_zero_inventory(db, inv)

    except IntegrityError as e:

        raise ValueError("Insufficient stock") from e

    return qty





def add_inventory(

    db: Session,

    product_id: int,

    brand_id: int,

    location_id: int,

    bag_type_id: int,

    bag_count: int,

    loose_kg: Decimal,

    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,

    customer_id: int | None = None,

    company_id: int = 1,

) -> Decimal:

    bt = _get_bag_type(db, bag_type_id)

    validate_bags_loose(bt, bag_count, loose_kg)

    qty = calc_quantity_kg(bt, bag_count, loose_kg)

    inv = get_or_create_inventory_row_for_update(
        db, product_id, brand_id, location_id, bag_type_id, owner_type, customer_id, company_id
    )

    try:

        if bt.is_loose:

            inv.loose_kg += loose_kg

        else:

            inv.bag_count += bag_count

        recalc_inventory_row(inv, bt)

        db.flush()

    except IntegrityError as e:

        raise ValueError("Insufficient stock") from e

    return qty





def _subtract_for_void(
    db: Session,
    product_id: int,
    brand_id: int,
    location_id: int,
    bag_type_id: int,
    bag_count: int,
    loose_kg: Decimal,
    *,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
    company_id: int = 1,
) -> Decimal:
    try:
        return subtract_inventory(
            db,
            product_id,
            brand_id,
            location_id,
            bag_type_id,
            bag_count,
            loose_kg,
            owner_type=owner_type,
            customer_id=customer_id,
            company_id=company_id,
        )
    except ValueError as e:
        if str(e) == "Insufficient stock":
            raise ValueError(OPERATION_VOID_INSUFFICIENT_STOCK_MSG) from e
        raise





def create_bag_change(

    db: Session,

    *,

    company_id: int = 1,

    location_id: int,

    product_id: int,

    brand_id: int,

    from_bag_type_id: int,

    from_bag_count: int,

    from_loose_kg: Decimal,

    quantity_loss_kg: Decimal,

    to_lines: list[dict],
    notes: str | None,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> BagChange:
    ot, cid = _resolve_stock_owner(owner_type, customer_id)

    if quantity_loss_kg < 0:

        raise ValueError("quantity_loss_kg cannot be negative")

    if not to_lines:

        raise ValueError("At least one to-line is required")

    bag_type_ids = [from_bag_type_id] + [line["to_bag_type_id"] for line in to_lines]
    _assert_stock_masters(
        db,
        company_id,
        product_id=product_id,
        brand_id=brand_id,
        location_ids=[location_id],
        bag_type_ids=bag_type_ids,
        customer_id=cid,
    )

    from_bt = _get_bag_type(db, from_bag_type_id)

    validate_bags_loose(from_bt, from_bag_count, from_loose_kg)

    from_kg = calc_quantity_kg(from_bt, from_bag_count, from_loose_kg)



    to_line_rows: list[tuple[int, int, Decimal, Decimal, BagType]] = []

    to_total = Decimal("0")

    for idx, line in enumerate(to_lines):

        to_bt = _get_bag_type(db, line["to_bag_type_id"])

        bags = line["bag_count"]

        loose = Decimal(line["loose_kg"])

        validate_bags_loose(to_bt, bags, loose)

        line_kg = calc_quantity_kg(to_bt, bags, loose)

        to_total += line_kg

        to_line_rows.append((line["to_bag_type_id"], bags, loose, line_kg, to_bt))



    if from_kg != to_total + quantity_loss_kg:

        raise ValueError("from_kg must equal sum(to_lines) + quantity_loss_kg")



    op_at = utc_now()



    lock_keys = [inventory_row_key(product_id, brand_id, location_id, from_bag_type_id, ot, cid)]

    for line in to_lines:

        lock_keys.append(inventory_row_key(product_id, brand_id, location_id, line["to_bag_type_id"], ot, cid))

    lock_inventory_rows(db, lock_keys)



    subtract_inventory(

        db, product_id, brand_id, location_id, from_bag_type_id, from_bag_count, from_loose_kg,
        owner_type=ot, customer_id=cid, company_id=company_id,

    )



    record = BagChange(

        company_id=company_id,
        location_id=location_id,

        product_id=product_id,

        brand_id=brand_id,

        from_bag_type_id=from_bag_type_id,
        owner_type=ot,
        customer_id=cid,

        from_bag_count=from_bag_count,

        from_loose_kg=from_loose_kg,

        from_quantity_kg=from_kg,

        quantity_loss_kg=quantity_loss_kg,

        operation_at=op_at,

        notes=notes,

    )

    db.add(record)

    db.flush()



    for idx, (to_bag_type_id, bags, loose, line_kg, _to_bt) in enumerate(to_line_rows):

        add_inventory(db, product_id, brand_id, location_id, to_bag_type_id, bags, loose, owner_type=ot, customer_id=cid, company_id=company_id)

        db.add(

            BagChangeToLine(

                bag_change_id=record.id,

                to_bag_type_id=to_bag_type_id,

                bag_count=bags,

                loose_kg=loose,

                quantity_kg=line_kg,

                line_index=idx,

            )

        )



    db.commit()

    return load_bag_change(db, record.id)





def create_product_transfer(

    db: Session,

    *,

    company_id: int = 1,

    product_id: int,

    brand_id: int,

    bag_type_id: int,

    from_location_id: int,

    to_location_id: int,

    bag_count: int,

    loose_kg: Decimal,
    notes: str | None,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> ProductTransfer:
    ot, cid = _resolve_stock_owner(owner_type, customer_id)

    if from_location_id == to_location_id:

        raise ValueError("from_location_id and to_location_id must differ")

    _assert_stock_masters(
        db,
        company_id,
        product_id=product_id,
        brand_id=brand_id,
        location_ids=[from_location_id, to_location_id],
        bag_type_ids=[bag_type_id],
        customer_id=cid,
    )



    lock_inventory_rows(

        db,

        [

            inventory_row_key(product_id, brand_id, from_location_id, bag_type_id, ot, cid),

            inventory_row_key(product_id, brand_id, to_location_id, bag_type_id, ot, cid),

        ],

    )



    qty = subtract_inventory(
        db, product_id, brand_id, from_location_id, bag_type_id, bag_count, loose_kg,
        owner_type=ot, customer_id=cid, company_id=company_id,
    )
    add_inventory(
        db, product_id, brand_id, to_location_id, bag_type_id, bag_count, loose_kg,
        owner_type=ot, customer_id=cid, company_id=company_id,
    )



    record = ProductTransfer(

        company_id=company_id,
        product_id=product_id,

        brand_id=brand_id,

        bag_type_id=bag_type_id,
        owner_type=ot,
        customer_id=cid,

        from_location_id=from_location_id,

        to_location_id=to_location_id,

        bag_count=bag_count,

        loose_kg=loose_kg,

        quantity_kg=qty,

        operation_at=utc_now(),

        notes=notes,

    )

    db.add(record)

    db.commit()

    return load_product_transfer(db, record.id)





def create_stock_disposal(

    db: Session,

    *,

    company_id: int = 1,

    location_id: int,

    product_id: int,

    brand_id: int,

    bag_type_id: int,

    bag_count: int,

    loose_kg: Decimal,

    reason: str | None,

    notes: str | None,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> StockDisposal:
    ot, cid = _resolve_stock_owner(owner_type, customer_id)

    _assert_stock_masters(
        db,
        company_id,
        product_id=product_id,
        brand_id=brand_id,
        location_ids=[location_id],
        bag_type_ids=[bag_type_id],
        customer_id=cid,
    )

    qty = subtract_inventory(
        db, product_id, brand_id, location_id, bag_type_id, bag_count, loose_kg,
        owner_type=ot, customer_id=cid, company_id=company_id,
    )



    record = StockDisposal(

        company_id=company_id,
        location_id=location_id,

        product_id=product_id,

        brand_id=brand_id,

        bag_type_id=bag_type_id,
        owner_type=ot,
        customer_id=cid,

        bag_count=bag_count,

        loose_kg=loose_kg,

        quantity_kg=qty,

        reason=reason,

        notes=notes,

        operation_at=utc_now(),

    )

    db.add(record)

    db.commit()

    return load_stock_disposal(db, record.id)





def load_bag_change(db: Session, record_id: int) -> BagChange:

    row = db.scalar(

        select(BagChange)

        .where(BagChange.id == record_id)

        .options(

            joinedload(BagChange.location),

            joinedload(BagChange.product),

            joinedload(BagChange.brand),

            joinedload(BagChange.from_bag_type),

            joinedload(BagChange.customer),

            joinedload(BagChange.to_lines).joinedload(BagChangeToLine.to_bag_type),

        )

    )

    if not row:

        raise ValueError("Bag change not found")

    return row





def load_product_transfer(db: Session, record_id: int) -> ProductTransfer:

    row = db.scalar(

        select(ProductTransfer)

        .where(ProductTransfer.id == record_id)

        .options(

            joinedload(ProductTransfer.product),

            joinedload(ProductTransfer.brand),

            joinedload(ProductTransfer.bag_type),

            joinedload(ProductTransfer.from_location),

            joinedload(ProductTransfer.to_location),

            joinedload(ProductTransfer.customer),

        )

    )

    if not row:

        raise ValueError("Product transfer not found")

    return row





def load_stock_disposal(db: Session, record_id: int) -> StockDisposal:

    row = db.scalar(

        select(StockDisposal)

        .where(StockDisposal.id == record_id)

        .options(

            joinedload(StockDisposal.location),

            joinedload(StockDisposal.product),

            joinedload(StockDisposal.brand),

            joinedload(StockDisposal.bag_type),

            joinedload(StockDisposal.customer),

        )

    )

    if not row:

        raise ValueError("Stock disposal not found")

    return row





def serialize_bag_change(row: BagChange) -> dict:

    return {

        "id": row.id,

        "location_id": row.location_id,

        "location_name": row.location.name if row.location else None,

        "product_id": row.product_id,

        "product_name": row.product.product_name if row.product else None,

        "brand_id": row.brand_id,

        "brand_name": row.brand.name if row.brand else None,

        "from_bag_type_id": row.from_bag_type_id,

        "from_bag_type_name": row.from_bag_type.name if row.from_bag_type else None,

        "owner_type": row.owner_type.value if row.owner_type else "owned",

        "customer_id": row.customer_id,

        "customer_name": row.customer.name if row.customer else None,

        "from_bag_count": row.from_bag_count,

        "from_loose_kg": row.from_loose_kg,

        "from_quantity_kg": row.from_quantity_kg,

        "quantity_loss_kg": row.quantity_loss_kg,

        "operation_at": row.operation_at,

        "voided_at": row.voided_at,

        "notes": row.notes,

        "created_at": row.created_at,

        "to_lines": [

            {

                "id": tl.id,

                "to_bag_type_id": tl.to_bag_type_id,

                "to_bag_type_name": tl.to_bag_type.name if tl.to_bag_type else None,

                "bag_count": tl.bag_count,

                "loose_kg": tl.loose_kg,

                "quantity_kg": tl.quantity_kg,

                "line_index": tl.line_index,

            }

            for tl in sorted(row.to_lines, key=lambda x: x.line_index)

        ],

    }





def serialize_product_transfer(row: ProductTransfer) -> dict:

    return {

        "id": row.id,

        "product_id": row.product_id,

        "product_name": row.product.product_name if row.product else None,

        "brand_id": row.brand_id,

        "brand_name": row.brand.name if row.brand else None,

        "bag_type_id": row.bag_type_id,

        "bag_type_name": row.bag_type.name if row.bag_type else None,

        "owner_type": row.owner_type.value if row.owner_type else "owned",

        "customer_id": row.customer_id,

        "customer_name": row.customer.name if row.customer else None,

        "from_location_id": row.from_location_id,

        "from_location_name": row.from_location.name if row.from_location else None,

        "to_location_id": row.to_location_id,

        "to_location_name": row.to_location.name if row.to_location else None,

        "bag_count": row.bag_count,

        "loose_kg": row.loose_kg,

        "quantity_kg": row.quantity_kg,

        "operation_at": row.operation_at,

        "voided_at": row.voided_at,

        "notes": row.notes,

        "created_at": row.created_at,

    }





def serialize_stock_disposal(row: StockDisposal) -> dict:

    return {

        "id": row.id,

        "location_id": row.location_id,

        "location_name": row.location.name if row.location else None,

        "product_id": row.product_id,

        "product_name": row.product.product_name if row.product else None,

        "brand_id": row.brand_id,

        "brand_name": row.brand.name if row.brand else None,

        "bag_type_id": row.bag_type_id,

        "bag_type_name": row.bag_type.name if row.bag_type else None,

        "owner_type": row.owner_type.value if row.owner_type else "owned",

        "customer_id": row.customer_id,

        "customer_name": row.customer.name if row.customer else None,

        "bag_count": row.bag_count,

        "loose_kg": row.loose_kg,

        "quantity_kg": row.quantity_kg,

        "reason": row.reason,

        "notes": row.notes,

        "operation_at": row.operation_at,

        "voided_at": row.voided_at,

        "created_at": row.created_at,

    }





def void_bag_change(db: Session, record_id: int, *, actor: User | None = None) -> BagChange:
    record = load_bag_change(db, record_id)
    if record.voided_at is not None:
        raise ValueError(OPERATION_ALREADY_VOIDED_MSG)

    lock_keys = [
        inventory_row_key(
            record.product_id, record.brand_id, record.location_id, record.from_bag_type_id,
            record.owner_type, record.customer_id,
        )
    ]
    for tl in sorted(record.to_lines, key=lambda x: x.line_index):
        lock_keys.append(
            inventory_row_key(
                record.product_id, record.brand_id, record.location_id, tl.to_bag_type_id,
                record.owner_type, record.customer_id,
            )
        )
    lock_inventory_rows(db, lock_keys)

    for tl in sorted(record.to_lines, key=lambda x: x.line_index):
        _subtract_for_void(
            db,
            record.product_id,
            record.brand_id,
            record.location_id,
            tl.to_bag_type_id,
            tl.bag_count,
            tl.loose_kg,
            owner_type=record.owner_type,
            customer_id=record.customer_id,
            company_id=record.company_id,
        )

    add_inventory(
        db,
        record.product_id,
        record.brand_id,
        record.location_id,
        record.from_bag_type_id,
        record.from_bag_count,
        record.from_loose_kg,
        owner_type=record.owner_type,
        customer_id=record.customer_id,
        company_id=record.company_id,
    )

    record.voided_at = utc_now()
    db.commit()
    result = load_bag_change(db, record_id)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.BAG_CHANGE_VOIDED,
            entity_type=AuditEntityType.BAG_CHANGE,
            entity_id=record_id,
            entity_label=f"Bag change #{record_id}",
        )
    return result


def void_product_transfer(db: Session, record_id: int, *, actor: User | None = None) -> ProductTransfer:
    record = load_product_transfer(db, record_id)
    if record.voided_at is not None:
        raise ValueError(OPERATION_ALREADY_VOIDED_MSG)

    lock_inventory_rows(
        db,
        [
            inventory_row_key(
                record.product_id, record.brand_id, record.from_location_id, record.bag_type_id,
                record.owner_type, record.customer_id,
            ),
            inventory_row_key(
                record.product_id, record.brand_id, record.to_location_id, record.bag_type_id,
                record.owner_type, record.customer_id,
            ),
        ],
    )

    _subtract_for_void(
        db,
        record.product_id,
        record.brand_id,
        record.to_location_id,
        record.bag_type_id,
        record.bag_count,
        record.loose_kg,
        owner_type=record.owner_type,
        customer_id=record.customer_id,
        company_id=record.company_id,
    )
    add_inventory(
        db,
        record.product_id,
        record.brand_id,
        record.from_location_id,
        record.bag_type_id,
        record.bag_count,
        record.loose_kg,
        owner_type=record.owner_type,
        customer_id=record.customer_id,
        company_id=record.company_id,
    )

    record.voided_at = utc_now()
    db.commit()
    result = load_product_transfer(db, record_id)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.PRODUCT_TRANSFER_VOIDED,
            entity_type=AuditEntityType.PRODUCT_TRANSFER,
            entity_id=record_id,
            entity_label=f"Transfer #{record_id}",
        )
    return result


def void_stock_disposal(db: Session, record_id: int, *, actor: User | None = None) -> StockDisposal:
    record = load_stock_disposal(db, record_id)
    if record.voided_at is not None:
        raise ValueError(OPERATION_ALREADY_VOIDED_MSG)

    lock_inventory_rows(
        db,
        [
            inventory_row_key(
                record.product_id, record.brand_id, record.location_id, record.bag_type_id,
                record.owner_type, record.customer_id,
            ),
        ],
    )
    add_inventory(
        db,
        record.product_id,
        record.brand_id,
        record.location_id,
        record.bag_type_id,
        record.bag_count,
        record.loose_kg,
        owner_type=record.owner_type,
        customer_id=record.customer_id,
        company_id=record.company_id,
    )

    record.voided_at = utc_now()
    db.commit()
    result = load_stock_disposal(db, record_id)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.STOCK_DISPOSAL_VOIDED,
            entity_type=AuditEntityType.STOCK_DISPOSAL,
            entity_id=record_id,
            entity_label=f"Disposal #{record_id}",
        )
    return result
