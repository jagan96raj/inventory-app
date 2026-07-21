"""Spec v12.13 — optimistic bill version checks for stale-write protection."""
from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException

from app.models.entities import Bill
from app.services.bill_lock import BILL_IN_USE_MSG
from app.services.bills import (
    BILL_ALREADY_VOIDED_MSG,
    BILL_VOID_HAS_FULFILLMENT_MSG,
    BILL_VOID_HAS_LINKED_CASHBOOK_MSG,
    BILL_VOID_HAS_PAYMENTS_MSG,
)

STALE_BILL_MSG = "Bill was updated by another user. Refresh and try again."
EXPECTED_VERSION_REQUIRED_MSG = "expected_version required"
EXPECTED_BILL_VERSION_HEADER = "X-Expected-Bill-Version"


def assert_bill_version(bill: Bill, expected_version: int | None) -> None:
    if expected_version is None:
        raise ValueError(EXPECTED_VERSION_REQUIRED_MSG)
    if expected_version != bill.version:
        raise ValueError(STALE_BILL_MSG)


def bump_bill_version(bill: Bill) -> None:
    bill.version += 1


def bump_bills_version(bills: Iterable[Bill]) -> None:
    for bill in bills:
        bump_bill_version(bill)


def http_exception_for_value_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg in (
        BILL_IN_USE_MSG,
        STALE_BILL_MSG,
        BILL_ALREADY_VOIDED_MSG,
        BILL_VOID_HAS_PAYMENTS_MSG,
        BILL_VOID_HAS_FULFILLMENT_MSG,
        BILL_VOID_HAS_LINKED_CASHBOOK_MSG,
    ):
        return HTTPException(409, msg)
    # Spec v17.0.2 — cross-company / missing entities: prefer 404 (no existence leak).
    if msg.lower().endswith("not found"):
        return HTTPException(404, msg)
    return HTTPException(400, msg)
