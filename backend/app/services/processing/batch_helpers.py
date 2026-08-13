"""Processing service — batch helpers."""
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
from app.services.fulfillment import get_inventory_row
from app.services.inventory_lock import inventory_row_key, lock_inventory_rows
from app.services.operations import (
    OPERATION_ALREADY_VOIDED_MSG,
    add_inventory,
    subtract_inventory,
    _get_bag_type,
    _subtract_for_void,
)
from app.services.owner_allocation import (
    OwnerKey,
    owner_key_from_line,
    proportional_split_bags,
    proportional_split_kg,
)
from app.utils import calc_quantity_kg, validate_bags_loose
from app.utils.time import utc_now

from app.services.processing.constants import PROCESSING_OUTPUT_TOLERANCE_KG

def _batch_is_active(batch: ProcessingBatch) -> bool:
    return getattr(batch, "voided_at", None) is None

def _active_job_batches(job: ProcessingJob) -> list[ProcessingBatch]:
    return [b for b in job.batches or [] if _batch_is_active(b)]

def _sorted_job_batches(job: ProcessingJob) -> list[ProcessingBatch]:
    return sorted(_active_job_batches(job), key=lambda b: (b.operation_at, b.id))

def _batch_has_outflow(
    *,
    output_lines: list[dict],
    balance_return_lines: list[dict],
    dust_kg: Decimal,
    stone_kg: Decimal,
    sack_weight_waste_kg: Decimal,
    powder_kg: Decimal,
    miscellaneous_waste_kg: Decimal,
) -> bool:
    return bool(
        output_lines
        or balance_return_lines
        or dust_kg > 0
        or stone_kg > 0
        or sack_weight_waste_kg > 0
        or powder_kg > 0
        or miscellaneous_waste_kg > 0
    )

def _kg_to_bags_loose(bt: BagType, kg: Decimal) -> tuple[int, Decimal]:
    kg = Decimal(kg)
    if bt.is_loose or bt.weight_per_bag_kg <= 0:
        return 0, kg
    bags = int(kg // bt.weight_per_bag_kg)
    loose = kg - bt.weight_per_bag_kg * bags
    if loose < 0:
        loose = Decimal("0")
    return bags, loose

def _is_loose_processing_line(bt: BagType, line: dict) -> bool:
    return bt.is_loose or (int(line.get("bag_count", 0)) == 0 and Decimal(line.get("loose_kg", 0)) > 0)

def _batch_total_waste_kg(batch: ProcessingBatch) -> Decimal:
    return (
        batch.dust_kg
        + batch.stone_kg
        + batch.sack_weight_waste_kg
        + getattr(batch, "powder_kg", Decimal("0"))
        + batch.miscellaneous_waste_kg
    )

def _pending_line_quantity_kg(db: Session, line: dict) -> Decimal:
    if line.get("quantity_kg") is not None:
        return Decimal(line["quantity_kg"])
    bag_type = db.get(BagType, line["bag_type_id"])
    if not bag_type:
        raise ValueError("Bag type not found")
    return calc_quantity_kg(bag_type, line["bag_count"], Decimal(line["loose_kg"]))

def _waste_has_content(
    dust_kg: Decimal,
    stone_kg: Decimal,
    sack_weight_waste_kg: Decimal,
    powder_kg: Decimal,
    miscellaneous_waste_kg: Decimal,
) -> bool:
    return any(
        v > 0
        for v in (dust_kg, stone_kg, sack_weight_waste_kg, powder_kg, miscellaneous_waste_kg)
    )

def batch_has_content(
    *,
    input_lines: list,
    output_lines: list,
    balance_return_lines: list,
    dust_kg: Decimal,
    stone_kg: Decimal,
    sack_weight_waste_kg: Decimal,
    powder_kg: Decimal,
    miscellaneous_waste_kg: Decimal,
) -> bool:
    if input_lines or output_lines or balance_return_lines:
        return True
    return _waste_has_content(
        dust_kg, stone_kg, sack_weight_waste_kg, powder_kg, miscellaneous_waste_kg
    )

def _parse_input_source(value: str | ProcessingInputSource | None) -> ProcessingInputSource:
    if value == ProcessingInputSource.balance_reprocess or value == "balance_reprocess":
        return ProcessingInputSource.balance_reprocess
    return ProcessingInputSource.fresh

def _is_balance_reprocess(source: ProcessingInputSource | str | None) -> bool:
    return source == ProcessingInputSource.balance_reprocess or source == "balance_reprocess"

def _batch_explicit_waste_kg(batch: ProcessingBatch) -> Decimal:
    return batch.dust_kg + batch.stone_kg + batch.sack_weight_waste_kg + getattr(batch, "powder_kg", Decimal("0"))
