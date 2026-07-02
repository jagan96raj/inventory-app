"""Spec v12.14 — bill adjustment: no abs() masking in recalc_bill_totals."""
import unittest
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    BagType,
    Bill,
    BillLine,
    BillStatus,
    BillType,
    Brand,
    Customer,
    DeliveryStatus,
    Location,
    PaymentStatus,
    Product,
)
from app.routers.bills import create_finalized_bill, edit_finalized_bill
from app.schemas import BillEditFinalized, BillEditLineIn, BillFinalizeCreate, BillLineIn
from app.services.bills import (
    ADJUSTMENT_NEGATIVE_MSG,
    recalc_bill_totals,
    validate_adjustment_non_negative,
)
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
    customer = Customer(name="No-Abs Test Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _line(m: dict, *, bags: int = 100, rate: str = "100") -> BillLineIn:
    return BillLineIn(
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
        ordered_bags=bags,
        ordered_loose_kg=Decimal("0"),
        rate_per_kg=Decimal(rate),
    )


class BillAdjustmentNoAbsV1214ServiceTests(unittest.TestCase):
    def test_validate_adjustment_non_negative_rejects_negative(self):
        with self.assertRaises(ValueError) as ctx:
            validate_adjustment_non_negative(Decimal("-1"))
        self.assertEqual(str(ctx.exception), ADJUSTMENT_NEGATIVE_MSG)

    def test_recalc_bill_totals_rejects_negative_adjustment(self):
        db = _make_session()
        try:
            bill = Bill(
                bill_number="P-NEG-ADJ",
                bill_type=BillType.purchase,
                status=BillStatus.finalized,
                bill_date=date(2026, 6, 1),
                customer_id=1,
                subtotal=Decimal("500000"),
                discount_percent=Decimal("0"),
                discount_amount=Decimal("0"),
                adjustment=Decimal("-1000"),
                grand_total=Decimal("0"),
            )
            db.add(bill)
            db.flush()
            line = BillLine(
                bill_id=bill.id,
                product_id=1,
                brand_id=1,
                bag_type_id=1,
                ordered_bags=100,
                ordered_loose_kg=Decimal("0"),
                ordered_quantity_kg=Decimal("5000"),
                rate_per_kg=Decimal("100"),
                line_total=Decimal("500000"),
            )
            db.add(line)
            db.flush()

            with self.assertRaises(ValueError) as ctx:
                recalc_bill_totals(db, bill)
            self.assertEqual(str(ctx.exception), ADJUSTMENT_NEGATIVE_MSG)
        finally:
            db.close()

    def test_recalc_bill_totals_valid_adjustment_unchanged(self):
        db = _make_session()
        try:
            bill = Bill(
                bill_number="P-VALID-ADJ",
                bill_type=BillType.purchase,
                status=BillStatus.finalized,
                bill_date=date(2026, 6, 1),
                customer_id=1,
                subtotal=Decimal("500000"),
                discount_percent=Decimal("0"),
                discount_amount=Decimal("0"),
                adjustment=Decimal("1000"),
                grand_total=Decimal("0"),
            )
            db.add(bill)
            db.flush()
            line = BillLine(
                bill_id=bill.id,
                product_id=1,
                brand_id=1,
                bag_type_id=1,
                ordered_bags=100,
                ordered_loose_kg=Decimal("0"),
                ordered_quantity_kg=Decimal("5000"),
                rate_per_kg=Decimal("100"),
                line_total=Decimal("500000"),
            )
            db.add(line)
            db.flush()

            recalc_bill_totals(db, bill)
            self.assertEqual(bill.grand_total, Decimal("499000"))
            self.assertEqual(bill.adjustment, Decimal("1000"))
        finally:
            db.close()


class BillAdjustmentNoAbsV1214ApiTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def test_valid_create_with_adjustment_succeeds(self):
        created = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.purchase,
                bill_date=date(2026, 6, 1),
                customer_id=self.m["customer"].id,
                adjustment=Decimal("1000"),
                lines=[_line(self.m, bags=100, rate="100")],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        self.assertEqual(created.grand_total, Decimal("499000"))
        self.assertEqual(created.adjustment, Decimal("1000"))

    def test_valid_edit_increasing_adjustment_succeeds(self):
        created = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.purchase,
                bill_date=date(2026, 6, 1),
                customer_id=self.m["customer"].id,
                adjustment=Decimal("500"),
                lines=[_line(self.m, bags=100, rate="100")],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        updated = edit_finalized_bill(
            created.id,
            BillEditFinalized(expected_version=created.version, adjustment=Decimal("2000")),
            db=self.db,
            **idem_kwargs(),
        )
        self.assertEqual(updated.grand_total, Decimal("498000"))
        self.assertEqual(updated.adjustment, Decimal("2000"))

    def test_corrupt_negative_adjustment_row_fails_on_edit_recalc(self):
        bill = Bill(
            bill_number="P-CORRUPT",
            bill_type=BillType.purchase,
            status=BillStatus.finalized,
            bill_date=date(2026, 6, 1),
            customer_id=self.m["customer"].id,
            subtotal=Decimal("500000"),
            discount_percent=Decimal("0"),
            discount_amount=Decimal("0"),
            adjustment=Decimal("-500"),
            grand_total=Decimal("499500"),
            amount_paid=Decimal("0"),
            payment_status=PaymentStatus.unpaid,
            order_delivery_status=DeliveryStatus.not_delivered,
            version=1,
        )
        self.db.add(bill)
        self.db.flush()
        line = BillLine(
            bill_id=bill.id,
            product_id=self.m["product"].id,
            brand_id=self.m["brand"].id,
            bag_type_id=self.m["bag_type"].id,
            ordered_bags=100,
            ordered_loose_kg=Decimal("0"),
            ordered_quantity_kg=Decimal("5000"),
            rate_per_kg=Decimal("100"),
            line_total=Decimal("500000"),
        )
        self.db.add(line)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            edit_finalized_bill(
                bill.id,
                BillEditFinalized(
                    expected_version=1,
                    lines=[BillEditLineIn(id=line.id, rate_per_kg=Decimal("101"))],
                ),
                db=self.db,
                **idem_kwargs(),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, ADJUSTMENT_NEGATIVE_MSG)


if __name__ == "__main__":
    unittest.main()
