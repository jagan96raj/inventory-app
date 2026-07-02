"""Processing service — serialization."""
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

from app.services.processing.allocation import (
    _build_input_rules_hint,
    _build_output_allocation_hint,
    _job_allowed_input_owner_key,
    _job_has_any_output,
    _job_input_fully_locked,
    _job_owner_mode,
    _job_stored_single_allocation_owner_key,
    _owner_key_from_stored_input,
    _owner_type_value,
    _owner_weights_from_loaded_job,
    format_owner_allocation_weights,
)
from app.services.processing.batch_helpers import (
    _active_job_batches,
    _batch_explicit_waste_kg,
    _is_balance_reprocess,
)
from app.services.processing.mass_balance import compute_job_available_reprocess_kg

def _batch_load_options():
    return (
        joinedload(ProcessingJob.input_product),
        joinedload(ProcessingJob.input_brand),
        joinedload(ProcessingJob.single_allocation_customer),
        joinedload(ProcessingJob.batches)
        .joinedload(ProcessingBatch.input_lines)
        .joinedload(ProcessingInputLine.location),
        joinedload(ProcessingJob.batches)
        .joinedload(ProcessingBatch.input_lines)
        .joinedload(ProcessingInputLine.bag_type),
        joinedload(ProcessingJob.batches)
        .joinedload(ProcessingBatch.output_lines)
        .joinedload(ProcessingOutputLine.brand),
        joinedload(ProcessingJob.batches)
        .joinedload(ProcessingBatch.output_lines)
        .joinedload(ProcessingOutputLine.location),
        joinedload(ProcessingJob.batches)
        .joinedload(ProcessingBatch.output_lines)
        .joinedload(ProcessingOutputLine.bag_type),
        joinedload(ProcessingJob.batches)
        .joinedload(ProcessingBatch.balance_return_lines)
        .joinedload(ProcessingBalanceReturnLine.location),
        joinedload(ProcessingJob.batches)
        .joinedload(ProcessingBatch.balance_return_lines)
        .joinedload(ProcessingBalanceReturnLine.bag_type),
        joinedload(ProcessingJob.batches).joinedload(ProcessingBatch.waste_allocations),
        joinedload(ProcessingJob.batches).joinedload(ProcessingBatch.powder_brand),
        joinedload(ProcessingJob.batches).joinedload(ProcessingBatch.powder_location),
        joinedload(ProcessingJob.batches).joinedload(ProcessingBatch.powder_bag_type),
    )

def load_processing_job(db: Session, job_id: int) -> ProcessingJob:
    row = db.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .options(*_batch_load_options())
        .execution_options(populate_existing=True)
    ).unique().one_or_none()
    if not row:
        raise ValueError("Processing job not found")
    return row

def compute_processing_summary(job: ProcessingJob) -> dict:
    total_fresh_input_kg = Decimal("0")
    fresh_input_bags = 0
    total_balance_reprocess_kg = Decimal("0")
    total_balance_return_kg = Decimal("0")
    total_waste_kg = Decimal("0")
    total_output_kg = Decimal("0")
    by_brand: dict[int, dict] = {}
    batches = _active_job_batches(job)

    for batch in batches:
        total_waste_kg += _batch_explicit_waste_kg(batch)
        for line in batch.input_lines:
            if _is_balance_reprocess(line.input_source):
                total_balance_reprocess_kg += line.quantity_kg
            else:
                total_fresh_input_kg += line.quantity_kg
                bag_type = line.bag_type
                if bag_type and not bag_type.is_loose:
                    fresh_input_bags += line.bag_count
        for line in batch.balance_return_lines:
            total_balance_return_kg += line.quantity_kg
        for line in batch.output_lines:
            bid = line.brand_id
            if bid not in by_brand:
                by_brand[bid] = {
                    "brand_id": bid,
                    "brand_name": line.brand.name if line.brand else None,
                    "quantity_kg": Decimal("0"),
                    "bag_count": 0,
                }
            by_brand[bid]["quantity_kg"] += line.quantity_kg
            by_brand[bid]["bag_count"] += line.bag_count
            total_output_kg += line.quantity_kg

    net_balance_kg = total_balance_return_kg - total_balance_reprocess_kg
    job_available_reprocess_kg = max(net_balance_kg, Decimal("0"))
    output_by_brand = sorted(by_brand.values(), key=lambda x: (x["brand_name"] or "", x["brand_id"]))
    total_misc_kg = (
        total_fresh_input_kg
        + total_balance_reprocess_kg
        - total_output_kg
        - total_balance_return_kg
        - total_waste_kg
    )
    total_loss_kg = total_waste_kg + total_misc_kg

    return {
        "total_fresh_input_kg": total_fresh_input_kg,
        "fresh_input_bags": fresh_input_bags,
        "total_balance_reprocess_kg": total_balance_reprocess_kg,
        "total_balance_return_kg": total_balance_return_kg,
        "net_balance_kg": net_balance_kg,
        "job_available_reprocess_kg": job_available_reprocess_kg,
        "output_by_brand": output_by_brand,
        "total_waste_kg": total_waste_kg,
        "total_misc_kg": total_misc_kg,
        "total_loss_kg": total_loss_kg,
        "batch_count": len(batches),
        "in_process_kg": Decimal("0"),
    }

def fetch_processing_list_summaries(db: Session, job_ids: list[int]) -> dict[int, dict]:
    """Aggregate batch_count and total_output_kg for list view (active batches only)."""
    if not job_ids:
        return {}

    summaries: dict[int, dict] = {
        jid: {"batch_count": 0, "total_output_kg": Decimal("0")} for jid in job_ids
    }

    batch_rows = db.execute(
        select(ProcessingBatch.job_id, func.count(ProcessingBatch.id))
        .where(ProcessingBatch.job_id.in_(job_ids))
        .where(ProcessingBatch.voided_at.is_(None))
        .group_by(ProcessingBatch.job_id)
    ).all()
    for job_id, count in batch_rows:
        summaries[job_id]["batch_count"] = int(count)

    output_rows = db.execute(
        select(
            ProcessingBatch.job_id,
            func.coalesce(func.sum(ProcessingOutputLine.quantity_kg), Decimal("0")),
        )
        .join(ProcessingOutputLine, ProcessingOutputLine.batch_id == ProcessingBatch.id)
        .where(ProcessingBatch.job_id.in_(job_ids))
        .where(ProcessingBatch.voided_at.is_(None))
        .group_by(ProcessingBatch.job_id)
    ).all()
    for job_id, total_kg in output_rows:
        summaries[job_id]["total_output_kg"] = total_kg

    return summaries

def serialize_processing_job_list_item(
    row: ProcessingJob,
    db: Session,
    *,
    summary: dict | None = None,
) -> dict:
    if summary is None:
        summary = fetch_processing_list_summaries(db, [row.id]).get(
            row.id, {"batch_count": 0, "total_output_kg": Decimal("0")}
        )
    return {
        "id": row.id,
        "input_product_id": row.input_product_id,
        "input_product_name": row.input_product.product_name if row.input_product else None,
        "input_brand_id": row.input_brand_id,
        "input_brand_name": row.input_brand.name if row.input_brand else None,
        "status": row.status.value,
        "opened_at": row.opened_at,
        "completed_at": row.completed_at,
        "batches": [],
        "summary": summary,
    }

def serialize_processing_job(
    row: ProcessingJob,
    *,
    include_batches: bool = True,
    db: Session | None = None,
) -> dict:
    batches = []
    if include_batches and row.batches:
        for batch in sorted(row.batches, key=lambda b: (b.operation_at, b.id)):
            batches.append(
                {
                    "id": batch.id,
                    "operation_at": batch.operation_at,
                    "voided_at": batch.voided_at,
                    "dust_kg": batch.dust_kg,
                    "stone_kg": batch.stone_kg,
                    "sack_weight_waste_kg": batch.sack_weight_waste_kg,
                    "powder_kg": batch.powder_kg,
                    "powder_brand_id": batch.powder_brand_id,
                    "powder_brand_name": batch.powder_brand.name if batch.powder_brand else None,
                    "powder_location_id": batch.powder_location_id,
                    "powder_location_name": batch.powder_location.name if batch.powder_location else None,
                    "powder_bag_type_id": batch.powder_bag_type_id,
                    "powder_bag_type_name": batch.powder_bag_type.name if batch.powder_bag_type else None,
                    "powder_bag_type_is_loose": batch.powder_bag_type.is_loose if batch.powder_bag_type else None,
                    "powder_bag_count": batch.powder_bag_count,
                    "powder_loose_kg": batch.powder_loose_kg,
                    "miscellaneous_waste_kg": batch.miscellaneous_waste_kg,
                    "input_lines": [
                        {
                            "id": ln.id,
                            "location_id": ln.location_id,
                            "location_name": ln.location.name if ln.location else None,
                            "bag_type_id": ln.bag_type_id,
                            "bag_type_name": ln.bag_type.name if ln.bag_type else None,
                            "bag_type_is_loose": ln.bag_type.is_loose if ln.bag_type else None,
                            "bag_count": ln.bag_count,
                            "loose_kg": ln.loose_kg,
                            "quantity_kg": ln.quantity_kg,
                            "line_index": ln.line_index,
                            "input_source": ln.input_source.value,
                            "owner_type": _owner_type_value(ln.owner_type),
                            "customer_id": ln.customer_id,
                            "job_work_order_id": ln.job_work_order_id,
                        }
                        for ln in sorted(batch.input_lines, key=lambda x: x.line_index)
                    ],
                    "output_lines": [
                        {
                            "id": ln.id,
                            "brand_id": ln.brand_id,
                            "brand_name": ln.brand.name if ln.brand else None,
                            "location_id": ln.location_id,
                            "location_name": ln.location.name if ln.location else None,
                            "bag_type_id": ln.bag_type_id,
                            "bag_type_name": ln.bag_type.name if ln.bag_type else None,
                            "bag_count": ln.bag_count,
                            "loose_kg": ln.loose_kg,
                            "quantity_kg": ln.quantity_kg,
                            "line_index": ln.line_index,
                            "owner_type": _owner_type_value(ln.owner_type),
                            "customer_id": ln.customer_id,
                        }
                        for ln in sorted(batch.output_lines, key=lambda x: x.line_index)
                    ],
                    "balance_return_lines": [
                        {
                            "id": ln.id,
                            "location_id": ln.location_id,
                            "location_name": ln.location.name if ln.location else None,
                            "bag_type_id": ln.bag_type_id,
                            "bag_type_name": ln.bag_type.name if ln.bag_type else None,
                            "bag_count": ln.bag_count,
                            "loose_kg": ln.loose_kg,
                            "quantity_kg": ln.quantity_kg,
                            "line_index": ln.line_index,
                            "owner_type": _owner_type_value(ln.owner_type),
                            "customer_id": ln.customer_id,
                        }
                        for ln in sorted(batch.balance_return_lines, key=lambda x: x.line_index)
                    ],
                    "waste_allocations": [
                        {
                            "owner_type": _owner_type_value(wa.owner_type),
                            "customer_id": wa.customer_id,
                            "dust_kg": wa.dust_kg,
                            "stone_kg": wa.stone_kg,
                            "sack_weight_waste_kg": wa.sack_weight_waste_kg,
                            "powder_kg": wa.powder_kg,
                            "miscellaneous_waste_kg": wa.miscellaneous_waste_kg,
                        }
                        for wa in batch.waste_allocations or []
                    ],
                }
            )

    owner_weights = _owner_weights_from_loaded_job(row)
    owner_mode = (
        _job_owner_mode(db, row) if db is not None else ("mixed" if len(owner_weights) >= 2 else "single_owner")
    )
    has_output = _job_has_any_output(row)
    input_locked = (
        owner_mode == "mixed" and _job_input_fully_locked(row)
        if owner_mode == "mixed"
        else False
    )
    allowed_input_key = _job_allowed_input_owner_key(row) if owner_mode == "mixed" else None
    input_allowed_owner = None
    if allowed_input_key is not None:
        ot, cid = allowed_input_key
        cust_name = None
        if cid is not None and db is not None:
            customer = db.get(Customer, cid)
            cust_name = customer.name if customer else None
        input_allowed_owner = {
            "owner_type": ot,
            "customer_id": cid,
            "customer_name": cust_name,
        }
    input_rules_hint = _build_input_rules_hint(db, row, owner_mode, has_output, owner_weights)
    single_customer_name = None
    if row.single_allocation_customer is not None:
        single_customer_name = row.single_allocation_customer.name
    elif row.single_allocation_customer_id is not None and db is not None:
        customer = db.get(Customer, row.single_allocation_customer_id)
        single_customer_name = customer.name if customer else None
    return {
        "id": row.id,
        "input_product_id": row.input_product_id,
        "input_product_name": row.input_product.product_name if row.input_product else None,
        "input_brand_id": row.input_brand_id,
        "input_brand_name": row.input_brand.name if row.input_brand else None,
        "status": row.status.value,
        "opened_at": row.opened_at,
        "completed_at": row.completed_at,
        "batches": batches,
        "summary": compute_processing_summary(row),
        "owner_mode": owner_mode,
        "input_locked": input_locked,
        "input_allowed_owner": input_allowed_owner,
        "has_output": has_output,
        "input_rules_hint": input_rules_hint,
        "owner_allocation_weights": format_owner_allocation_weights(owner_weights, db),
        "output_allocation_mode": (
            row.output_allocation_mode.value if row.output_allocation_mode else None
        ),
        "single_allocation_owner_type": (
            _owner_type_value(row.single_allocation_owner_type)
            if row.single_allocation_owner_type is not None
            else None
        ),
        "single_allocation_customer_id": row.single_allocation_customer_id,
        "single_allocation_customer_name": single_customer_name,
        "output_allocation_locked": (
            owner_mode == "mixed" and row.output_allocation_mode is not None
        ),
        "output_allocation_hint": _build_output_allocation_hint(db, row, owner_mode, owner_weights),
    }
