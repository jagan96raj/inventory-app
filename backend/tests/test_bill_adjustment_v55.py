"""Spec v5.5 — bill adjustment and final payable validation."""
import unittest
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    BagType,
    Bill,
    BillStatus,
    BillType,
    Brand,
    Customer,
    Location,
    Product,
)
from app.routers.bills import build_lines, create_finalized_bill, edit_finalized_bill
from app.schemas import BillEditFinalized, BillFinalizeCreate, BillLineIn
from app.services.bills import (
    FINAL_PAYABLE_NEGATIVE_MSG,
    finalize_bill,
    load_bill,
    next_bill_number,
    validate_bill_final_payable,
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
    customer = Customer(name="Adj Test Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _line(m: dict, *, bags: int = 10, rate: str = "100") -> BillLineIn:
    return BillLineIn(
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
        ordered_bags=bags,
        ordered_loose_kg=Decimal("0"),
        rate_per_kg=Decimal(rate),
    )


class BillAdjustmentV55SchemaTests(unittest.TestCase):
    def test_negative_adjustment_on_create_schema_rejected(self):
        with self.assertRaises(ValidationError):
            BillFinalizeCreate(
                bill_type=BillType.purchase,
                bill_date=date(2026, 1, 1),
                customer_id=1,
                adjustment=Decimal("-100"),
                lines=[
                    BillLineIn(
                        product_id=1,
                        brand_id=1,
                        bag_type_id=1,
                        ordered_bags=1,
                        rate_per_kg=Decimal("100"),
                    )
                ],
            )

    def test_negative_adjustment_on_edit_schema_rejected(self):
        with self.assertRaises(ValidationError):
            BillEditFinalized(adjustment=Decimal("-50"))


class BillAdjustmentV55ServiceTests(unittest.TestCase):
    def test_validate_bill_final_payable_negative(self):
        bill = Bill(
            bill_number="P-1",
            bill_type=BillType.purchase,
            status=BillStatus.finalized,
            bill_date=date.today(),
            customer_id=1,
            grand_total=Decimal("-1"),
        )
        with self.assertRaises(ValueError) as ctx:
            validate_bill_final_payable(bill)
        self.assertEqual(str(ctx.exception), FINAL_PAYABLE_NEGATIVE_MSG)


class BillAdjustmentV55ApiTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def _create_body(self, *, adjustment: str = "0") -> BillFinalizeCreate:
        return BillFinalizeCreate(
            bill_type=BillType.purchase,
            bill_date=date(2026, 1, 1),
            customer_id=self.m["customer"].id,
            discount_percent=Decimal("0"),
            adjustment=Decimal(adjustment),
            lines=[_line(self.m)],
        )

    def test_create_excessive_adjustment_blocked(self):
        with self.assertRaises(HTTPException) as ctx:
            create_finalized_bill(self._create_body(adjustment="60000"), db=self.db, **idem_kwargs())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, FINAL_PAYABLE_NEGATIVE_MSG)
        count = self.db.scalar(select(func.count()).select_from(Bill)) or 0
        self.assertEqual(count, 0)

    def test_create_valid_adjustment_persists(self):
        created = create_finalized_bill(self._create_body(adjustment="1000"), db=self.db, **idem_kwargs())
        self.assertEqual(created.grand_total, Decimal("49000"))
        customer = self.db.get(Customer, self.m["customer"].id)
        self.assertEqual(customer.credit_balance, Decimal("49000"))

    def test_edit_excessive_adjustment_blocked(self):
        created = create_finalized_bill(self._create_body(), db=self.db, **idem_kwargs())
        with self.assertRaises(HTTPException) as ctx:
            edit_finalized_bill(
                created.id,
                BillEditFinalized(expected_version=1, adjustment=Decimal("60000")),
                db=self.db,
                **idem_kwargs(),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, FINAL_PAYABLE_NEGATIVE_MSG)
        bill = load_bill(self.db, created.id)
        self.assertEqual(bill.grand_total, Decimal("50000"))

    def test_finalize_direct_negative_grand_total_blocked(self):
        bill = Bill(
            bill_number=next_bill_number(self.db, BillType.purchase),
            bill_type=BillType.purchase,
            bill_date=date(2026, 1, 1),
            customer_id=self.m["customer"].id,
            adjustment=Decimal("60000"),
        )
        self.db.add(bill)
        self.db.flush()
        build_lines(self.db, bill, [_line(self.m)])
        self.db.flush()
        with self.assertRaises(ValueError) as ctx:
            finalize_bill(self.db, bill)
        self.assertEqual(str(ctx.exception), FINAL_PAYABLE_NEGATIVE_MSG)


if __name__ == "__main__":
    unittest.main()
