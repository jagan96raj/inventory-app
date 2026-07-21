"""Spec v17.1.5 — bill money fields always persist at 2 decimal places."""
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    BagType,
    Bill,
    BillType,
    Brand,
    Customer,
    Location,
    Product,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
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
    customer = Customer(name="Money Round Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _at_most_2_dp(value: Decimal) -> bool:
    """True when Decimal has at most 2 fractional digits (exponent >= -2)."""
    return int(value.as_tuple().exponent) >= -2


class BillMoneyRoundingV1715Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def _create_fractional_discount_bill(self, bill_type: BillType) -> Bill:
        # 1 × 50kg @ 6.153 → line/subtotal 307.65; 2.5% → raw 7.69125 → 7.69
        body = BillFinalizeCreate(
            bill_type=bill_type,
            bill_date=date(2026, 1, 1),
            customer_id=self.m["customer"].id,
            location_id=self.m["location"].id if bill_type == BillType.sales else None,
            discount_percent=Decimal("2.5"),
            adjustment=Decimal("0"),
            lines=[
                BillLineIn(
                    product_id=self.m["product"].id,
                    brand_id=self.m["brand"].id,
                    bag_type_id=self.m["bag_type"].id,
                    ordered_bags=1,
                    ordered_loose_kg=Decimal("0"),
                    rate_per_kg=Decimal("6.153"),
                )
            ],
        )
        created = create_finalized_bill(body, db=self.db, **idem_kwargs())
        bill = self.db.get(Bill, created.id)
        assert bill is not None
        return bill

    def _assert_money_2dp(self, bill: Bill) -> None:
        self.assertEqual(bill.subtotal, Decimal("307.65"))
        self.assertEqual(bill.discount_amount, Decimal("7.69"))
        expected_grand = (
            bill.subtotal - bill.discount_amount - Decimal(bill.adjustment)
        ).quantize(Decimal("0.01"))
        self.assertEqual(bill.grand_total, expected_grand)
        self.assertEqual(bill.grand_total, Decimal("299.96"))

        self.assertTrue(_at_most_2_dp(bill.subtotal))
        self.assertTrue(_at_most_2_dp(bill.discount_amount))
        self.assertTrue(_at_most_2_dp(bill.grand_total))
        self.assertTrue(_at_most_2_dp(Decimal(bill.adjustment)))
        for line in bill.lines:
            self.assertTrue(_at_most_2_dp(line.line_total))
            self.assertEqual(line.line_total, Decimal("307.65"))

    def test_purchase_fractional_discount_rounds_to_2dp(self):
        bill = self._create_fractional_discount_bill(BillType.purchase)
        self._assert_money_2dp(bill)

    def test_sales_fractional_discount_rounds_to_2dp(self):
        bill = self._create_fractional_discount_bill(BillType.sales)
        self._assert_money_2dp(bill)


if __name__ == "__main__":
    unittest.main()
