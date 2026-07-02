"""Processing service — allocation."""
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

from app.services.processing.batch_helpers import (
    _active_job_batches,
    _batch_total_waste_kg,
    _is_loose_processing_line,
    _pending_line_quantity_kg,
    _sorted_job_batches,
)
from app.services.processing.constants import (
    DIFFERENT_OWNER_AFTER_OUTPUT_MSG,
    JOB_WORK_OUTPUT_MISSING_MSG,
    MIXED_EXTERNAL_OWNER_MSG,
    MIXED_JOB_NO_MORE_INPUT_MSG,
    MIXED_OWNER_WEIGHTS_COLLAPSED_MSG,
    MIXED_OWNERS_FIRST_BATCH_ONLY_MSG,
    NO_INPUT_FOR_OUTPUT_MSG,
    OUTPUT_ALLOCATION_LOCKED_MSG,
    OUTPUT_ALLOCATION_MODE_REQUIRED_MSG,
    SINGLE_OWNER_NOT_IN_JOB_INPUT_MSG,
)


def _job_output_allocation_mode(job: ProcessingJob) -> ProcessingOutputAllocationMode | None:
    return getattr(job, "output_allocation_mode", None)


def _single_owner_input_only_msg(db: Session | None, owner_key: OwnerKey) -> str:
    label = _owner_key_label(db, owner_key)
    return f"Only {label} may receive more input on this job (100% output allocation)."

def _owner_type_value(owner_type: InventoryOwnerType | str | None) -> str:
    if isinstance(owner_type, InventoryOwnerType):
        return owner_type.value
    return str(owner_type)

def _parse_owner_type(value: str | InventoryOwnerType | None) -> InventoryOwnerType:
    if value == InventoryOwnerType.job_work or value == "job_work":
        return InventoryOwnerType.job_work
    return InventoryOwnerType.owned

def _owner_inventory_args(owner_key: OwnerKey) -> tuple[InventoryOwnerType, int | None]:
    ot, cid = owner_key
    return InventoryOwnerType(ot), cid

def validate_processing_owner_mix(
    db: Session,
    input_lines: list[dict],
    *,
    is_first_input_batch: bool = True,
) -> None:
    owners: set[OwnerKey] = set()
    job_work_customer_ids: set[int] = set()
    for line in input_lines:
        key = owner_key_from_line(line)
        owners.add(key)
        if key[0] == "job_work" and key[1] is not None:
            job_work_customer_ids.add(key[1])
    if len(owners) > 1 and not is_first_input_batch:
        raise ValueError(MIXED_OWNERS_FIRST_BATCH_ONLY_MSG)
    if len(owners) <= 1:
        return
    for cid in job_work_customer_ids:
        customer = db.get(Customer, cid)
        if customer and customer.party_type == CustomerPartyType.external:
            raise ValueError(MIXED_EXTERNAL_OWNER_MSG)

def _job_has_any_output(job: ProcessingJob) -> bool:
    for batch in _active_job_batches(job):
        if batch.output_lines or batch.balance_return_lines or _batch_total_waste_kg(batch) > 0:
            return True
    return False

def _job_input_owner_keys(db: Session, job: ProcessingJob) -> set[OwnerKey]:
    keys: set[OwnerKey] = set()
    for batch in _active_job_batches(job):
        for line in batch.input_lines:
            keys.add(_owner_key_from_stored_input(line))
    return keys

def _job_owner_mode(db: Session, job: ProcessingJob) -> str:
    return "mixed" if len(_job_input_owner_keys(db, job)) >= 2 else "single_owner"

def _job_input_fully_locked(job: ProcessingJob) -> bool:
    return (
        _job_output_allocation_mode(job) == ProcessingOutputAllocationMode.proportional
    )

def _job_allowed_input_owner_key(job: ProcessingJob) -> OwnerKey | None:
    if _job_output_allocation_mode(job) != ProcessingOutputAllocationMode.single_owner:
        return None
    return _job_stored_single_allocation_owner_key(job)

def _batch_will_create_mix(
    db: Session, job: ProcessingJob, pending_input_lines: list[dict]
) -> bool:
    if _job_output_allocation_mode(job) is not None:
        return False
    stored_keys = _job_input_owner_keys(db, job)
    pending_keys = _pending_input_owner_keys(db, pending_input_lines)
    return len(stored_keys | pending_keys) >= 2

def _first_input_batch_number(db: Session, job: ProcessingJob) -> int | None:
    for i, batch in enumerate(_sorted_job_batches(job), start=1):
        if batch.input_lines:
            return i
    return None

def _pending_input_owner_keys(db: Session, input_lines: list[dict]) -> set[OwnerKey]:
    keys: set[OwnerKey] = set()
    for line in input_lines:
        qty = _pending_line_quantity_kg(db, line)
        if qty <= 0:
            continue
        keys.add(owner_key_from_line(line))
    return keys

def _owner_key_label(db: Session | None, owner_key: OwnerKey) -> str:
    ot, cid = owner_key
    if ot == "owned":
        return "Owned"
    if db and cid is not None:
        customer = db.get(Customer, cid)
        if customer:
            return f"Job work · {customer.name}"
    return "Job work"

def _build_input_rules_hint(
    db: Session | None,
    job: ProcessingJob,
    owner_mode: str,
    has_output: bool,
    owner_weights: dict[OwnerKey, Decimal],
) -> str:
    if owner_mode == "mixed":
        if _job_output_allocation_mode(job) == ProcessingOutputAllocationMode.single_owner:
            key = _job_stored_single_allocation_owner_key(job)
            if key:
                label = _owner_key_label(db, key)
                return (
                    f"Mixed job — 100% outputs to {label}. "
                    f"You may add more {label} input only."
                )
        formatted = format_owner_allocation_weights(owner_weights, db)
        parts: list[str] = []
        for w in formatted:
            if w["owner_type"] == "owned":
                parts.append(f"{w['share_pct']}% Owned")
            else:
                name = w.get("customer_name") or "Job work"
                parts.append(f"{w['share_pct']}% Job work · {name}")
        if _job_output_allocation_mode(job) == ProcessingOutputAllocationMode.proportional:
            mix = ", ".join(parts) if parts else "input mix"
            return f"Mixed job — input closed. Outputs split proportionally by: {mix}."
        if parts:
            return f"Mixed job — choose output allocation when adding the second owner. Input mix: {', '.join(parts)}."
        return "Mixed job — choose output allocation when adding the second owner."
    keys = _job_input_owner_keys(db, job) if db is not None else set(owner_weights.keys())
    if has_output and keys:
        label = _owner_key_label(db, next(iter(keys)))
        return f"Locked to {label}. Only same-owner input allowed."
    return (
        "Single owner. You may add more input from the same owner, "
        "or one batch from a different owner before any output."
    )

def _validate_input_batch_allowed(
    db: Session,
    job: ProcessingJob,
    pending_input_lines: list[dict],
) -> None:
    if not pending_input_lines:
        return

    stored_keys = _job_input_owner_keys(db, job)
    is_first_input_batch = len(stored_keys) == 0

    validate_processing_owner_mix(
        db, pending_input_lines, is_first_input_batch=is_first_input_batch
    )

    pending_keys = _pending_input_owner_keys(db, pending_input_lines)
    if not pending_keys:
        return

    has_output = _job_has_any_output(job)

    if len(stored_keys) >= 2:
        if _job_input_fully_locked(job):
            raise ValueError(MIXED_JOB_NO_MORE_INPUT_MSG)
        allowed_key = _job_allowed_input_owner_key(job)
        if allowed_key is None:
            raise ValueError(MIXED_JOB_NO_MORE_INPUT_MSG)
        for key in pending_keys:
            if key != allowed_key:
                raise ValueError(_single_owner_input_only_msg(db, allowed_key))

    if len(stored_keys) == 1:
        stored_key = next(iter(stored_keys))
        if has_output and pending_keys != {stored_key}:
            raise ValueError(DIFFERENT_OWNER_AFTER_OUTPUT_MSG)

def _owner_weights_from_inputs(db: Session, input_lines: list[dict]) -> dict[OwnerKey, Decimal]:
    weights: dict[OwnerKey, Decimal] = {}
    for line in input_lines:
        qty = _pending_line_quantity_kg(db, line)
        if qty <= 0:
            continue
        key = owner_key_from_line(line)
        weights[key] = weights.get(key, Decimal("0")) + qty
    return weights

def _owner_key_from_stored_input(line: ProcessingInputLine) -> OwnerKey:
    if _owner_type_value(line.owner_type) == "job_work":
        if line.customer_id is None:
            raise ValueError("job_work processing input line missing customer_id")
        return ("job_work", line.customer_id)
    return ("owned", None)

def _owner_weights_for_job_allocation(
    db: Session,
    job: ProcessingJob,
    pending_input_lines: list[dict],
) -> dict[OwnerKey, Decimal]:
    """Cumulative input kg per owner across all job batches plus pending lines in this submit."""
    weights: dict[OwnerKey, Decimal] = {}
    stored_lines = db.scalars(
        select(ProcessingInputLine)
        .join(ProcessingBatch, ProcessingInputLine.batch_id == ProcessingBatch.id)
        .where(ProcessingBatch.job_id == job.id, ProcessingBatch.voided_at.is_(None))
    ).all()
    for line in stored_lines:
        key = _owner_key_from_stored_input(line)
        weights[key] = weights.get(key, Decimal("0")) + line.quantity_kg
    for key, qty in _owner_weights_from_inputs(db, pending_input_lines).items():
        weights[key] = weights.get(key, Decimal("0")) + qty

    stored_owner_types = {_owner_type_value(line.owner_type) for line in stored_lines}
    if (
        "owned" in stored_owner_types
        and "job_work" in stored_owner_types
        and len(weights) == 1
    ):
        raise ValueError(MIXED_OWNER_WEIGHTS_COLLAPSED_MSG)

    return weights

def _owner_weights_from_loaded_job(job: ProcessingJob) -> dict[OwnerKey, Decimal]:
    weights: dict[OwnerKey, Decimal] = {}
    for batch in _active_job_batches(job):
        for line in batch.input_lines:
            key = _owner_key_from_stored_input(line)
            weights[key] = weights.get(key, Decimal("0")) + line.quantity_kg
    return weights

def _owner_key_from_allocation_fields(
    owner_type: str, customer_id: int | None
) -> OwnerKey:
    if owner_type == "job_work":
        return ("job_work", customer_id)
    return ("owned", None)

def _job_stored_single_allocation_owner_key(job: ProcessingJob) -> OwnerKey | None:
    if _job_output_allocation_mode(job) != ProcessingOutputAllocationMode.single_owner:
        return None
    if job.single_allocation_owner_type is None:
        return None
    ot = _owner_type_value(job.single_allocation_owner_type)
    return _owner_key_from_allocation_fields(ot, job.single_allocation_customer_id)

def _default_single_allocation_owner(weights: dict[OwnerKey, Decimal]) -> OwnerKey:
    if not weights:
        raise ValueError(SINGLE_OWNER_NOT_IN_JOB_INPUT_MSG)

    def sort_key(item: tuple[OwnerKey, Decimal]) -> tuple[Decimal, int, int]:
        key, kg = item
        ot, cid = key
        owned_priority = 1 if ot == "owned" else 0
        return (kg, owned_priority, cid or 0)

    return max(weights.items(), key=sort_key)[0]

def _allocation_body_conflicts_stored(
    job: ProcessingJob,
    *,
    output_allocation_mode: str | None,
    single_allocation_owner_type: str | None,
    single_allocation_customer_id: int | None,
) -> bool:
    if _job_output_allocation_mode(job) is None:
        return False
    stored_mode = _job_output_allocation_mode(job).value
    if output_allocation_mode is not None and output_allocation_mode != stored_mode:
        return True
    if stored_mode == "single_owner":
        stored_key = _job_stored_single_allocation_owner_key(job)
        if single_allocation_owner_type is not None:
            body_key = _owner_key_from_allocation_fields(
                single_allocation_owner_type, single_allocation_customer_id
            )
            if body_key != stored_key:
                return True
    elif stored_mode == "proportional":
        if single_allocation_owner_type is not None or single_allocation_customer_id is not None:
            return True
    return False

def _persist_output_allocation_mode(
    job: ProcessingJob,
    owner_weights: dict[OwnerKey, Decimal],
    *,
    output_allocation_mode: str,
    single_allocation_owner_type: str | None,
    single_allocation_customer_id: int | None,
) -> tuple[ProcessingOutputAllocationMode, OwnerKey | None]:
    if output_allocation_mode == "proportional":
        job.output_allocation_mode = ProcessingOutputAllocationMode.proportional
        job.single_allocation_owner_type = None
        job.single_allocation_customer_id = None
        return ProcessingOutputAllocationMode.proportional, None

    if output_allocation_mode == "single_owner":
        if single_allocation_owner_type:
            key = _owner_key_from_allocation_fields(
                single_allocation_owner_type, single_allocation_customer_id
            )
        else:
            key = _default_single_allocation_owner(owner_weights)
        if key not in owner_weights or owner_weights[key] <= 0:
            raise ValueError(SINGLE_OWNER_NOT_IN_JOB_INPUT_MSG)
        ot, cid = key
        job.output_allocation_mode = ProcessingOutputAllocationMode.single_owner
        job.single_allocation_owner_type = InventoryOwnerType(ot)
        job.single_allocation_customer_id = cid if ot == "job_work" else None
        return ProcessingOutputAllocationMode.single_owner, key

    raise ValueError(OUTPUT_ALLOCATION_MODE_REQUIRED_MSG)

def _resolve_and_lock_allocation_on_input(
    db: Session,
    job: ProcessingJob,
    pending_input_lines: list[dict],
    *,
    output_allocation_mode: str | None,
    single_allocation_owner_type: str | None,
    single_allocation_customer_id: int | None,
) -> None:
    if _job_output_allocation_mode(job) is not None:
        if _allocation_body_conflicts_stored(
            job,
            output_allocation_mode=output_allocation_mode,
            single_allocation_owner_type=single_allocation_owner_type,
            single_allocation_customer_id=single_allocation_customer_id,
        ):
            raise ValueError(OUTPUT_ALLOCATION_LOCKED_MSG)
        return

    if not _batch_will_create_mix(db, job, pending_input_lines):
        return

    if output_allocation_mode is None:
        raise ValueError(OUTPUT_ALLOCATION_MODE_REQUIRED_MSG)

    owner_weights = _owner_weights_for_job_allocation(db, job, pending_input_lines)
    _persist_output_allocation_mode(
        job,
        owner_weights,
        output_allocation_mode=output_allocation_mode,
        single_allocation_owner_type=single_allocation_owner_type,
        single_allocation_customer_id=single_allocation_customer_id,
    )

def _reject_conflicting_allocation_body(
    job: ProcessingJob,
    *,
    output_allocation_mode: str | None,
    single_allocation_owner_type: str | None,
    single_allocation_customer_id: int | None,
) -> None:
    if _job_output_allocation_mode(job) is None:
        return
    if _allocation_body_conflicts_stored(
        job,
        output_allocation_mode=output_allocation_mode,
        single_allocation_owner_type=single_allocation_owner_type,
        single_allocation_customer_id=single_allocation_customer_id,
    ):
        raise ValueError(OUTPUT_ALLOCATION_LOCKED_MSG)

def _effective_owner_weights_for_output(
    job: ProcessingJob,
    db: Session,
    pending_input_lines: list[dict],
) -> dict[OwnerKey, Decimal]:
    cumulative = _owner_weights_for_job_allocation(db, job, pending_input_lines)
    if _job_owner_mode(db, job) == "single_owner":
        return cumulative
    if _job_output_allocation_mode(job) == ProcessingOutputAllocationMode.single_owner:
        single_owner_key = _job_stored_single_allocation_owner_key(job)
        if single_owner_key:
            total = sum(cumulative.values())
            return {single_owner_key: total}
    return cumulative

def _build_output_allocation_hint(
    db: Session | None,
    job: ProcessingJob,
    owner_mode: str,
    owner_weights: dict[OwnerKey, Decimal],
) -> str | None:
    if owner_mode != "mixed" or _job_output_allocation_mode(job) is None:
        return None
    if _job_output_allocation_mode(job) == ProcessingOutputAllocationMode.single_owner:
        key = _job_stored_single_allocation_owner_key(job)
        if not key:
            return None
        label = _owner_key_label(db, key)
        return f"Output allocation: 100% {label}"
    formatted = format_owner_allocation_weights(owner_weights, db)
    if not formatted:
        return "Output allocation: proportional"
    parts: list[str] = []
    for w in formatted:
        if w["owner_type"] == "owned":
            parts.append(f"{w['share_pct']}% Owned")
        else:
            name = w.get("customer_name") or "Job work"
            parts.append(f"{w['share_pct']}% Job work · {name}")
    return f"Output allocation: proportional ({', '.join(parts)})"

def format_owner_allocation_weights(
    weights: dict[OwnerKey, Decimal],
    db: Session | None = None,
) -> list[dict]:
    total = sum(weights.values())
    rows: list[dict] = []
    for (owner_type, customer_id), input_kg in weights.items():
        if input_kg <= 0:
            continue
        customer_name = None
        if customer_id is not None and db is not None:
            customer = db.get(Customer, customer_id)
            customer_name = customer.name if customer else None
        share_pct = (
            (input_kg / total * Decimal("100")).quantize(Decimal("0.01"))
            if total > 0
            else Decimal("0")
        )
        rows.append(
            {
                "owner_type": owner_type,
                "customer_id": customer_id,
                "customer_name": customer_name,
                "input_kg": input_kg,
                "share_pct": share_pct,
            }
        )
    rows.sort(key=lambda r: (0 if r["owner_type"] == "owned" else 1, r["customer_id"] or 0))
    return rows

def _split_line_kg_across_owners(
    total_kg: Decimal, weights: dict[OwnerKey, Decimal]
) -> list[tuple[OwnerKey, Decimal]]:
    if not weights:
        return []
    if len(weights) == 1:
        key = next(iter(weights))
        return [(key, total_kg)]
    split = proportional_split_kg(total_kg, weights)
    return [(k, split[k]) for k in split if split[k] > 0]

def _split_processing_line_across_owners(
    db: Session,
    line: dict,
    bt: BagType,
    owner_weights: dict[OwnerKey, Decimal],
) -> list[tuple[OwnerKey, int, Decimal]]:
    """Return (owner_key, bag_count, loose_kg) slices for one output or balance line."""
    bag_count = int(line["bag_count"])
    loose_kg = Decimal(line["loose_kg"])

    if not owner_weights or len(owner_weights) <= 1:
        key = next(iter(owner_weights)) if owner_weights else ("owned", None)
        return [(key, bag_count, loose_kg)]

    if _is_loose_processing_line(bt, line):
        total_kg = _pending_line_quantity_kg(db, line)
        return [
            (owner_key, 0, slice_kg)
            for owner_key, slice_kg in _split_line_kg_across_owners(total_kg, owner_weights)
            if slice_kg > 0
        ]

    bag_splits = proportional_split_bags(bag_count, owner_weights)
    loose_splits = (
        proportional_split_kg(loose_kg, owner_weights)
        if loose_kg > 0
        else {k: Decimal("0") for k in owner_weights}
    )
    result: list[tuple[OwnerKey, int, Decimal]] = []
    for owner_key in owner_weights:
        bags = bag_splits.get(owner_key, 0)
        loose = loose_splits.get(owner_key, Decimal("0"))
        if bags > 0 or loose > 0:
            result.append((owner_key, bags, loose))
    return result

def _owner_key_from_stored_owner_line(line) -> OwnerKey:
    if _owner_type_value(line.owner_type) == "job_work":
        if line.customer_id is None:
            raise ValueError("job_work processing line missing customer_id")
        return ("job_work", line.customer_id)
    return ("owned", None)
