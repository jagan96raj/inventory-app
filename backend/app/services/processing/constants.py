"""Processing message constants and tolerances."""
from decimal import Decimal

PROCESSING_OUTPUT_TOLERANCE_KG = Decimal("100")

BALANCE_REPROCESS_NO_RETURN_MSG = (
    "No unclean balance returned in this job yet; use From stock only"
)

BALANCE_REPROCESS_NO_STOCK_MSG = (
    "No unclean stock at this location (balance may have been sold)"
)

LATER_REPROCESS_VOID_MSG = (
    "Cannot void this batch because a later batch reprocessed its returned balance. "
    "Void later batches first (newest first), then void this one."
)

MIXED_EXTERNAL_OWNER_MSG = "Mixed-owner processing is not allowed for external customers"

NO_INPUT_FOR_OUTPUT_MSG = "Cannot allocate output: no input recorded on this job yet"

MIXED_OWNER_WEIGHTS_COLLAPSED_MSG = (
    "Mixed-owner input detected but owner weights collapsed to a single owner — "
    "check processing_input_lines owner_type/customer_id"
)

JOB_WORK_OUTPUT_MISSING_MSG = (
    "Owner split failed: job_work input present but no job_work output lines"
)

MIXED_JOB_NO_MORE_INPUT_MSG = (
    "Mixed-owner jobs do not allow further input. "
    "Create a new processing job for additional material."
)

DIFFERENT_OWNER_AFTER_OUTPUT_MSG = (
    "Cannot add a different owner after output has been recorded on this job."
)

MIXED_OWNERS_FIRST_BATCH_ONLY_MSG = (
    "Mixed owners are allowed only on the first input batch."
)

OUTPUT_ALLOCATION_MODE_REQUIRED_MSG = (
    "Choose output allocation: proportional or single owner."
)

OUTPUT_ALLOCATION_LOCKED_MSG = "Output allocation is locked for this job."

SINGLE_OWNER_NOT_IN_JOB_INPUT_MSG = (
    "Selected owner did not contribute input on this job."
)

POWDER_OUTPUT_LINE_MSG = (
    "Enter powder in the Waste section (Powder kg), not as an output brand line."
)

POWDER_DEST_NOT_CONFIGURED_MSG = (
    "Configure powder destination in Book settings before recording powder kg."
)

