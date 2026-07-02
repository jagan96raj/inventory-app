"""Spec v12.10 — GET bills read-only; no recalc on list/detail."""
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    BagType,
    Bill,
    BillLine,
    BillType,
    Brand,
    Customer,
    Location,
    Product,
)
from app.routers.bills import create_finalized_bill, edit_finalized_bill, get_bill, list_bills
from app.schemas import BillEditFinalized, BillFinalizeCreate, BillLineIn
from tests.idempotency_helpers import idem_kwargs


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_masters(db: Session) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="Readonly Test Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _line(m: dict, *, bags: int = 20, rate: str = "100") -> BillLineIn:
    return BillLineIn(
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
        ordered_bags=bags,
        ordered_loose_kg=Decimal("0"),
        rate_per_kg=Decimal(rate),
    )


def _create_sales_bill(db: Session, m: dict) -> Bill:
    out = create_finalized_bill(
        BillFinalizeCreate(
            bill_type=BillType.sales,
            bill_date=date(2026, 6, 1),
            customer_id=m["customer"].id,
            location_id=m["location"].id,
            discount_percent=Decimal("0"),
            adjustment=Decimal("0"),
            lines=[_line(m)],
        ),
        db=db,
        **idem_kwargs(),
    )
    bill = db.get(Bill, out.id)
    assert bill is not None
    return bill


def _db_snapshot(db: Session, bill_id: int) -> dict:
    bill = db.get(Bill, bill_id)
    assert bill is not None
    line = db.scalar(select(BillLine).where(BillLine.bill_id == bill_id))
    assert line is not None
    return {
        "grand_total": bill.grand_total,
        "subtotal": bill.subtotal,
        "line_total": line.line_total,
        "ordered_quantity_kg": line.ordered_quantity_kg,
    }


class BillsGetReadonlyV1210Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)
        self.bill = _create_sales_bill(self.db, self.m)

    def tearDown(self):
        self.db.close()

    def test_get_single_bill_matches_stored_totals(self):
        before = _db_snapshot(self.db, self.bill.id)
        out = get_bill(self.bill.id, db=self.db)
        self.assertEqual(out.grand_total, before["grand_total"])
        self.assertEqual(out.subtotal, before["subtotal"])
        self.assertEqual(out.grand_total, Decimal("100000"))
        self.assertEqual(len(out.lines), 1)
        self.assertEqual(out.lines[0].line_total, before["line_total"])
        self.assertEqual(out.lines[0].ordered_quantity_kg, before["ordered_quantity_kg"])
        self.assertEqual(out.lines[0].ordered_quantity_kg, Decimal("1000"))

    def test_get_single_bill_does_not_mutate_db(self):
        before = _db_snapshot(self.db, self.bill.id)
        get_bill(self.bill.id, db=self.db)
        after = _db_snapshot(self.db, self.bill.id)
        self.assertEqual(after, before)

    def test_get_list_does_not_mutate_db(self):
        before = _db_snapshot(self.db, self.bill.id)
        page = list_bills(bill_type=BillType.sales, db=self.db)
        self.assertEqual(page.total, 1)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].grand_total, before["grand_total"])
        after = _db_snapshot(self.db, self.bill.id)
        self.assertEqual(after, before)

    def test_patch_still_recalculates(self):
        line = self.db.scalar(select(BillLine).where(BillLine.bill_id == self.bill.id))
        assert line is not None
        updated = edit_finalized_bill(
            self.bill.id,
            BillEditFinalized(expected_version=1, lines=[{"id": line.id, "rate_per_kg": Decimal("120")}]),
            db=self.db,
            **idem_kwargs(),
        )
        self.assertEqual(updated.grand_total, Decimal("120000"))
        after = _db_snapshot(self.db, self.bill.id)
        self.assertEqual(after["grand_total"], Decimal("120000"))
        self.assertEqual(after["line_total"], Decimal("120000"))


if __name__ == "__main__":
    unittest.main()
