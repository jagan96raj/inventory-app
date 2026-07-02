from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import BagType, Inventory


def normalize_name(value: str) -> str:
    return value.strip()


def calc_quantity_kg(bag_type: BagType, bag_count: int, loose_kg: Decimal) -> Decimal:
    if bag_type.is_loose:
        return Decimal(loose_kg)
    return Decimal(bag_count) * Decimal(bag_type.weight_per_bag_kg)


def validate_bags_loose(bag_type: BagType, bag_count: int, loose_kg: Decimal) -> None:
    """Validate a transaction line — quantity must be greater than zero."""
    if bag_type.is_loose:
        if bag_count != 0:
            raise ValueError("Loose bag type cannot have bag count")
        if loose_kg <= 0:
            raise ValueError("Loose quantity must be greater than zero")
    else:
        if bag_count <= 0:
            raise ValueError("Bagged inventory requires at least one bag")
        if loose_kg != 0:
            raise ValueError("Bagged inventory cannot have loose kg")


def validate_inventory_row_state(bag_type: BagType, bag_count: int, loose_kg: Decimal) -> None:
    """Validate stored inventory — zero bags/kg is allowed (empty stock)."""
    if bag_type.is_loose:
        if bag_count != 0:
            raise ValueError("Loose bag type cannot have bag count")
    else:
        if loose_kg != 0:
            raise ValueError("Bagged inventory cannot have loose kg")


def validate_bag_type_fields(name: str, weight_per_bag_kg: Decimal, is_loose: bool) -> None:
    if is_loose:
        if weight_per_bag_kg != 0:
            raise ValueError("Loose bag type must have weight_per_bag_kg = 0")
    else:
        if weight_per_bag_kg <= 0:
            raise ValueError("Non-loose bag type must have weight_per_bag_kg > 0")


def recalc_inventory_row(inv: Inventory, bag_type: BagType) -> None:
    validate_inventory_row_state(bag_type, inv.bag_count, inv.loose_kg)
    inv.total_quantity_kg = calc_quantity_kg(bag_type, inv.bag_count, inv.loose_kg)


def delivery_status_from_qty(ordered: Decimal, net: Decimal) -> str:
    if net <= 0:
        return "not_delivered"
    if net >= ordered:
        return "delivered"
    return "partial"
