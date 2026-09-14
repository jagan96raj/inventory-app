"""Display-only sales bill stock hints. Billing never writes inventory."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    Bill,
    BillLine,
    BillStatus,
    BillType,
    Inventory,
    InventoryOwnerType,
    StockSource,
)
from app.services.bills import bags_delivered_count
from app.services.fulfillment import net_fulfilled_kg

SkuKey = tuple[int, int, int, str, int | None]


@dataclass(frozen=True)
class OpenBillRemaining:
    bill_id: int
    bill_date: date
    remaining_kg: Decimal
    remaining_bags: int = 0


@dataclass(frozen=True)
class SalesStockHint:
    available_kg: Decimal
    available_bags: int
    reserved_kg: Decimal
    reserved_bags: int


@dataclass(frozen=True)
class SalesStockHintItem:
    product_id: int
    brand_id: int
    bag_type_id: int
    stock_source: str
    customer_id: int | None
    on_hand_kg: Decimal
    on_hand_bags: int
    open_bills: tuple[OpenBillRemaining, ...]


def compute_sales_stock_hint(
    on_hand_kg: Decimal,
    other_open_bills: Sequence[OpenBillRemaining],
    *,
    on_hand_bags: int = 0,
) -> SalesStockHint:
    """Available = physical on_hand. Reserved = remaining on OTHER open bills of this SKU."""
    bills = [
        b
        for b in other_open_bills
        if Decimal(b.remaining_kg) > 0 or int(b.remaining_bags or 0) > 0
    ]
    reserved_kg = sum((Decimal(b.remaining_kg) for b in bills), Decimal("0"))
    reserved_bags = sum((int(b.remaining_bags or 0) for b in bills), 0)
    return SalesStockHint(
        available_kg=Decimal(on_hand_kg),
        available_bags=int(on_hand_bags),
        reserved_kg=reserved_kg,
        reserved_bags=reserved_bags,
    )


def _sku_key(
    product_id: int,
    brand_id: int,
    bag_type_id: int,
    stock_source: str,
    customer_id: int | None,
) -> SkuKey:
    return (product_id, brand_id, bag_type_id, stock_source, customer_id)


def _line_remaining_bags(line: BillLine, bill: Bill) -> int:
    if line.bag_type and line.bag_type.is_loose:
        return 0
    delivered = bags_delivered_count(line, bill.bill_type)
    return max(int(line.ordered_bags or 0) - delivered, 0)


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
        .options(joinedload(BillLine.bag_type))
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
    for bill, line in db.execute(q).unique().all():
        remaining_kg = Decimal(line.ordered_quantity_kg or 0) - net_fulfilled_kg(line, bill.bill_type)
        remaining_bags = _line_remaining_bags(line, bill)
        if remaining_kg <= 0 and remaining_bags <= 0:
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
                remaining_kg=existing.remaining_kg + remaining_kg,
                remaining_bags=existing.remaining_bags + remaining_bags,
            )
        else:
            by_sku_bill[bill_key] = OpenBillRemaining(
                bill_id=bill.id,
                bill_date=bill.bill_date,
                remaining_kg=remaining_kg,
                remaining_bags=remaining_bags,
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

    on_hand: dict[SkuKey, tuple[Decimal, int]] = {}
    for inv in inv_rows:
        if inv.owner_type == InventoryOwnerType.job_work:
            source = StockSource.job_work.value
            cust_id = inv.customer_id
        else:
            source = StockSource.owned.value
            cust_id = None
        key = _sku_key(inv.product_id, inv.brand_id, inv.bag_type_id, source, cust_id)
        on_hand[key] = (Decimal(inv.total_quantity_kg or 0), int(inv.bag_count or 0))

    keys = set(on_hand) | set(remainings)
    items: list[SalesStockHintItem] = []
    for key in sorted(keys):
        product_id, brand_id, bag_type_id, source, cust_id = key
        kg, bags = on_hand.get(key, (Decimal("0"), 0))
        items.append(
            SalesStockHintItem(
                product_id=product_id,
                brand_id=brand_id,
                bag_type_id=bag_type_id,
                stock_source=source,
                customer_id=cust_id,
                on_hand_kg=kg,
                on_hand_bags=bags,
                open_bills=tuple(remainings.get(key, [])),
            )
        )
    return items
