"""Display-only sales bill stock hints. Billing never writes inventory."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Bill,
    BillLine,
    BillStatus,
    BillType,
    Inventory,
    InventoryOwnerType,
    StockSource,
)
from app.services.fulfillment import net_fulfilled_kg

SkuKey = tuple[int, int, int, str, int | None]


@dataclass(frozen=True)
class OpenBillRemaining:
    bill_id: int
    bill_date: date
    remaining_kg: Decimal


@dataclass(frozen=True)
class SalesStockHint:
    available_kg: Decimal
    reserved_kg: Decimal
    not_delivered_kg: Decimal
    open_bill_count: int


@dataclass(frozen=True)
class SalesStockHintItem:
    product_id: int
    brand_id: int
    bag_type_id: int
    stock_source: str
    customer_id: int | None
    on_hand_kg: Decimal
    open_bills: tuple[OpenBillRemaining, ...]


def compute_sales_stock_hint(
    on_hand_kg: Decimal,
    open_bills: Sequence[OpenBillRemaining],
) -> SalesStockHint:
    """available = physical on_hand. Oldest open bill is excluded from reserved."""
    bills = [b for b in open_bills if Decimal(b.remaining_kg) > 0]
    bills.sort(key=lambda b: (b.bill_date, b.bill_id))
    not_delivered = sum((Decimal(b.remaining_kg) for b in bills), Decimal("0"))
    on_hand = Decimal(on_hand_kg)
    if len(bills) <= 1:
        reserved = Decimal("0")
    else:
        later_qty = sum((Decimal(b.remaining_kg) for b in bills[1:]), Decimal("0"))
        reserved = on_hand - later_qty
    return SalesStockHint(
        available_kg=on_hand,
        reserved_kg=reserved,
        not_delivered_kg=not_delivered,
        open_bill_count=len(bills),
    )


def _sku_key(
    product_id: int,
    brand_id: int,
    bag_type_id: int,
    stock_source: str,
    customer_id: int | None,
) -> SkuKey:
    return (product_id, brand_id, bag_type_id, stock_source, customer_id)


def list_open_sales_remainings(
    db: Session,
    *,
    company_id: int,
    location_id: int,
    exclude_bill_id: int | None = None,
) -> dict[SkuKey, list[OpenBillRemaining]]:
    q = (
        select(Bill, BillLine)
        .join(BillLine, BillLine.bill_id == Bill.id)
        .where(
            Bill.company_id == company_id,
            Bill.bill_type == BillType.sales,
            Bill.status == BillStatus.finalized,
            Bill.location_id == location_id,
        )
    )
    if exclude_bill_id is not None:
        q = q.where(Bill.id != exclude_bill_id)

    by_sku_bill: dict[tuple[SkuKey, int], OpenBillRemaining] = {}
    for bill, line in db.execute(q).all():
        remaining = Decimal(line.ordered_quantity_kg or 0) - net_fulfilled_kg(line, bill.bill_type)
        if remaining <= 0:
            continue
        source = (line.stock_source or StockSource.owned).value
        cust_id = bill.customer_id if source == StockSource.job_work.value else None
        key = _sku_key(line.product_id, line.brand_id, line.bag_type_id, source, cust_id)
        bill_key = (key, bill.id)
        existing = by_sku_bill.get(bill_key)
        if existing:
            by_sku_bill[bill_key] = OpenBillRemaining(
                bill_id=bill.id,
                bill_date=bill.bill_date,
                remaining_kg=existing.remaining_kg + remaining,
            )
        else:
            by_sku_bill[bill_key] = OpenBillRemaining(
                bill_id=bill.id,
                bill_date=bill.bill_date,
                remaining_kg=remaining,
            )

    out: dict[SkuKey, list[OpenBillRemaining]] = {}
    for (key, _bid), row in by_sku_bill.items():
        out.setdefault(key, []).append(row)
    for rows in out.values():
        rows.sort(key=lambda b: (b.bill_date, b.bill_id))
    return out


def list_sales_stock_hint_items(
    db: Session,
    *,
    company_id: int,
    location_id: int,
    exclude_bill_id: int | None = None,
) -> list[SalesStockHintItem]:
    remainings = list_open_sales_remainings(
        db,
        company_id=company_id,
        location_id=location_id,
        exclude_bill_id=exclude_bill_id,
    )
    inv_rows = db.scalars(
        select(Inventory).where(
            Inventory.company_id == company_id,
            Inventory.location_id == location_id,
        )
    ).all()

    on_hand: dict[SkuKey, Decimal] = {}
    for inv in inv_rows:
        if inv.owner_type == InventoryOwnerType.job_work:
            source = StockSource.job_work.value
            cust_id = inv.customer_id
        else:
            source = StockSource.owned.value
            cust_id = None
        key = _sku_key(inv.product_id, inv.brand_id, inv.bag_type_id, source, cust_id)
        on_hand[key] = Decimal(inv.total_quantity_kg or 0)

    keys = set(on_hand) | set(remainings)
    items: list[SalesStockHintItem] = []
    for key in sorted(keys):
        product_id, brand_id, bag_type_id, source, cust_id = key
        items.append(
            SalesStockHintItem(
                product_id=product_id,
                brand_id=brand_id,
                bag_type_id=bag_type_id,
                stock_source=source,
                customer_id=cust_id,
                on_hand_kg=on_hand.get(key, Decimal("0")),
                open_bills=tuple(remainings.get(key, [])),
            )
        )
    return items
