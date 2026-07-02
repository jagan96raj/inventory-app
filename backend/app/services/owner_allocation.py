"""Spec v14.0 / v14.4 — proportional owner allocation (largest-remainder method)."""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

OwnerKey = tuple[str, int | None]


def proportional_split_kg(total: Decimal, weights: dict[OwnerKey, Decimal]) -> dict[OwnerKey, Decimal]:
    """
    Split total kg across owners by weight ratio.
    Uses largest-remainder at 0.001 kg precision.
    """
    if total <= 0:
        return {k: Decimal("0") for k in weights}
    if not weights:
        return {}

    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Cannot split quantity with zero total owner input weight")

    keys = list(weights.keys())
    raw = {k: total * weights[k] / total_weight for k in keys}
    floored = {k: raw[k].quantize(Decimal("0.001"), rounding=ROUND_DOWN) for k in keys}
    allocated = sum(floored.values())
    remainder_units = int(((total - allocated) / Decimal("0.001")).quantize(Decimal("1")))
    if remainder_units > 0:
        fractional = sorted(
            keys,
            key=lambda k: (raw[k] - floored[k], weights[k]),
            reverse=True,
        )
        for i in range(remainder_units):
            floored[fractional[i % len(fractional)]] += Decimal("0.001")
    return floored


def proportional_split_bags(total_bags: int, weights: dict[OwnerKey, Decimal]) -> dict[OwnerKey, int]:
    """
    Split integer bag count across owners by weight ratio.
    Uses largest-remainder: remainder bags distributed one at a time to owners
    with the largest fractional part (tie-break by larger weight).
    """
    if total_bags <= 0:
        return {k: 0 for k in weights}
    if not weights:
        return {}

    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Cannot split bags with zero total owner input weight")

    keys = list(weights.keys())
    total_dec = Decimal(total_bags)
    raw = {k: total_dec * weights[k] / total_weight for k in keys}
    floored = {k: int(raw[k].to_integral_value(rounding=ROUND_DOWN)) for k in keys}
    allocated = sum(floored.values())
    remainder = total_bags - allocated
    if remainder > 0:
        fractional = sorted(
            keys,
            key=lambda k: (raw[k] - Decimal(floored[k]), weights[k]),
            reverse=True,
        )
        for i in range(remainder):
            floored[fractional[i % len(fractional)]] += 1
    return floored


def owner_key_from_line(line: dict) -> OwnerKey:
    ot = line.get("owner_type", "owned")
    if isinstance(ot, str) and ot != "job_work":
        return ("owned", None)
    cid = line.get("customer_id")
    if ot == "job_work":
        if cid is None:
            raise ValueError("customer_id required for job_work input line")
        return ("job_work", int(cid))
    return ("owned", None)
