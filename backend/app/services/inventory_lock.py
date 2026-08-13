"""Spec v12.3 / v14.0 — inventory row locking for concurrent stock mutations."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Inventory, InventoryOwnerType

InventoryKey = tuple[int, int, int, int, str, int | None]
InventorySkuKey = tuple[int, int, int, str, int | None]


def _normalize_owner(
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> tuple[str, int | None]:
    ot = owner_type.value if isinstance(owner_type, InventoryOwnerType) else str(owner_type)
    if ot == InventoryOwnerType.owned.value:
        return ot, None
    if ot == InventoryOwnerType.job_work.value:
        if customer_id is None:
            raise ValueError("customer_id is required for job_work inventory")
        return ot, customer_id
    raise ValueError(f"Invalid owner_type: {owner_type}")


def inventory_row_key(
    product_id: int,
    brand_id: int,
    location_id: int,
    bag_type_id: int,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> InventoryKey:
    ot, cid = _normalize_owner(owner_type, customer_id)
    return (product_id, brand_id, location_id, bag_type_id, ot, cid)


def sort_inventory_keys(keys: list[InventoryKey]) -> list[InventoryKey]:
    return sorted(set(keys))


def get_inventory_row_for_update(
    db: Session,
    product_id: int,
    brand_id: int,
    location_id: int,
    bag_type_id: int,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
    *,
    company_id: int,
) -> Inventory | None:
    ot, cid = _normalize_owner(owner_type, customer_id)
    ot_enum = InventoryOwnerType(ot)
    q = (
        select(Inventory)
        .where(
            Inventory.company_id == company_id,
            Inventory.product_id == product_id,
            Inventory.brand_id == brand_id,
            Inventory.location_id == location_id,
            Inventory.bag_type_id == bag_type_id,
            Inventory.owner_type == ot_enum,
        )
        .with_for_update()
    )
    if cid is None:
        q = q.where(Inventory.customer_id.is_(None))
    else:
        q = q.where(Inventory.customer_id == cid)
    return db.scalar(q)


def get_or_create_inventory_row_for_update(
    db: Session,
    product_id: int,
    brand_id: int,
    location_id: int,
    bag_type_id: int,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
    *,
    company_id: int,
) -> Inventory:
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
    if inv:
        return inv
    ot, cid = _normalize_owner(owner_type, customer_id)
    ot_enum = InventoryOwnerType(ot)
    try:
        with db.begin_nested():
            inv = Inventory(
                company_id=company_id,
                product_id=product_id,
                brand_id=brand_id,
                location_id=location_id,
                bag_type_id=bag_type_id,
                owner_type=ot_enum,
                customer_id=cid,
                bag_count=0,
                loose_kg=Decimal("0"),
                total_quantity_kg=Decimal("0"),
            )
            db.add(inv)
            db.flush()
    except IntegrityError:
        pass
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
        raise ValueError("Could not lock or create inventory row")
    return inv


def inventory_sku_key(
    product_id: int,
    brand_id: int,
    location_id: int,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> InventorySkuKey:
    ot, cid = _normalize_owner(owner_type, customer_id)
    return (product_id, brand_id, location_id, ot, cid)


def lock_inventory_product_brand_owner_rows(
    db: Session,
    company_id: int,
    product_id: int,
    brand_id: int,
    owner_type: InventoryOwnerType | str = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> list[Inventory]:
    """Lock every location/bag-type row for product+brand+owner (void kg fallback)."""
    ot, cid = _normalize_owner(owner_type, customer_id)
    ot_enum = InventoryOwnerType(ot)
    q = (
        select(Inventory)
        .where(
            Inventory.company_id == company_id,
            Inventory.product_id == product_id,
            Inventory.brand_id == brand_id,
            Inventory.owner_type == ot_enum,
        )
        .order_by(Inventory.id)
        .with_for_update()
    )
    if cid is None:
        q = q.where(Inventory.customer_id.is_(None))
    else:
        q = q.where(Inventory.customer_id == cid)
    return list(db.scalars(q).all())


def lock_inventory_sku_rows(
    db: Session, company_id: int, sku_keys: list[InventorySkuKey]
) -> list[Inventory]:
    """Lock every bag-type row for product+brand+location+owner (void kg fallback)."""
    locked: list[Inventory] = []
    for product_id, brand_id, location_id, owner_type, customer_id in sorted(set(sku_keys)):
        ot_enum = InventoryOwnerType(owner_type)
        q = (
            select(Inventory)
            .where(
                Inventory.company_id == company_id,
                Inventory.product_id == product_id,
                Inventory.brand_id == brand_id,
                Inventory.location_id == location_id,
                Inventory.owner_type == ot_enum,
            )
            .order_by(Inventory.id)
            .with_for_update()
        )
        if customer_id is None:
            q = q.where(Inventory.customer_id.is_(None))
        else:
            q = q.where(Inventory.customer_id == customer_id)
        locked.extend(list(db.scalars(q).all()))
    return locked


def lock_inventory_rows(
    db: Session, company_id: int, keys: list[InventoryKey]
) -> dict[InventoryKey, Inventory | None]:
    locked: dict[InventoryKey, Inventory | None] = {}
    for key in sort_inventory_keys(keys):
        product_id, brand_id, location_id, bag_type_id, owner_type, customer_id = key
        locked[key] = get_inventory_row_for_update(
            db,
            product_id,
            brand_id,
            location_id,
            bag_type_id,
            owner_type,
            customer_id,
            company_id=company_id,
        )
    return locked
