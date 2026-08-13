"""Processing service — batch."""
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.tenant import assert_entity_company
from app.models.entities import (
    BagType,
    BookSettings,
    Brand,
    Customer,
    CustomerPartyType,
    InventoryOwnerType,
    Location,
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
from app.services.operations import OPERATION_VOID_INSUFFICIENT_STOCK_MSG, _void_line_quantity_kg
from app.services.inventory_lock import (
    inventory_row_key,
    inventory_sku_key,
    lock_inventory_product_brand_owner_rows,
    lock_inventory_rows,
    lock_inventory_sku_rows,
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

from app.services.processing.allocation import (
    _effective_owner_weights_for_output,
    _job_has_any_output,
    _job_input_owner_keys,
    _job_owner_mode,
    _owner_inventory_args,
    _owner_key_from_stored_input,
    _owner_key_from_stored_owner_line,
    _owner_type_value,
    _owner_weights_for_job_allocation,
    _reject_conflicting_allocation_body,
    _resolve_and_lock_allocation_on_input,
    _split_processing_line_across_owners,
    _job_output_allocation_mode,
    _validate_input_batch_allowed,
)
from app.services.processing.batch_helpers import (
    _batch_has_outflow,
    _is_balance_reprocess,
    _kg_to_bags_loose,
    _parse_input_source,
    batch_has_content,
)
from app.services.processing.constants import (
    BALANCE_REPROCESS_NO_STOCK_MSG,
    JOB_WORK_OUTPUT_MISSING_MSG,
    LATER_REPROCESS_VOID_MSG,
    NO_INPUT_FOR_OUTPUT_MSG,
    OUTPUT_ALLOCATION_MODE_REQUIRED_MSG,
)
from app.services.processing.deps import OPERATION_ALREADY_VOIDED_MSG
from app.services.processing.mass_balance import (
    validate_balance_reprocess,
    validate_processing_mass_balance,
)
from app.services.processing.powder import (
    _allocate_powder_to_owners,
    _batch_powder_inventory_tuple,
    _ensure_waste_allocation_row,
    _resolve_powder_for_batch,
    _store_powder_line_on_batch,
    _validate_no_powder_output_lines,
)

def _get_open_job(db: Session, job_id: int) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise ValueError("Processing job not found")
    if job.status != ProcessingJobStatus.open:
        raise ValueError("Processing job is not open")
    return job

def create_job(
    db: Session, *, company_id: int = 1, input_product_id: int, input_brand_id: int
) -> ProcessingJob:
    product = db.get(Product, input_product_id)
    brand = db.get(Brand, input_brand_id)
    if product is not None:
        assert_entity_company(product, company_id, "Product")
    if brand is not None:
        assert_entity_company(brand, company_id, "Brand")
    existing = db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.company_id == company_id,
            ProcessingJob.input_product_id == input_product_id,
            ProcessingJob.input_brand_id == input_brand_id,
            ProcessingJob.status == ProcessingJobStatus.open,
        )
    )
    if existing:
        raise ValueError("An open processing job already exists for this product and brand")

    job = ProcessingJob(
        company_id=company_id,
        input_product_id=input_product_id,
        input_brand_id=input_brand_id,
        status=ProcessingJobStatus.open,
    )
    db.add(job)
    db.commit()
    return _processing.load_processing_job(db, job.id)

def _apply_batch(
    db: Session,
    job: ProcessingJob,
    *,
    input_lines: list[dict],
    output_lines: list[dict],
    balance_return_lines: list[dict],
    dust_kg: Decimal,
    stone_kg: Decimal,
    sack_weight_waste_kg: Decimal,
    powder_kg: Decimal,
    powder_line_data: dict | None,
    miscellaneous_waste_kg: Decimal,
    output_allocation_mode: str | None = None,
    single_allocation_owner_type: str | None = None,
    single_allocation_customer_id: int | None = None,
) -> ProcessingBatch:
    job_company_id = int(getattr(job, "company_id", 1))
    if not batch_has_content(
        input_lines=input_lines,
        output_lines=output_lines,
        balance_return_lines=balance_return_lines,
        dust_kg=dust_kg,
        stone_kg=stone_kg,
        sack_weight_waste_kg=sack_weight_waste_kg,
        powder_kg=powder_kg,
        miscellaneous_waste_kg=miscellaneous_waste_kg,
    ):
        raise ValueError(
            "Batch must have at least one input line, output line, balance return line, or waste kg"
        )

    for field_name, value in (
        ("dust_kg", dust_kg),
        ("stone_kg", stone_kg),
        ("sack_weight_waste_kg", sack_weight_waste_kg),
        ("powder_kg", powder_kg),
        ("miscellaneous_waste_kg", miscellaneous_waste_kg),
    ):
        if value < 0:
            raise ValueError(f"{field_name} cannot be negative")

    _validate_no_powder_output_lines(db, output_lines, company_id=job_company_id)

    op_at = utc_now()
    batch = ProcessingBatch(
        job_id=job.id,
        operation_at=op_at,
        dust_kg=dust_kg,
        stone_kg=stone_kg,
        sack_weight_waste_kg=sack_weight_waste_kg,
        powder_kg=Decimal("0"),
        miscellaneous_waste_kg=miscellaneous_waste_kg,
    )
    db.add(batch)
    db.flush()
    _store_powder_line_on_batch(batch, powder_line_data, powder_kg)

    if input_lines:
        _validate_input_batch_allowed(db, job, input_lines)
        _resolve_and_lock_allocation_on_input(
            db,
            job,
            input_lines,
            output_allocation_mode=output_allocation_mode,
            single_allocation_owner_type=single_allocation_owner_type,
            single_allocation_customer_id=single_allocation_customer_id,
        )
    elif output_allocation_mode is not None or single_allocation_owner_type is not None:
        _reject_conflicting_allocation_body(
            job,
            output_allocation_mode=output_allocation_mode,
            single_allocation_owner_type=single_allocation_owner_type,
            single_allocation_customer_id=single_allocation_customer_id,
        )

    cumulative_weights = _owner_weights_for_job_allocation(db, job, input_lines)
    has_outflow = _batch_has_outflow(
        output_lines=output_lines,
        balance_return_lines=balance_return_lines,
        dust_kg=dust_kg,
        stone_kg=stone_kg,
        sack_weight_waste_kg=sack_weight_waste_kg,
        powder_kg=powder_kg,
        miscellaneous_waste_kg=miscellaneous_waste_kg,
    )
    if has_outflow and not cumulative_weights:
        raise ValueError(NO_INPUT_FOR_OUTPUT_MSG)

    owner_mode = _job_owner_mode(db, job)
    if owner_mode == "mixed" and has_outflow and _job_output_allocation_mode(job) is None:
        raise ValueError(OUTPUT_ALLOCATION_MODE_REQUIRED_MSG)

    _reject_conflicting_allocation_body(
        job,
        output_allocation_mode=output_allocation_mode,
        single_allocation_owner_type=single_allocation_owner_type,
        single_allocation_customer_id=single_allocation_customer_id,
    )

    owner_weights = _effective_owner_weights_for_output(job, db, input_lines)
    allocation_mode = _job_output_allocation_mode(job)

    for idx, line in enumerate(input_lines):
        owner_type, customer_id = _owner_inventory_args(owner_key_from_line(line))
        try:
            qty = _processing.subtract_inventory(
                db,
                job.input_product_id,
                job.input_brand_id,
                line["location_id"],
                line["bag_type_id"],
                line["bag_count"],
                Decimal(line["loose_kg"]),
                owner_type=owner_type,
                customer_id=customer_id,
                company_id=job_company_id,
            )
        except ValueError as exc:
            if _is_balance_reprocess(line.get("input_source")) and str(exc) == "Insufficient stock":
                raise ValueError(BALANCE_REPROCESS_NO_STOCK_MSG) from exc
            raise
        db.add(
            ProcessingInputLine(
                batch_id=batch.id,
                location_id=line["location_id"],
                bag_type_id=line["bag_type_id"],
                bag_count=line["bag_count"],
                loose_kg=Decimal(line["loose_kg"]),
                quantity_kg=qty,
                line_index=idx,
                input_source=_parse_input_source(line.get("input_source")),
                owner_type=owner_type,
                customer_id=customer_id,
                job_work_order_id=line.get("job_work_order_id"),
            )
        )

    out_line_idx = 0
    created_output_owner_types: set[str] = set()
    for line in output_lines:
        bt = db.get(BagType, line["bag_type_id"])
        if not bt:
            raise ValueError("Bag type not found")
        for owner_key, bags, loose in _split_processing_line_across_owners(
            db, line, bt, owner_weights
        ):
            owner_type, customer_id = _owner_inventory_args(owner_key)
            created_output_owner_types.add(_owner_type_value(owner_type))
            qty = _processing.add_inventory(
                db,
                job.input_product_id,
                line["brand_id"],
                line["location_id"],
                line["bag_type_id"],
                bags,
                loose,
                owner_type=owner_type,
                customer_id=customer_id,
                company_id=job_company_id,
            )
            db.add(
                ProcessingOutputLine(
                    batch_id=batch.id,
                    brand_id=line["brand_id"],
                    location_id=line["location_id"],
                    bag_type_id=line["bag_type_id"],
                    bag_count=bags,
                    loose_kg=loose,
                    quantity_kg=qty,
                    line_index=out_line_idx,
                    owner_type=owner_type,
                    customer_id=customer_id,
                )
            )
            out_line_idx += 1

    if (
        allocation_mode == ProcessingOutputAllocationMode.proportional
        and len(cumulative_weights) >= 2
        and output_lines
    ):
        has_jw_input = any(
            key[0] == "job_work" and qty > 0 for key, qty in cumulative_weights.items()
        )
        if has_jw_input and "job_work" not in created_output_owner_types:
            raise ValueError(JOB_WORK_OUTPUT_MISSING_MSG)

    bal_line_idx = 0
    for line in balance_return_lines:
        bt = db.get(BagType, line["bag_type_id"])
        if not bt:
            raise ValueError("Bag type not found")
        for owner_key, bags, loose in _split_processing_line_across_owners(
            db, line, bt, owner_weights
        ):
            owner_type, customer_id = _owner_inventory_args(owner_key)
            qty = _processing.add_inventory(
                db,
                job.input_product_id,
                job.input_brand_id,
                line["location_id"],
                line["bag_type_id"],
                bags,
                loose,
                owner_type=owner_type,
                customer_id=customer_id,
                company_id=job_company_id,
            )
            db.add(
                ProcessingBalanceReturnLine(
                    batch_id=batch.id,
                    location_id=line["location_id"],
                    bag_type_id=line["bag_type_id"],
                    bag_count=bags,
                    loose_kg=loose,
                    quantity_kg=qty,
                    line_index=bal_line_idx,
                    owner_type=owner_type,
                    customer_id=customer_id,
                )
            )
            bal_line_idx += 1

    if owner_weights:
        waste_rows: dict[OwnerKey, ProcessingWasteAllocation] = {}
        for waste_field, waste_total in (
            ("dust_kg", dust_kg),
            ("stone_kg", stone_kg),
            ("sack_weight_waste_kg", sack_weight_waste_kg),
            ("miscellaneous_waste_kg", miscellaneous_waste_kg),
        ):
            if waste_total <= 0:
                continue
            split = proportional_split_kg(waste_total, owner_weights)
            for owner_key, alloc_kg in split.items():
                if alloc_kg <= 0:
                    continue
                wa = _ensure_waste_allocation_row(db, batch.id, owner_key, waste_rows)
                current = getattr(wa, waste_field) or Decimal("0")
                setattr(wa, waste_field, current + alloc_kg)

        _allocate_powder_to_owners(db, batch, powder_kg, powder_line_data, owner_weights, waste_rows)
    elif powder_kg > 0 and powder_line_data:
        _allocate_powder_to_owners(
            db, batch, powder_kg, powder_line_data, {("owned", None): powder_kg}, {}
        )

    return batch

def submit_batch(
    db: Session,
    job_id: int,
    *,
    company_id: int | None = None,
    input_lines: list[dict],
    output_lines: list[dict],
    balance_return_lines: list[dict],
    dust_kg: Decimal,
    stone_kg: Decimal,
    sack_weight_waste_kg: Decimal,
    powder_kg: Decimal = Decimal("0"),
    powder_line: dict | None = None,
    miscellaneous_waste_kg: Decimal,
    output_allocation_mode: str | None = None,
    single_allocation_owner_type: str | None = None,
    single_allocation_customer_id: int | None = None,
) -> ProcessingJob:
    job = _processing.load_processing_job(db, job_id, company_id=company_id)
    if job.status != ProcessingJobStatus.open:
        raise ValueError("Processing job is not open")
    job_company_id = int(getattr(job, "company_id", 1))
    resolved_powder_kg, powder_line_data = _resolve_powder_for_batch(
        db,
        powder_line=powder_line,
        powder_kg_legacy=powder_kg,
        company_id=job_company_id,
    )
    try:
        validate_balance_reprocess(job, input_lines, db)
        validate_processing_mass_balance(
            job,
            pending_input_lines=input_lines,
            pending_output_lines=output_lines,
            pending_balance_return_lines=balance_return_lines,
            pending_waste_fields={
                "dust_kg": dust_kg,
                "stone_kg": stone_kg,
                "sack_weight_waste_kg": sack_weight_waste_kg,
                "powder_kg": resolved_powder_kg,
                "miscellaneous_waste_kg": miscellaneous_waste_kg,
            },
            db=db,
        )
        _apply_batch(
            db,
            job,
            input_lines=input_lines,
            output_lines=output_lines,
            balance_return_lines=balance_return_lines,
            dust_kg=dust_kg,
            stone_kg=stone_kg,
            sack_weight_waste_kg=sack_weight_waste_kg,
            powder_kg=resolved_powder_kg,
            powder_line_data=powder_line_data,
            miscellaneous_waste_kg=miscellaneous_waste_kg,
            output_allocation_mode=output_allocation_mode,
            single_allocation_owner_type=single_allocation_owner_type,
            single_allocation_customer_id=single_allocation_customer_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _processing.load_processing_job(db, job_id)

def complete_job(
    db: Session,
    job_id: int,
    *,
    company_id: int | None = None,
    input_lines: list[dict],
    output_lines: list[dict],
    balance_return_lines: list[dict],
    dust_kg: Decimal,
    stone_kg: Decimal,
    sack_weight_waste_kg: Decimal,
    powder_kg: Decimal = Decimal("0"),
    powder_line: dict | None = None,
    miscellaneous_waste_kg: Decimal,
    output_allocation_mode: str | None = None,
    single_allocation_owner_type: str | None = None,
    single_allocation_customer_id: int | None = None,
) -> ProcessingJob:
    job = _processing.load_processing_job(db, job_id, company_id=company_id)
    if job.status != ProcessingJobStatus.open:
        raise ValueError("Processing job is not open")
    job_company_id = int(getattr(job, "company_id", 1))
    resolved_powder_kg, powder_line_data = _resolve_powder_for_batch(
        db,
        powder_line=powder_line,
        powder_kg_legacy=powder_kg,
        company_id=job_company_id,
    )
    has_body = batch_has_content(
        input_lines=input_lines,
        output_lines=output_lines,
        balance_return_lines=balance_return_lines,
        dust_kg=dust_kg,
        stone_kg=stone_kg,
        sack_weight_waste_kg=sack_weight_waste_kg,
        powder_kg=resolved_powder_kg,
        miscellaneous_waste_kg=miscellaneous_waste_kg,
    )

    if not has_body and not _job_has_active_batches(db, job_id):
        # Empty open job (never recorded, or all batches voided): close to free
        # the per-product/brand open slot so another completed job can reopen.
        try:
            job.status = ProcessingJobStatus.completed
            job.completed_at = utc_now()
            db.commit()
        except Exception:
            db.rollback()
            raise
        return _processing.load_processing_job(db, job_id)

    try:
        validate_balance_reprocess(job, input_lines, db)
        validate_processing_mass_balance(
            job,
            pending_input_lines=input_lines if has_body else [],
            pending_output_lines=output_lines if has_body else [],
            pending_balance_return_lines=balance_return_lines if has_body else [],
            pending_waste_fields={
                "dust_kg": dust_kg if has_body else Decimal("0"),
                "stone_kg": stone_kg if has_body else Decimal("0"),
                "sack_weight_waste_kg": sack_weight_waste_kg if has_body else Decimal("0"),
                "powder_kg": resolved_powder_kg if has_body else Decimal("0"),
                "miscellaneous_waste_kg": miscellaneous_waste_kg if has_body else Decimal("0"),
            },
            db=db,
        )
        if has_body:
            _apply_batch(
                db,
                job,
                input_lines=input_lines,
                output_lines=output_lines,
                balance_return_lines=balance_return_lines,
                dust_kg=dust_kg,
                stone_kg=stone_kg,
                sack_weight_waste_kg=sack_weight_waste_kg,
                powder_kg=resolved_powder_kg,
                powder_line_data=powder_line_data,
                miscellaneous_waste_kg=miscellaneous_waste_kg,
                output_allocation_mode=output_allocation_mode,
                single_allocation_owner_type=single_allocation_owner_type,
                single_allocation_customer_id=single_allocation_customer_id,
            )
        job.status = ProcessingJobStatus.completed
        job.completed_at = utc_now()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _processing.load_processing_job(db, job_id)


def _job_has_active_batches(db: Session, job_id: int) -> bool:
    return (
        db.scalar(
            select(ProcessingBatch.id)
            .where(ProcessingBatch.job_id == job_id, ProcessingBatch.voided_at.is_(None))
            .limit(1)
        )
        is not None
    )


def _close_empty_open_job(db: Session, job: ProcessingJob) -> None:
    """Complete an open job that has no non-voided batches (frees open unique slot)."""
    job.status = ProcessingJobStatus.completed
    job.completed_at = utc_now()


def _stock_tuple_label(
    db: Session, product_id: int, brand_id: int, location_id: int, bag_type_id: int
) -> str:
    product = db.get(Product, product_id)
    brand = db.get(Brand, brand_id)
    location = db.get(Location, location_id)
    bag_type = db.get(BagType, bag_type_id)
    return (
        f"{product.product_name if product else product_id} / "
        f"{brand.name if brand else brand_id} / "
        f"{location.name if location else location_id} / "
        f"{bag_type.name if bag_type else bag_type_id}"
    )


def _available_kg_at_sku(
    db: Session,
    *,
    company_id: int,
    product_id: int,
    brand_id: int,
    location_id: int,
    owner_type,
    customer_id,
) -> Decimal:
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
    return sum((Decimal(r.total_quantity_kg or 0) for r in rows), Decimal("0"))


def _unique_lines(lines) -> list:
    seen: set[int] = set()
    unique: list = []
    for line in lines or []:
        if line.id in seen:
            continue
        seen.add(line.id)
        unique.append(line)
    return unique


def _line_bags_loose_for_void(line, bt: BagType) -> tuple[int, Decimal]:
    """Prefer posted quantity_kg for loose lines (UI kg), then stored bags/loose."""
    bag_count = int(line.bag_count or 0)
    loose_kg = Decimal(line.loose_kg or 0)
    posted = Decimal(line.quantity_kg or 0)
    if bt.is_loose:
        kg = posted if posted > loose_kg else loose_kg
        return 0, kg
    return bag_count, loose_kg


def _subtract_void_with_label(
    db: Session,
    *,
    role: str,
    product_id: int,
    brand_id: int,
    location_id: int,
    bag_type_id: int,
    bag_count: int,
    loose_kg: Decimal,
    owner_type,
    customer_id,
    company_id: int,
) -> None:
    try:
        _processing._subtract_for_void(
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
            allow_other_locations=True,
        )
    except ValueError as exc:
        if str(exc) != OPERATION_VOID_INSUFFICIENT_STOCK_MSG:
            raise
        bt = _processing._get_bag_type(db, bag_type_id)
        need = _void_line_quantity_kg(bt, bag_count, loose_kg)
        have_here = _available_kg_at_sku(
            db,
            company_id=company_id,
            product_id=product_id,
            brand_id=brand_id,
            location_id=location_id,
            owner_type=owner_type,
            customer_id=customer_id,
        )
        have_all = sum(
            (
                Decimal(r.total_quantity_kg or 0)
                for r in lock_inventory_product_brand_owner_rows(
                    db,
                    company_id,
                    product_id,
                    brand_id,
                    owner_type,
                    customer_id,
                )
            ),
            Decimal("0"),
        )
        label = _stock_tuple_label(db, product_id, brand_id, location_id, bag_type_id)
        raise ValueError(
            f"{OPERATION_VOID_INSUFFICIENT_STOCK_MSG} "
            f"({role}: {label}; need {need} kg, have {have_here} kg here / {have_all} kg all locations)"
        ) from exc


def _job_has_later_balance_reprocess(db: Session, job: ProcessingJob, batch: ProcessingBatch) -> bool:
    later_ids = select(ProcessingBatch.id).where(
        ProcessingBatch.job_id == job.id,
        ProcessingBatch.voided_at.is_(None),
        ProcessingBatch.id != batch.id,
        or_(
            ProcessingBatch.operation_at > batch.operation_at,
            and_(
                ProcessingBatch.operation_at == batch.operation_at,
                ProcessingBatch.id > batch.id,
            ),
        ),
    )
    found = db.scalar(
        select(ProcessingInputLine.id).where(
            ProcessingInputLine.batch_id.in_(later_ids),
            ProcessingInputLine.input_source == ProcessingInputSource.balance_reprocess,
        ).limit(1)
    )
    return found is not None

def _void_powder_inventory_for_batch(db: Session, batch: ProcessingBatch, *, company_id: int) -> None:
    if batch.powder_kg <= 0:
        return
    product_id, brand_id, location_id, bag_type_id, bt = _batch_powder_inventory_tuple(db, batch)
    allocations = batch.waste_allocations or []
    powder_splits = [
        (wa.owner_type, wa.customer_id, wa.powder_kg)
        for wa in allocations
        if wa.powder_kg and wa.powder_kg > 0
    ]
    if not powder_splits:
        powder_splits = [(InventoryOwnerType.owned, None, batch.powder_kg)]
    use_stored_line = (
        len(powder_splits) == 1
        and batch.powder_bag_type_id is not None
        and batch.powder_bag_count is not None
    )
    for owner_type, customer_id, alloc_kg in powder_splits:
        if alloc_kg <= 0:
            continue
        if use_stored_line:
            if bt.is_loose:
                bag_count = 0
                loose_kg = (
                    Decimal(batch.powder_loose_kg)
                    if batch.powder_loose_kg is not None
                    else alloc_kg
                )
            else:
                bag_count = int(batch.powder_bag_count or 0)
                loose_kg = Decimal(batch.powder_loose_kg or 0)
                if bag_count <= 0 or loose_kg != 0:
                    bag_count, loose_kg = _kg_to_bags_loose(bt, alloc_kg)
        elif bt.is_loose:
            bag_count = 0
            loose_kg = alloc_kg
        else:
            bag_count, loose_kg = _kg_to_bags_loose(bt, alloc_kg)
        if bt.is_loose:
            validate_bags_loose(bt, bag_count, loose_kg)
        elif bag_count > 0 and loose_kg == 0:
            validate_bags_loose(bt, bag_count, loose_kg)
        _subtract_void_with_label(
            db,
            role="powder",
            product_id=product_id,
            brand_id=brand_id,
            location_id=location_id,
            bag_type_id=bag_type_id,
            bag_count=bag_count,
            loose_kg=loose_kg,
            owner_type=owner_type,
            customer_id=customer_id,
            company_id=company_id,
        )

def _reconcile_job_after_batch_void(db: Session, job: ProcessingJob) -> None:
    if job.status == ProcessingJobStatus.completed:
        # Unique open job per product+brand. Auto-close an empty open sibling
        # (voided-only / never recorded); block if the other open still has activity.
        other_open = db.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.company_id == job.company_id,
                ProcessingJob.input_product_id == job.input_product_id,
                ProcessingJob.input_brand_id == job.input_brand_id,
                ProcessingJob.status == ProcessingJobStatus.open,
                ProcessingJob.id != job.id,
            )
            .with_for_update()
        )
        if other_open is not None:
            if _job_has_active_batches(db, other_open.id):
                raise ValueError(
                    "Cannot reopen this completed job while another open processing job "
                    "already exists for the same product and brand with recorded batches. "
                    "Complete that job first (or void its batches and close it), then void again."
                )
            _close_empty_open_job(db, other_open)
        job.status = ProcessingJobStatus.open
        job.completed_at = None
    if len(_job_input_owner_keys(db, job)) < 2:
        job.output_allocation_mode = None
        job.single_allocation_owner_type = None
        job.single_allocation_customer_id = None

def void_processing_batch(
    db: Session,
    batch_id: int,
    *,
    actor: User | None = None,
    company_id: int | None = None,
) -> ProcessingJob:
    batch = db.execute(
        select(ProcessingBatch)
        .where(ProcessingBatch.id == batch_id)
        .options(
            selectinload(ProcessingBatch.input_lines),
            selectinload(ProcessingBatch.output_lines),
            selectinload(ProcessingBatch.balance_return_lines),
            selectinload(ProcessingBatch.waste_allocations),
        )
        .with_for_update(of=ProcessingBatch)
    ).unique().scalar_one_or_none()
    if not batch:
        raise ValueError("Processing batch not found")
    if batch.voided_at is not None:
        raise ValueError(OPERATION_ALREADY_VOIDED_MSG)

    job = db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.id == batch.job_id)
        .with_for_update(of=ProcessingJob)
    )
    if not job:
        raise ValueError("Processing job not found")
    if company_id is not None and int(job.company_id) != int(company_id):
        raise ValueError("Processing batch not found")

    input_lines = _unique_lines(batch.input_lines)
    output_lines = _unique_lines(batch.output_lines)
    balance_return_lines = _unique_lines(batch.balance_return_lines)

    if balance_return_lines and _job_has_later_balance_reprocess(db, job, batch):
        raise ValueError(LATER_REPROCESS_VOID_MSG)

    lock_keys: list[tuple] = []
    for line in input_lines:
        ot, cid = _owner_inventory_args(_owner_key_from_stored_input(line))
        lock_keys.append(
            inventory_row_key(
                job.input_product_id,
                job.input_brand_id,
                line.location_id,
                line.bag_type_id,
                ot,
                cid,
            )
        )
    for line in output_lines:
        ot, cid = _owner_inventory_args(_owner_key_from_stored_owner_line(line))
        lock_keys.append(
            inventory_row_key(
                job.input_product_id,
                line.brand_id,
                line.location_id,
                line.bag_type_id,
                ot,
                cid,
            )
        )
    for line in balance_return_lines:
        ot, cid = _owner_inventory_args(_owner_key_from_stored_owner_line(line))
        lock_keys.append(
            inventory_row_key(
                job.input_product_id,
                job.input_brand_id,
                line.location_id,
                line.bag_type_id,
                ot,
                cid,
            )
        )
    if batch.powder_kg > 0:
        product_id, brand_id, location_id, bag_type_id, _bt = _batch_powder_inventory_tuple(db, batch)
        allocations = batch.waste_allocations or []
        powder_splits = [
            (wa.owner_type, wa.customer_id, wa.powder_kg)
            for wa in allocations
            if wa.powder_kg and wa.powder_kg > 0
        ]
        if not powder_splits:
            lock_keys.append(
                inventory_row_key(
                    product_id,
                    brand_id,
                    location_id,
                    bag_type_id,
                    InventoryOwnerType.owned,
                    None,
                )
            )
        else:
            for owner_type, customer_id, _alloc_kg in powder_splits:
                lock_keys.append(
                    inventory_row_key(
                        product_id,
                        brand_id,
                        location_id,
                        bag_type_id,
                        owner_type,
                        customer_id,
                    )
                )

    lock_inventory_rows(db, job.company_id, lock_keys)
    sku_keys = [
        inventory_sku_key(product_id, brand_id, location_id, ot, cid)
        for product_id, brand_id, location_id, _bag_type_id, ot, cid in lock_keys
    ]
    lock_inventory_sku_rows(db, job.company_id, sku_keys)

    _void_powder_inventory_for_batch(db, batch, company_id=job.company_id)

    for line in output_lines:
        ot, cid = _owner_inventory_args(_owner_key_from_stored_owner_line(line))
        bt = _processing._get_bag_type(db, line.bag_type_id)
        bags, loose = _line_bags_loose_for_void(line, bt)
        brand = db.get(Brand, line.brand_id)
        role = f"output {brand.name}" if brand else "output"
        _subtract_void_with_label(
            db,
            role=role,
            product_id=job.input_product_id,
            brand_id=line.brand_id,
            location_id=line.location_id,
            bag_type_id=line.bag_type_id,
            bag_count=bags,
            loose_kg=loose,
            owner_type=ot,
            customer_id=cid,
            company_id=job.company_id,
        )

    for line in balance_return_lines:
        ot, cid = _owner_inventory_args(_owner_key_from_stored_owner_line(line))
        bt = _processing._get_bag_type(db, line.bag_type_id)
        bags, loose = _line_bags_loose_for_void(line, bt)
        _subtract_void_with_label(
            db,
            role="balance return",
            product_id=job.input_product_id,
            brand_id=job.input_brand_id,
            location_id=line.location_id,
            bag_type_id=line.bag_type_id,
            bag_count=bags,
            loose_kg=loose,
            owner_type=ot,
            customer_id=cid,
            company_id=job.company_id,
        )

    for line in input_lines:
        ot, cid = _owner_inventory_args(_owner_key_from_stored_input(line))
        bt = _processing._get_bag_type(db, line.bag_type_id)
        bags, loose = _line_bags_loose_for_void(line, bt)
        _processing.add_inventory(
            db,
            job.input_product_id,
            job.input_brand_id,
            line.location_id,
            line.bag_type_id,
            bags,
            loose,
            owner_type=ot,
            customer_id=cid,
            company_id=job.company_id,
        )

    batch.voided_at = utc_now()
    try:
        _reconcile_job_after_batch_void(db, job)
        db.commit()
    except ValueError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        # Safety net if uq_processing_job_open_input still fires (race with concurrent open).
        msg = str(getattr(exc, "orig", exc))
        if "uq_processing_job_open_input" in msg:
            raise ValueError(
                "Cannot reopen this completed job while another open processing job "
                "already exists for the same product and brand. Complete or close the "
                "other open job first, then void again."
            ) from exc
        raise
    result = _processing.load_processing_job(db, job.id)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.PROCESSING_BATCH_VOIDED,
            entity_type=AuditEntityType.PROCESSING_BATCH,
            entity_id=batch_id,
            entity_label=f"Batch #{batch_id} (job #{job.id})",
            metadata={"job_id": job.id},
        )
    return result
