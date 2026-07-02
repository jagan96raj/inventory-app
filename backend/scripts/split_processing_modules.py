"""One-off helper: split processing.py into processing/ package modules."""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "services" / "processing.py"
OUT = ROOT / "app" / "services" / "processing"

MODULE_FUNCS: dict[str, list[str]] = {
    "constants": [],
    "batch_helpers": [
        "_batch_is_active",
        "_active_job_batches",
        "_sorted_job_batches",
        "_batch_has_outflow",
        "_kg_to_bags_loose",
        "_is_loose_processing_line",
        "_batch_total_waste_kg",
        "_pending_line_quantity_kg",
        "_waste_has_content",
        "batch_has_content",
        "_parse_input_source",
        "_is_balance_reprocess",
        "_batch_explicit_waste_kg",
    ],
    "powder": [
        "_powder_brand_ids",
        "_validate_no_powder_output_lines",
        "_validate_powder_brand_id",
        "_resolve_powder_product_id",
        "_resolve_powder_destination",
        "_batch_powder_inventory_tuple",
        "_resolve_powder_for_batch",
        "_store_powder_line_on_batch",
        "_ensure_waste_allocation_row",
        "_allocate_powder_to_owners",
    ],
    "allocation": [
        "_single_owner_input_only_msg",
        "_owner_type_value",
        "_parse_owner_type",
        "_owner_inventory_args",
        "validate_processing_owner_mix",
        "_job_has_any_output",
        "_job_input_owner_keys",
        "_job_owner_mode",
        "_job_input_fully_locked",
        "_job_allowed_input_owner_key",
        "_batch_will_create_mix",
        "_first_input_batch_number",
        "_pending_input_owner_keys",
        "_owner_key_label",
        "_build_input_rules_hint",
        "_validate_input_batch_allowed",
        "_owner_weights_from_inputs",
        "_owner_key_from_stored_input",
        "_owner_weights_for_job_allocation",
        "_owner_weights_from_loaded_job",
        "_owner_key_from_allocation_fields",
        "_job_stored_single_allocation_owner_key",
        "_default_single_allocation_owner",
        "_allocation_body_conflicts_stored",
        "_persist_output_allocation_mode",
        "_resolve_and_lock_allocation_on_input",
        "_reject_conflicting_allocation_body",
        "_effective_owner_weights_for_output",
        "_build_output_allocation_hint",
        "format_owner_allocation_weights",
        "_split_line_kg_across_owners",
        "_split_processing_line_across_owners",
        "_owner_key_from_stored_owner_line",
    ],
    "mass_balance": [
        "compute_job_fresh_input_kg",
        "_sum_output_balance_kg_from_batches",
        "compute_job_outflow_kg",
        "_sum_output_balance_kg",
        "validate_processing_mass_balance",
        "compute_job_committed_balance_return_kg",
        "compute_job_committed_balance_reprocess_kg",
        "compute_job_available_reprocess_kg",
        "_pending_reprocess_kg",
        "_reprocess_line_has_physical_stock",
        "validate_balance_reprocess",
    ],
    "batch": [
        "_get_open_job",
        "create_job",
        "_apply_batch",
        "submit_batch",
        "complete_job",
        "_void_powder_inventory_for_batch",
        "_reconcile_job_after_batch_void",
        "void_processing_batch",
    ],
    "serialization": [
        "_batch_load_options",
        "load_processing_job",
        "compute_processing_summary",
        "fetch_processing_list_summaries",
        "serialize_processing_job_list_item",
        "serialize_processing_job",
    ],
}

SHARED_IMPORTS = textwrap.dedent(
    """
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
    """
).strip()


def extract_top_level_defs(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = "".join(lines[node.lineno - 1 : node.end_lineno])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = "".join(lines[node.lineno - 1 : node.end_lineno])
    return out


def main() -> None:
    source = SRC.read_text(encoding="utf-8")
    defs = extract_top_level_defs(source)

    const_names = [
        "PROCESSING_OUTPUT_TOLERANCE_KG",
        "BALANCE_REPROCESS_NO_RETURN_MSG",
        "BALANCE_REPROCESS_NO_STOCK_MSG",
        "MIXED_EXTERNAL_OWNER_MSG",
        "NO_INPUT_FOR_OUTPUT_MSG",
        "MIXED_OWNER_WEIGHTS_COLLAPSED_MSG",
        "JOB_WORK_OUTPUT_MISSING_MSG",
        "MIXED_JOB_NO_MORE_INPUT_MSG",
        "DIFFERENT_OWNER_AFTER_OUTPUT_MSG",
        "MIXED_OWNERS_FIRST_BATCH_ONLY_MSG",
        "OUTPUT_ALLOCATION_MODE_REQUIRED_MSG",
        "OUTPUT_ALLOCATION_LOCKED_MSG",
        "SINGLE_OWNER_NOT_IN_JOB_INPUT_MSG",
        "POWDER_OUTPUT_LINE_MSG",
        "POWDER_DEST_NOT_CONFIGURED_MSG",
    ]

    OUT.mkdir(exist_ok=True)

    const_body = "\n".join(defs[name] for name in const_names)
    (OUT / "constants.py").write_text(
        f'"""Processing message constants and tolerances."""\nfrom decimal import Decimal\n\n{const_body}\n',
        encoding="utf-8",
    )

    all_assigned = {name for names in MODULE_FUNCS.values() for name in names}
    missing = all_assigned - set(defs)
    if missing:
        raise SystemExit(f"Missing definitions: {sorted(missing)}")

    module_imports = {
        "batch_helpers": "from app.services.processing.constants import PROCESSING_OUTPUT_TOLERANCE_KG\n",
        "powder": (
            "from app.services.processing.allocation import _owner_inventory_args\n"
            "from app.services.processing.batch_helpers import _kg_to_bags_loose\n"
            "from app.services.processing.constants import (\n"
            "    POWDER_DEST_NOT_CONFIGURED_MSG,\n"
            "    POWDER_OUTPUT_LINE_MSG,\n"
            ")\n"
        ),
        "allocation": (
            "from app.services.processing.batch_helpers import (\n"
            "    _active_job_batches,\n"
            "    _batch_total_waste_kg,\n"
            "    _pending_line_quantity_kg,\n"
            ")\n"
            "from app.services.processing.constants import (\n"
            "    DIFFERENT_OWNER_AFTER_OUTPUT_MSG,\n"
            "    JOB_WORK_OUTPUT_MISSING_MSG,\n"
            "    MIXED_EXTERNAL_OWNER_MSG,\n"
            "    MIXED_JOB_NO_MORE_INPUT_MSG,\n"
            "    MIXED_OWNER_WEIGHTS_COLLAPSED_MSG,\n"
            "    MIXED_OWNERS_FIRST_BATCH_ONLY_MSG,\n"
            "    NO_INPUT_FOR_OUTPUT_MSG,\n"
            "    OUTPUT_ALLOCATION_LOCKED_MSG,\n"
            "    OUTPUT_ALLOCATION_MODE_REQUIRED_MSG,\n"
            "    SINGLE_OWNER_NOT_IN_JOB_INPUT_MSG,\n"
            ")\n"
        ),
        "mass_balance": (
            "from app.services.processing.allocation import _owner_inventory_args\n"
            "from app.services.processing.batch_helpers import (\n"
            "    _active_job_batches,\n"
            "    _batch_total_waste_kg,\n"
            "    _is_balance_reprocess,\n"
            "    _pending_line_quantity_kg,\n"
            ")\n"
            "from app.services.processing.constants import (\n"
            "    BALANCE_REPROCESS_NO_RETURN_MSG,\n"
            "    BALANCE_REPROCESS_NO_STOCK_MSG,\n"
            "    PROCESSING_OUTPUT_TOLERANCE_KG,\n"
            ")\n"
        ),
        "batch": (
            "from app.services.processing.allocation import (\n"
            "    _effective_owner_weights_for_output,\n"
            "    _job_has_any_output,\n"
            "    _job_input_owner_keys,\n"
            "    _job_owner_mode,\n"
            "    _owner_inventory_args,\n"
            "    _owner_key_from_stored_input,\n"
            "    _owner_key_from_stored_owner_line,\n"
            "    _owner_type_value,\n"
            "    _owner_weights_for_job_allocation,\n"
            "    _reject_conflicting_allocation_body,\n"
            "    _resolve_and_lock_allocation_on_input,\n"
            "    _validate_input_batch_allowed,\n"
            ")\n"
            "from app.services.processing.batch_helpers import (\n"
            "    _batch_has_outflow,\n"
            "    batch_has_content,\n"
            ")\n"
            "from app.services.processing.constants import (\n"
            "    BALANCE_REPROCESS_NO_STOCK_MSG,\n"
            "    JOB_WORK_OUTPUT_MISSING_MSG,\n"
            "    NO_INPUT_FOR_OUTPUT_MSG,\n"
            "    OUTPUT_ALLOCATION_MODE_REQUIRED_MSG,\n"
            ")\n"
            "from app.services.processing.mass_balance import (\n"
            "    validate_balance_reprocess,\n"
            "    validate_processing_mass_balance,\n"
            ")\n"
            "from app.services.processing.powder import (\n"
            "    _allocate_powder_to_owners,\n"
            "    _batch_powder_inventory_tuple,\n"
            "    _ensure_waste_allocation_row,\n"
            "    _resolve_powder_for_batch,\n"
            "    _store_powder_line_on_batch,\n"
            "    _validate_no_powder_output_lines,\n"
            ")\n"
            "from app.services.processing.serialization import load_processing_job\n"
        ),
        "serialization": (
            "from app.services.processing.allocation import (\n"
            "    _build_input_rules_hint,\n"
            "    _build_output_allocation_hint,\n"
            "    _job_allowed_input_owner_key,\n"
            "    _job_has_any_output,\n"
            "    _job_input_fully_locked,\n"
            "    _job_owner_mode,\n"
            "    _job_stored_single_allocation_owner_key,\n"
            "    _owner_key_from_stored_input,\n"
            "    _owner_type_value,\n"
            "    _owner_weights_from_loaded_job,\n"
            "    format_owner_allocation_weights,\n"
            ")\n"
            "from app.services.processing.batch_helpers import (\n"
            "    _active_job_batches,\n"
            "    _batch_explicit_waste_kg,\n"
            "    _is_balance_reprocess,\n"
            ")\n"
            "from app.services.processing.mass_balance import compute_job_available_reprocess_kg\n"
        ),
    }

    for module, funcs in MODULE_FUNCS.items():
        if module == "constants":
            continue
        body = "\n\n".join(defs[name].rstrip() for name in funcs)
        extra = module_imports.get(module, "")
        content = f'"""Processing service — {module.replace("_", " ")}."""\n{SHARED_IMPORTS}\n\n{extra}\n{body}\n'
        (OUT / f"{module}.py").write_text(content, encoding="utf-8")

    public_exports = sorted(
        set(const_names)
        | {
            "validate_processing_owner_mix",
            "format_owner_allocation_weights",
            "compute_job_fresh_input_kg",
            "compute_job_outflow_kg",
            "validate_processing_mass_balance",
            "batch_has_content",
            "compute_job_committed_balance_return_kg",
            "compute_job_committed_balance_reprocess_kg",
            "compute_job_available_reprocess_kg",
            "validate_balance_reprocess",
            "create_job",
            "submit_batch",
            "complete_job",
            "void_processing_batch",
            "load_processing_job",
            "compute_processing_summary",
            "fetch_processing_list_summaries",
            "serialize_processing_job_list_item",
            "serialize_processing_job",
            "_owner_key_from_stored_input",
            "_owner_weights_for_job_allocation",
        }
    )

    init_lines = [
        '"""Processing service facade — re-exports split modules (Spec v16.0.13)."""',
        "from app.services.processing.allocation import (",
        "    _owner_key_from_stored_input,",
        "    _owner_weights_for_job_allocation,",
        "    format_owner_allocation_weights,",
        "    validate_processing_owner_mix,",
        ")",
        "from app.services.processing.batch import (",
        "    complete_job,",
        "    create_job,",
        "    submit_batch,",
        "    void_processing_batch,",
        ")",
        "from app.services.processing.batch_helpers import batch_has_content",
        "from app.services.processing.constants import *",
        "from app.services.processing.mass_balance import (",
        "    compute_job_available_reprocess_kg,",
        "    compute_job_committed_balance_reprocess_kg,",
        "    compute_job_committed_balance_return_kg,",
        "    compute_job_fresh_input_kg,",
        "    compute_job_outflow_kg,",
        "    validate_balance_reprocess,",
        "    validate_processing_mass_balance,",
        ")",
        "from app.services.processing.serialization import (",
        "    compute_processing_summary,",
        "    fetch_processing_list_summaries,",
        "    load_processing_job,",
        "    serialize_processing_job,",
        "    serialize_processing_job_list_item,",
        ")",
        "",
        "__all__ = " + repr(public_exports),
        "",
    ]
    (OUT / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")
    print(f"Wrote package under {OUT}")


if __name__ == "__main__":
    main()
