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

    inventory_sku_key,

    lock_inventory_product_brand_owner_rows,

    lock_inventory_rows,

    lock_inventory_sku_rows,

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
        db,
        product_id,
        brand_id,
        location_id,
        bag_type_id,
        owner_type,
        customer_id,
        company_id=company_id,
    )

    if not inv:

        raise ValueError("Insufficient stock")

    try:

        if bt.is_loose:

            have = Decimal(inv.loose_kg).quantize(Decimal("0.001"))
            need = Decimal(loose_kg).quantize(Decimal("0.001"))
            if have < need:

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
        db,
        product_id,
        brand_id,
        location_id,
        bag_type_id,
        owner_type,
        customer_id,
        company_id=company_id,
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





VOID_KG_TOLERANCE = Decimal("0.001")


def _void_line_quantity_kg(bt: BagType, bag_count: int, loose_kg: Decimal) -> Decimal:
    """Kg to reverse: bagged leftover (legacy / rebagged) counts, unlike calc_quantity_kg."""
    if bt.is_loose:
        return Decimal(loose_kg)
    return Decimal(bag_count) * Decimal(bt.weight_per_bag_kg or 0) + Decimal(loose_kg or 0)


def _take_kg_from_inventory_row(db: Session, inv: Inventory, kg: Decimal) -> Decimal:
    """Remove up to ``kg`` from one inventory row (whole bags or loose)."""
    if kg <= 0:
        return Decimal("0")
    bt = _get_bag_type(db, inv.bag_type_id)
    taken = Decimal("0")
    if bt.is_loose:
        on_hand = Decimal(inv.loose_kg or 0)
        total = Decimal(inv.total_quantity_kg or 0)
        if total > on_hand:
            on_hand = total
            inv.loose_kg = on_hand
        take = min(on_hand, kg)
        if take <= 0:
            return Decimal("0")
        inv.loose_kg = on_hand - take
        taken = take
    else:
        weight = Decimal(bt.weight_per_bag_kg)
        if weight <= 0 or inv.bag_count <= 0:
            return Decimal("0")
        take_bags = min(int(inv.bag_count), int(kg // weight))
        if take_bags <= 0:
            return Decimal("0")
        inv.bag_count -= take_bags
        taken = Decimal(take_bags) * weight
    recalc_inventory_row(inv, bt)
    db.flush()
    prune_zero_inventory(db, inv)
    return taken


def _subtract_equivalent_kg_for_void(
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
    allow_other_locations: bool = False,
) -> Decimal:
    """Reverse void qty by kg at the same SKU when the original bag type was rebagged."""
    bt = _get_bag_type(db, bag_type_id)
    needed = _void_line_quantity_kg(bt, bag_count, loose_kg)
    if needed <= 0:
        return Decimal("0")

    rows = lock_inventory_sku_rows(
        db,
        company_id,
        [
            inventory_sku_key(
                product_id,
                brand_id,
                location_id,
                owner_type,
                customer_id,
            )
        ],
    )
    available = sum((Decimal(r.total_quantity_kg or 0) for r in rows), Decimal("0"))
    if available + VOID_KG_TOLERANCE < needed and allow_other_locations:
        rows = lock_inventory_product_brand_owner_rows(
            db,
            company_id,
            product_id,
            brand_id,
            owner_type,
            customer_id,
        )
        available = sum((Decimal(r.total_quantity_kg or 0) for r in rows), Decimal("0"))
    if available + VOID_KG_TOLERANCE < needed:
        raise ValueError(OPERATION_VOID_INSUFFICIENT_STOCK_MSG)

    def _row_sort_key(row: Inventory) -> tuple[int, int, int, int]:
        other_bt = _get_bag_type(db, row.bag_type_id)
        return (
            0 if row.location_id == location_id else 1,
            0 if row.bag_type_id == bag_type_id else 1,
            0 if other_bt.is_loose else 1,
            row.id,
        )

    ordered = sorted(rows, key=_row_sort_key)

    remaining = needed
    for inv in ordered:
        if remaining <= VOID_KG_TOLERANCE:
            break
        remaining -= _take_kg_from_inventory_row(db, inv, remaining)

    if remaining > VOID_KG_TOLERANCE:
        raise ValueError(OPERATION_VOID_INSUFFICIENT_STOCK_MSG)
    return needed


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
    allow_other_locations: bool = False,
) -> Decimal:
    bt = _get_bag_type(db, bag_type_id)
    try:
        validate_bags_loose(bt, bag_count, loose_kg)
        line_ok = True
    except ValueError:
        line_ok = False
    if line_ok:
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
            if str(e) != "Insufficient stock":
                raise
    try:
        return _subtract_equivalent_kg_for_void(
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
            allow_other_locations=allow_other_locations,
        )
    except ValueError as fallback_exc:
        if str(fallback_exc) == OPERATION_VOID_INSUFFICIENT_STOCK_MSG:
            raise ValueError(OPERATION_VOID_INSUFFICIENT_STOCK_MSG) from fallback_exc
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

    lock_inventory_rows(db, company_id, lock_keys)



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
        company_id,

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
    lock_inventory_rows(db, record.company_id, lock_keys)

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
        record.company_id,
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
        record.company_id,
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
