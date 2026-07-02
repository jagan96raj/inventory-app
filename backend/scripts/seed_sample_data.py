"""DEV ONLY — seeds demo bills/payments/fulfillment (not guarded; does not wipe DB).

Seed two months of sample bills, payments, and fulfillment using existing master data.

Creates purchase + sales bills for May and June 2026 with varied payment/delivery
statuses. Idempotent: skips bills whose bill_number already exists (DEMO-* prefix).

Usage:
    cd backend
    python scripts/seed_sample_data.py
    python scripts/seed_sample_data.py --force   # delete DEMO-* bills first
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models.entities import (
    BagType,
    Bill,
    BillLine,
    BillType,
    Brand,
    Customer,
    FulfillmentEntry,
    FulfillmentType,
    Location,
    Payment,
    Product,
)
from app.schemas import BillLineIn
from app.services.bills import finalize_bill, load_bill, recalc_line
from app.services.fulfillment import create_bill_fulfillment_event
from app.services.payments import create_payment
from app.models.entities import PaymentMode
from app.utils import validate_bags_loose

DEMO_PREFIX = "DEMO-"


def _find_by_name(db: Session, model, field: str, name: str):
    rows = db.scalars(select(model)).all()
    target = name.strip().lower()
    for row in rows:
        if getattr(row, field).strip().lower() == target:
            return row
    for row in rows:
        if target in getattr(row, field).strip().lower():
            return row
    return rows[0] if rows else None


def _find_bag_type(db: Session, *, loose: bool = False, weight: Decimal | None = None) -> BagType:
    rows = db.scalars(select(BagType)).all()
    if loose:
        for bt in rows:
            if bt.is_loose:
                return bt
    if weight is not None:
        for bt in rows:
            if not bt.is_loose and bt.weight_per_bag_kg == weight:
                return bt
    for bt in rows:
        if not bt.is_loose:
            return bt
    return rows[0]


class Masters:
    def __init__(self, db: Session):
        self.db = db
        self.products = {p.product_name: p for p in db.scalars(select(Product)).all()}
        self.brands = {b.name: b for b in db.scalars(select(Brand)).all()}
        self.locations = {loc.name: loc for loc in db.scalars(select(Location)).all()}
        self.customers = {c.name: c for c in db.scalars(select(Customer)).all()}
        self.bag_50 = _find_bag_type(db, weight=Decimal("50"))
        self.bag_30 = _find_bag_type(db, weight=Decimal("30"))
        self.bag_100 = _find_bag_type(db, weight=Decimal("100"))
        self.bag_loose = _find_bag_type(db, loose=True)

    def product(self, name: str) -> Product:
        p = self.products.get(name) or _find_by_name(self.db, Product, "product_name", name)
        if not p:
            raise RuntimeError(f"Product not found: {name}")
        return p

    def brand(self, name: str) -> Brand:
        b = self.brands.get(name) or _find_by_name(self.db, Brand, "name", name)
        if not b:
            raise RuntimeError(f"Brand not found: {name}")
        return b

    def location(self, name: str) -> Location:
        loc = self.locations.get(name) or _find_by_name(self.db, Location, "name", name)
        if not loc:
            raise RuntimeError(f"Location not found: {name}")
        return loc

    def customer(self, name: str) -> Customer:
        c = self.customers.get(name) or _find_by_name(self.db, Customer, "name", name)
        if not c:
            raise RuntimeError(f"Customer not found: {name}")
        return c


def _dt(bill_date: date, hour: int = 10) -> datetime:
    return datetime(bill_date.year, bill_date.month, bill_date.day, hour, 0, 0, tzinfo=timezone.utc)


def _add_lines(db: Session, bill: Bill, lines_in: list[BillLineIn]) -> None:
    for li in lines_in:
        bt = db.get(BagType, li.bag_type_id)
        if not bt:
            raise ValueError(f"Invalid bag type {li.bag_type_id}")
        validate_bags_loose(bt, li.ordered_bags, li.ordered_loose_kg)
        line = BillLine(
            bill=bill,
            product_id=li.product_id,
            brand_id=li.brand_id,
            bag_type_id=li.bag_type_id,
            ordered_bags=li.ordered_bags,
            ordered_loose_kg=li.ordered_loose_kg,
            rate_per_kg=li.rate_per_kg,
        )
        recalc_line(line, bt)
        bill.lines.append(line)
    db.flush()


def create_demo_bill(
    db: Session,
    *,
    bill_number: str,
    bill_type: BillType,
    bill_date: date,
    customer_id: int,
    location_id: int | None,
    lines: list[BillLineIn],
    discount_percent: Decimal = Decimal("0"),
    adjustment: Decimal = Decimal("0"),
) -> tuple[Bill | None, bool]:
    existing = db.scalar(select(Bill).where(Bill.bill_number == bill_number))
    if existing:
        print(f"  Skip existing bill {bill_number}")
        return load_bill(db, existing.id), False

    bill = Bill(
        bill_number=bill_number,
        bill_type=bill_type,
        bill_date=bill_date,
        customer_id=customer_id,
        location_id=location_id if bill_type == BillType.sales else None,
        discount_percent=discount_percent,
        adjustment=adjustment,
    )
    db.add(bill)
    db.flush()
    _add_lines(db, bill, lines)
    db.flush()
    finalize_bill(db, bill)
    return load_bill(db, bill.id), True


def bill_has_fulfillment(db: Session, bill: Bill) -> bool:
    line_ids = [ln.id for ln in bill.lines]
    if not line_ids:
        return False
    count = db.scalar(
        select(func.count())
        .select_from(FulfillmentEntry)
        .where(FulfillmentEntry.bill_line_id.in_(line_ids))
    )
    return bool(count)


def fulfill_bill(
    db: Session,
    bill: Bill,
    *,
    receive_or_deliver_at: int | None = None,
    fraction: Decimal = Decimal("1"),
    fulfilled_at: datetime | None = None,
) -> None:
    if bill_has_fulfillment(db, bill):
        return
    if fraction <= 0:
        return
    at = fulfilled_at or _dt(bill.bill_date, 14)
    line_items: list[tuple[int, int, Decimal]] = []
    for line in bill.lines:
        bags = line.ordered_bags
        loose = line.ordered_loose_kg
        if line.bag_type and line.bag_type.is_loose:
            loose = (loose * fraction).quantize(Decimal("0.001"))
            if loose <= 0:
                continue
            line_items.append((line.id, 0, loose))
        else:
            eff_bags = int(Decimal(bags) * fraction)
            if eff_bags <= 0:
                continue
            line_items.append((line.id, eff_bags, Decimal("0")))
    if not line_items:
        return
    create_bill_fulfillment_event(
        db,
        bill.id,
        FulfillmentType.deliver,
        at,
        vehicle_no="TN-DEMO-01",
        line_items=line_items,
        location_id=receive_or_deliver_at,
    )


def add_payment(
    db: Session,
    bill: Bill,
    amount: Decimal,
    mode: PaymentMode,
    paid_at: datetime,
) -> None:
    if amount <= 0:
        return
    paid_so_far = sum((p.amount for p in bill.payments), Decimal("0"))
    if paid_so_far >= amount:
        return
    create_payment(db, bill.id, amount, mode, expected_version=1)


def clear_demo_data(db: Session) -> None:
    demo_bills = db.scalars(select(Bill).where(Bill.bill_number.like(f"{DEMO_PREFIX}%"))).all()
    if not demo_bills:
        print("No DEMO bills to remove.")
        return
    ids = [b.id for b in demo_bills]
    db.execute(delete(Payment).where(Payment.bill_id.in_(ids)))
    line_ids = db.scalars(select(BillLine.id).where(BillLine.bill_id.in_(ids))).all()
    if line_ids:
        db.execute(delete(FulfillmentEntry).where(FulfillmentEntry.bill_line_id.in_(line_ids)))
    db.execute(delete(BillLine).where(BillLine.bill_id.in_(ids)))
    db.execute(delete(Bill).where(Bill.id.in_(ids)))
    db.commit()
    print(f"Removed {len(ids)} DEMO bills and related rows.")


def seed_sample_data(db: Session) -> dict:
    m = Masters(db)
    unit = m.location("Raj Agro (UNIT)")
    godown = m.location("Raj Agro (Godown)")
    cust1 = m.customer("Sri Ragavendhra Traders")
    cust2 = m.customer("Sri Murugan Traders")

    created = {"bills": 0}

    def track(result: tuple[Bill | None, bool]) -> Bill | None:
        bill, is_new = result
        if is_new:
            created["bills"] += 1
        return bill

    print("Seeding May 2026...")

    # --- May purchases (stock in) ---
    p1 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250501",
            bill_type=BillType.purchase,
            bill_date=date(2026, 5, 1),
            customer_id=cust1.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Bajra").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=200,
                    rate_per_kg=Decimal("28"),
                ),
            ],
        )
    )
    if p1:
        fulfill_bill(db, p1, receive_or_deliver_at=godown.id, fraction=Decimal("1"))
        add_payment(db, p1, Decimal("100000"), PaymentMode.cash, _dt(date(2026, 5, 2)))

    p2 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250505",
            bill_type=BillType.purchase,
            bill_date=date(2026, 5, 5),
            customer_id=cust2.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Moong").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=150,
                    rate_per_kg=Decimal("45"),
                ),
            ],
        )
    )
    if p2:
        fulfill_bill(db, p2, receive_or_deliver_at=godown.id)

    p3 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250508",
            bill_type=BillType.purchase,
            bill_date=date(2026, 5, 8),
            customer_id=cust1.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Jowar (Milk)").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_30.id,
                    ordered_bags=100,
                    rate_per_kg=Decimal("32"),
                ),
            ],
        )
    )
    if p3:
        fulfill_bill(db, p3, receive_or_deliver_at=unit.id)
        add_payment(db, p3, p3.grand_total, PaymentMode.bank, _dt(date(2026, 5, 9)))

    p4 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250511",
            bill_type=BillType.purchase,
            bill_date=date(2026, 5, 11),
            customer_id=cust2.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Moong Polish").id,
                    brand_id=m.brand("Generic").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=60,
                    rate_per_kg=Decimal("40"),
                ),
            ],
        )
    )
    if p4:
        fulfill_bill(db, p4, receive_or_deliver_at=godown.id)

    p5 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250514",
            bill_type=BillType.purchase,
            bill_date=date(2026, 5, 14),
            customer_id=cust1.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Foxtail").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_loose.id,
                    ordered_loose_kg=Decimal("1000"),
                    rate_per_kg=Decimal("38"),
                ),
            ],
        )
    )
    if p5:
        fulfill_bill(db, p5, receive_or_deliver_at=unit.id)

    p6 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250516",
            bill_type=BillType.purchase,
            bill_date=date(2026, 5, 16),
            customer_id=cust2.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Corn").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_100.id,
                    ordered_bags=50,
                    rate_per_kg=Decimal("18"),
                ),
            ],
        )
    )
    if p6:
        fulfill_bill(db, p6, receive_or_deliver_at=godown.id)

    # --- May sales ---
    s1 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250503",
            bill_type=BillType.sales,
            bill_date=date(2026, 5, 3),
            customer_id=cust1.id,
            location_id=unit.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Bajra").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=80,
                    rate_per_kg=Decimal("35"),
                ),
            ],
        )
    )
    if s1:
        fulfill_bill(db, s1, fraction=Decimal("0.75"))
        add_payment(db, s1, Decimal("80000"), PaymentMode.cash, _dt(date(2026, 5, 4)))

    s2 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250510",
            bill_type=BillType.sales,
            bill_date=date(2026, 5, 10),
            customer_id=cust2.id,
            location_id=godown.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Moong").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=50,
                    rate_per_kg=Decimal("52"),
                ),
            ],
        )
    )
    if s2:
        fulfill_bill(db, s2)
        add_payment(db, s2, s2.grand_total, PaymentMode.bank, _dt(date(2026, 5, 11)))

    s3 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250512",
            bill_type=BillType.sales,
            bill_date=date(2026, 5, 12),
            customer_id=cust1.id,
            location_id=godown.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Moong Polish").id,
                    brand_id=m.brand("Generic").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=40,
                    rate_per_kg=Decimal("48"),
                ),
            ],
        )
    )
    # unpaid, not delivered

    s4 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250515",
            bill_type=BillType.sales,
            bill_date=date(2026, 5, 15),
            customer_id=cust2.id,
            location_id=unit.id,
            discount_percent=Decimal("5"),
            lines=[
                BillLineIn(
                    product_id=m.product("Foxtail").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_loose.id,
                    ordered_loose_kg=Decimal("800"),
                    rate_per_kg=Decimal("42"),
                ),
            ],
        )
    )
    if s4:
        fulfill_bill(db, s4, fraction=Decimal("0.625"))
        add_payment(db, s4, Decimal("15000"), PaymentMode.cash, _dt(date(2026, 5, 16)))

    s5 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250518",
            bill_type=BillType.sales,
            bill_date=date(2026, 5, 18),
            customer_id=cust1.id,
            location_id=godown.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Corn").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_100.id,
                    ordered_bags=20,
                    rate_per_kg=Decimal("22"),
                ),
            ],
        )
    )
    if s5:
        fulfill_bill(db, s5)
        add_payment(db, s5, s5.grand_total, PaymentMode.cash, _dt(date(2026, 5, 19)))

    s6 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250522",
            bill_type=BillType.sales,
            bill_date=date(2026, 5, 22),
            customer_id=cust2.id,
            location_id=unit.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Jowar (Milk)").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_30.id,
                    ordered_bags=35,
                    rate_per_kg=Decimal("38"),
                ),
            ],
        )
    )
    if s6:
        fulfill_bill(db, s6)
        add_payment(db, s6, Decimal("20000"), PaymentMode.cash, _dt(date(2026, 5, 23)))

    p6b = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250526",
            bill_type=BillType.purchase,
            bill_date=date(2026, 5, 26),
            customer_id=cust2.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Moong").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=40,
                    rate_per_kg=Decimal("43"),
                ),
            ],
        )
    )
    if p6b:
        fulfill_bill(db, p6b, receive_or_deliver_at=unit.id)

    s7 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250528",
            bill_type=BillType.sales,
            bill_date=date(2026, 5, 28),
            customer_id=cust1.id,
            location_id=unit.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Bajra").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=30,
                    rate_per_kg=Decimal("36"),
                ),
                BillLineIn(
                    product_id=m.product("Moong").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=20,
                    rate_per_kg=Decimal("55"),
                ),
            ],
        )
    )
    if s7:
        fulfill_bill(db, s7)

    print("Seeding June 2026...")

    p7 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250601",
            bill_type=BillType.purchase,
            bill_date=date(2026, 6, 1),
            customer_id=cust1.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Lobia").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=120,
                    rate_per_kg=Decimal("38"),
                ),
            ],
        )
    )
    if p7:
        fulfill_bill(db, p7, receive_or_deliver_at=godown.id)
        add_payment(db, p7, Decimal("100000"), PaymentMode.bank, _dt(date(2026, 6, 2)))

    s8 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250603",
            bill_type=BillType.sales,
            bill_date=date(2026, 6, 3),
            customer_id=cust2.id,
            location_id=godown.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Lobia").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=45,
                    rate_per_kg=Decimal("45"),
                ),
            ],
        )
    )

    p8 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250608",
            bill_type=BillType.purchase,
            bill_date=date(2026, 6, 8),
            customer_id=cust2.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Horse Gram").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=80,
                    rate_per_kg=Decimal("55"),
                ),
            ],
        )
    )
    if p8:
        fulfill_bill(db, p8, receive_or_deliver_at=godown.id, fraction=Decimal("0.625"))

    s9 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250610",
            bill_type=BillType.sales,
            bill_date=date(2026, 6, 10),
            customer_id=cust1.id,
            location_id=unit.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Bajra").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=100,
                    rate_per_kg=Decimal("36"),
                ),
            ],
        )
    )
    if s9:
        fulfill_bill(db, s9)
        add_payment(db, s9, s9.grand_total, PaymentMode.cash, _dt(date(2026, 6, 11)))

    s10 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250615",
            bill_type=BillType.sales,
            bill_date=date(2026, 6, 15),
            customer_id=cust2.id,
            location_id=godown.id,
            adjustment=Decimal("500"),
            lines=[
                BillLineIn(
                    product_id=m.product("Moong").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=75,
                    rate_per_kg=Decimal("54"),
                ),
            ],
        )
    )
    if s10:
        fulfill_bill(db, s10, fraction=Decimal("0.533"))
        add_payment(db, s10, Decimal("100000"), PaymentMode.bank, _dt(date(2026, 6, 16)))

    s11 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250620",
            bill_type=BillType.sales,
            bill_date=date(2026, 6, 20),
            customer_id=cust1.id,
            location_id=godown.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Corn").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_100.id,
                    ordered_bags=15,
                    rate_per_kg=Decimal("25"),
                ),
            ],
        )
    )
    if s11:
        fulfill_bill(db, s11)

    p9 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}P-250625",
            bill_type=BillType.purchase,
            bill_date=date(2026, 6, 25),
            customer_id=cust1.id,
            location_id=None,
            lines=[
                BillLineIn(
                    product_id=m.product("Moong").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=100,
                    rate_per_kg=Decimal("44"),
                ),
            ],
        )
    )
    if p9:
        fulfill_bill(db, p9, receive_or_deliver_at=unit.id)

    s12 = track(
        create_demo_bill(
            db,
            bill_number=f"{DEMO_PREFIX}S-250628",
            bill_type=BillType.sales,
            bill_date=date(2026, 6, 28),
            customer_id=cust2.id,
            location_id=godown.id,
            lines=[
                BillLineIn(
                    product_id=m.product("Horse Gram").id,
                    brand_id=m.brand("Raj Agro").id,
                    bag_type_id=m.bag_50.id,
                    ordered_bags=30,
                    rate_per_kg=Decimal("62"),
                ),
            ],
        )
    )
    if s12:
        fulfill_bill(db, s12)
        add_payment(db, s12, Decimal("50000"), PaymentMode.cash, _dt(date(2026, 6, 29)))

    demo_count = db.scalar(
        select(func.count()).select_from(Bill).where(Bill.bill_number.like(f"{DEMO_PREFIX}%"))
    )
    pay_count = db.scalar(
        select(func.count())
        .select_from(Payment)
        .join(Bill, Payment.bill_id == Bill.id)
        .where(Bill.bill_number.like(f"{DEMO_PREFIX}%"))
    )
    fulfill_count = db.scalar(
        select(func.count())
        .select_from(FulfillmentEntry)
        .join(BillLine, FulfillmentEntry.bill_line_id == BillLine.id)
        .join(Bill, BillLine.bill_id == Bill.id)
        .where(Bill.bill_number.like(f"{DEMO_PREFIX}%"))
    )
    return {
        "demo_bills": demo_count,
        "demo_payments": pay_count,
        "demo_fulfillment_entries": fulfill_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed two months of sample transactional data.")
    parser.add_argument("--force", action="store_true", help="Remove existing DEMO-* bills first")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.force:
            clear_demo_data(db)
        print("Using existing master data (products, brands, locations, customers, bag types)...")
        summary = seed_sample_data(db)
        print("Sample data seed complete.")
        print(f"  DEMO bills: {summary['demo_bills']}")
        print(f"  DEMO payments: {summary['demo_payments']}")
        print(f"  DEMO fulfillment entries: {summary['demo_fulfillment_entries']}")
    except Exception as exc:
        db.rollback()
        print(f"Seed failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
