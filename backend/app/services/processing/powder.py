"""Processing service — powder."""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    BagType,
    BookSettings,
    Brand,
    Customer,
    CustomerPartyType,
    InventoryOwnerType,
    ProcessingBalanceReturnLine,
    ProcessingBatch,
    ProcessingInputLine,
    ProcessingInputSource,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingOutputAllocationMode,
    ProcessingOutputLine,
    ProcessingWasteAllocation,
    Product,
    User,
)
import app.services.processing as _processing
from app.services.owner_allocation import (
    OwnerKey,
    owner_key_from_line,
    proportional_split_bags,
    proportional_split_kg,
)
from app.utils import calc_quantity_kg, validate_bags_loose
from app.utils.time import utc_now

from app.services.processing.allocation import _owner_inventory_args
from app.services.processing.batch_helpers import _kg_to_bags_loose
from app.services.processing.constants import (
    POWDER_DEST_NOT_CONFIGURED_MSG,
    POWDER_OUTPUT_LINE_MSG,
)

def _powder_brand_ids(db: Session, company_id: int = 1) -> set[int]:
    from app.services.accounts import get_book_settings

    ids: set[int] = set()
    settings = get_book_settings(db, company_id)
    if settings and settings.powder_brand_id:
        ids.add(settings.powder_brand_id)
    for brand_id in db.scalars(
        select(Brand.id).where(
            Brand.company_id == company_id,
            func.lower(Brand.name) == "powder",
        )
    ).all():
        ids.add(brand_id)
    return ids

def _validate_no_powder_output_lines(
    db: Session, output_lines: list[dict], *, company_id: int = 1
) -> None:
    powder_brand_ids = _powder_brand_ids(db, company_id)
    for line in output_lines:
        brand_id = line["brand_id"]
        if brand_id in powder_brand_ids:
            raise ValueError(POWDER_OUTPUT_LINE_MSG)
        brand = db.get(Brand, brand_id)
        if brand and brand.name.strip().lower() == "powder":
            raise ValueError(POWDER_OUTPUT_LINE_MSG)

def _validate_powder_brand_id(db: Session, brand_id: int, *, company_id: int = 1) -> None:
    if brand_id in _powder_brand_ids(db, company_id):
        return
    brand = db.get(Brand, brand_id)
    if brand and brand.name.strip().lower() == "powder":
        return
    raise ValueError("Select a Powder brand for powder stock.")

def _resolve_powder_product_id(db: Session, company_id: int = 1) -> int:
    from app.services.accounts import get_book_settings

    settings = get_book_settings(db, company_id)
    if settings and settings.powder_product_id:
        return settings.powder_product_id
    product_id = db.scalar(
        select(Product.id)
        .where(
            Product.company_id == company_id,
            func.lower(Product.product_name) == "powder",
        )
        .limit(1)
    )
    if not product_id:
        raise ValueError("Create a product master named Powder (or set powder product in Book settings).")
    return product_id

def _resolve_powder_destination(db: Session, company_id: int = 1) -> tuple[int, int, int, int, BagType]:
    from app.services.accounts import get_book_settings

    settings = get_book_settings(db, company_id)
    if not settings or not all(
        [
            settings.powder_product_id,
            settings.powder_brand_id,
            settings.powder_location_id,
            settings.powder_bag_type_id,
        ]
    ):
        raise ValueError(POWDER_DEST_NOT_CONFIGURED_MSG)
    bt = db.get(BagType, settings.powder_bag_type_id)
    if not bt:
        raise ValueError(POWDER_DEST_NOT_CONFIGURED_MSG)
    return (
        settings.powder_product_id,
        settings.powder_brand_id,
        settings.powder_location_id,
        settings.powder_bag_type_id,
        bt,
    )

def _batch_powder_inventory_tuple(
    db: Session, batch: ProcessingBatch
) -> tuple[int, int, int, int, BagType]:
    company_id = getattr(batch.job, "company_id", 1) if batch.job else 1
    if batch.powder_location_id is not None:
        bt = _processing._get_bag_type(db, batch.powder_bag_type_id)
        return (
            _resolve_powder_product_id(db, company_id),
            batch.powder_brand_id,
            batch.powder_location_id,
            batch.powder_bag_type_id,
            bt,
        )
    return _resolve_powder_destination(db, company_id)

def _resolve_powder_for_batch(
    db: Session,
    *,
    powder_line: dict | None,
    powder_kg_legacy: Decimal,
    company_id: int = 1,
) -> tuple[Decimal, dict | None]:
    if powder_line:
        brand_id = powder_line["brand_id"]
        location_id = powder_line["location_id"]
        bag_type_id = powder_line["bag_type_id"]
        bag_count = powder_line["bag_count"]
        loose_kg = Decimal(powder_line["loose_kg"])
        _validate_powder_brand_id(db, brand_id, company_id=company_id)
        bt = _processing._get_bag_type(db, bag_type_id)
        validate_bags_loose(bt, bag_count, loose_kg)
        qty = calc_quantity_kg(bt, bag_count, loose_kg)
        if qty <= 0:
            raise ValueError("Powder quantity must be greater than zero")
        return qty, {
            "brand_id": brand_id,
            "location_id": location_id,
            "bag_type_id": bag_type_id,
            "bag_count": bag_count,
            "loose_kg": loose_kg,
        }
    if powder_kg_legacy > 0:
        _product_id, brand_id, location_id, bag_type_id, bt = _resolve_powder_destination(
            db, company_id
        )
        if bt.is_loose:
            bag_count = 0
            loose_kg = powder_kg_legacy
        else:
            bag_count, loose_kg = _kg_to_bags_loose(bt, powder_kg_legacy)
        validate_bags_loose(bt, bag_count, loose_kg)
        return powder_kg_legacy, {
            "brand_id": brand_id,
            "location_id": location_id,
            "bag_type_id": bag_type_id,
            "bag_count": bag_count,
            "loose_kg": loose_kg,
        }
    return Decimal("0"), None

def _store_powder_line_on_batch(
    batch: ProcessingBatch, powder_line: dict | None, powder_kg: Decimal
) -> None:
    batch.powder_kg = powder_kg
    if powder_line:
        batch.powder_brand_id = powder_line["brand_id"]
        batch.powder_location_id = powder_line["location_id"]
        batch.powder_bag_type_id = powder_line["bag_type_id"]
        batch.powder_bag_count = powder_line["bag_count"]
        batch.powder_loose_kg = powder_line["loose_kg"]
    else:
        batch.powder_brand_id = None
        batch.powder_location_id = None
        batch.powder_bag_type_id = None
        batch.powder_bag_count = None
        batch.powder_loose_kg = None

def _ensure_waste_allocation_row(
    db: Session,
    batch_id: int,
    owner_key: OwnerKey,
    waste_rows: dict[OwnerKey, ProcessingWasteAllocation],
) -> ProcessingWasteAllocation:
    if owner_key in waste_rows:
        return waste_rows[owner_key]
    owner_type, customer_id = _owner_inventory_args(owner_key)
    wa = ProcessingWasteAllocation(
        batch_id=batch_id,
        owner_type=owner_type,
        customer_id=customer_id,
    )
    db.add(wa)
    waste_rows[owner_key] = wa
    return wa

def _allocate_powder_to_owners(
    db: Session,
    batch: ProcessingBatch,
    powder_kg: Decimal,
    powder_line: dict,
    owner_weights: dict[OwnerKey, Decimal],
    waste_rows: dict[OwnerKey, ProcessingWasteAllocation],
) -> None:
    if powder_kg <= 0:
        return
    product_id = _resolve_powder_product_id(
        db, getattr(batch.job, "company_id", 1) if batch.job else 1
    )
    brand_id = powder_line["brand_id"]
    location_id = powder_line["location_id"]
    bag_type_id = powder_line["bag_type_id"]
    bt = _processing._get_bag_type(db, bag_type_id)
    weights = owner_weights or {("owned", None): powder_kg}
    splits = proportional_split_kg(powder_kg, weights)
    for owner_key, alloc_kg in splits.items():
        if alloc_kg <= 0:
            continue
        owner_type, customer_id = _owner_inventory_args(owner_key)
        if bt.is_loose:
            bag_count = 0
            loose_kg = alloc_kg
        else:
            bag_count, loose_kg = _kg_to_bags_loose(bt, alloc_kg)
        validate_bags_loose(bt, bag_count, loose_kg)
        _processing.add_inventory(
            db,
            product_id,
            brand_id,
            location_id,
            bag_type_id,
            bag_count,
            loose_kg,
            owner_type=owner_type,
            customer_id=customer_id,
            company_id=getattr(batch.job, "company_id", 1) if batch.job else 1,
        )
        wa = _ensure_waste_allocation_row(db, batch.id, owner_key, waste_rows)
        current = wa.powder_kg or Decimal("0")
        wa.powder_kg = current + alloc_kg
