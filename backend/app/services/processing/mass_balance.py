"""Processing service — mass balance."""
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
from app.services.processing.batch_helpers import (
    _active_job_batches,
    _batch_total_waste_kg,
    _is_balance_reprocess,
    _pending_line_quantity_kg,
)
from app.services.processing.constants import (
    BALANCE_REPROCESS_NO_RETURN_MSG,
    BALANCE_REPROCESS_NO_STOCK_MSG,
    PROCESSING_OUTPUT_TOLERANCE_KG,
)

def compute_job_fresh_input_kg(
    job: ProcessingJob,
    *,
    pending_input_lines: list[dict] | None = None,
    db: Session | None = None,
) -> Decimal:
    """Sum From-stock input only (excludes balance_reprocess). Used for Fresh-in reporting."""
    total = Decimal("0")
    for batch in _active_job_batches(job):
        for line in batch.input_lines:
            if not _is_balance_reprocess(line.input_source):
                total += line.quantity_kg
    if pending_input_lines and db:
        for line in pending_input_lines:
            if not _is_balance_reprocess(line.get("input_source")):
                total += _pending_line_quantity_kg(db, line)
    return total


def compute_job_mass_balance_input_kg(
    job: ProcessingJob,
    *,
    pending_input_lines: list[dict] | None = None,
    db: Session | None = None,
) -> Decimal:
    """Fresh + balance_reprocess — same 'in' side as misc / allowance.

    Balance return counts as outflow, so reprocess of that material must count as input
    or allowance stays short by the reprocess weight.
    """
    total = Decimal("0")
    for batch in _active_job_batches(job):
        for line in batch.input_lines:
            total += line.quantity_kg
    if pending_input_lines and db:
        for line in pending_input_lines:
            total += _pending_line_quantity_kg(db, line)
    return total


def _sum_output_balance_kg_from_batches(job: ProcessingJob) -> Decimal:
    total = Decimal("0")
    for batch in _active_job_batches(job):
        for line in batch.output_lines:
            total += line.quantity_kg
        for line in batch.balance_return_lines:
            total += line.quantity_kg
    return total

def compute_job_outflow_kg(
    job: ProcessingJob,
    *,
    pending_batch: dict | None = None,
    db: Session | None = None,
) -> Decimal:
    total = Decimal("0")
    for batch in _active_job_batches(job):
        total += _batch_total_waste_kg(batch)
        for line in batch.output_lines:
            total += line.quantity_kg
        for line in batch.balance_return_lines:
            total += line.quantity_kg
    if pending_batch:
        total += Decimal(pending_batch.get("dust_kg", 0))
        total += Decimal(pending_batch.get("stone_kg", 0))
        total += Decimal(pending_batch.get("sack_weight_waste_kg", 0))
        total += Decimal(pending_batch.get("powder_kg", 0))
        total += Decimal(pending_batch.get("miscellaneous_waste_kg", 0))
        if db:
            for line in pending_batch.get("output_lines", []):
                total += _pending_line_quantity_kg(db, line)
            for line in pending_batch.get("balance_return_lines", []):
                total += _pending_line_quantity_kg(db, line)
    return total

def _sum_output_balance_kg(
    job: ProcessingJob,
    *,
    pending_output_lines: list[dict] | None = None,
    pending_balance_return_lines: list[dict] | None = None,
    db: Session | None = None,
) -> Decimal:
    total = _sum_output_balance_kg_from_batches(job)
    if db:
        for line in pending_output_lines or []:
            total += _pending_line_quantity_kg(db, line)
        for line in pending_balance_return_lines or []:
            total += _pending_line_quantity_kg(db, line)
    return total

def validate_processing_mass_balance(
    job: ProcessingJob,
    *,
    pending_input_lines: list[dict],
    pending_output_lines: list[dict],
    pending_balance_return_lines: list[dict],
    pending_waste_fields: dict,
    db: Session,
) -> None:
    fresh_kg = compute_job_fresh_input_kg(job, pending_input_lines=pending_input_lines, db=db)
    output_balance_kg = _sum_output_balance_kg(
        job,
        pending_output_lines=pending_output_lines,
        pending_balance_return_lines=pending_balance_return_lines,
        db=db,
    )
    if output_balance_kg > 0 and fresh_kg == 0:
        raise ValueError(
            "Record fresh input from stock before submitting output or balance return."
        )

    pending_batch = {
        "output_lines": pending_output_lines,
        "balance_return_lines": pending_balance_return_lines,
        **pending_waste_fields,
    }
    input_kg = compute_job_mass_balance_input_kg(
        job, pending_input_lines=pending_input_lines, db=db
    )
    outflow_kg = compute_job_outflow_kg(job, pending_batch=pending_batch, db=db)
    max_outflow = input_kg + PROCESSING_OUTPUT_TOLERANCE_KG
    if outflow_kg > max_outflow:
        raise ValueError(
            f"Total outflow ({outflow_kg} kg) exceeds job input ({input_kg} kg) "
            f"(fresh + reprocess) plus the {PROCESSING_OUTPUT_TOLERANCE_KG} kg allowance."
        )

def compute_job_committed_balance_return_kg(job: ProcessingJob) -> Decimal:
    total = Decimal("0")
    for batch in _active_job_batches(job):
        for line in batch.balance_return_lines:
            total += line.quantity_kg
    return total

def compute_job_committed_balance_reprocess_kg(job: ProcessingJob) -> Decimal:
    total = Decimal("0")
    for batch in _active_job_batches(job):
        for line in batch.input_lines:
            if _is_balance_reprocess(line.input_source):
                total += line.quantity_kg
    return total

def compute_job_available_reprocess_kg(job: ProcessingJob) -> Decimal:
    """max(0, committed balance return − committed balance reprocess on this job)."""
    available = (
        compute_job_committed_balance_return_kg(job)
        - compute_job_committed_balance_reprocess_kg(job)
    )
    return max(available, Decimal("0"))

def _pending_reprocess_kg(db: Session, pending_input_lines: list[dict]) -> Decimal:
    total = Decimal("0")
    for line in pending_input_lines:
        if _is_balance_reprocess(line.get("input_source")):
            total += _pending_line_quantity_kg(db, line)
    return total

def _reprocess_line_has_physical_stock(
    db: Session,
    job: ProcessingJob,
    line: dict,
) -> bool:
    bt = db.get(BagType, line["bag_type_id"])
    if not bt:
        raise ValueError("Bag type not found")
    owner_type, customer_id = _owner_inventory_args(owner_key_from_line(line))
    inv = _processing.get_inventory_row(
        db,
        job.input_product_id,
        job.input_brand_id,
        line["location_id"],
        line["bag_type_id"],
        owner_type=owner_type,
        customer_id=customer_id,
    )
    if not inv:
        return False
    if bt.is_loose:
        return inv.loose_kg >= Decimal(line["loose_kg"])
    return inv.bag_count >= line["bag_count"]

def validate_balance_reprocess(
    job: ProcessingJob,
    pending_input_lines: list[dict],
    db: Session,
) -> None:
    reprocess_lines = [
        ln for ln in pending_input_lines if _is_balance_reprocess(ln.get("input_source"))
    ]
    if not reprocess_lines:
        return

    available = compute_job_available_reprocess_kg(job)
    if available <= 0:
        raise ValueError(BALANCE_REPROCESS_NO_RETURN_MSG)

    pending_kg = _pending_reprocess_kg(db, pending_input_lines)
    if pending_kg > available:
        raise ValueError(
            f"Reprocess ({pending_kg} kg) exceeds unclean balance available from this job "
            f"({available} kg)"
        )

    for line in reprocess_lines:
        if not _reprocess_line_has_physical_stock(db, job, line):
            raise ValueError(BALANCE_REPROCESS_NO_STOCK_MSG)
