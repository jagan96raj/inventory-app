"""Spec v12.11 — bill row lock on concurrent bill writes."""
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
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
    FulfillmentType,
    Location,
    PaymentMode,
    Product,
)
from app.routers.bills import edit_finalized_bill
from app.schemas import BillEditFinalized, BillFinalizeCreate, BillLineIn
from app.services.bill_lock import BILL_IN_USE_MSG, lock_bill_for_update
from app.services.fulfillment import create_fulfillment, void_fulfillment_entry
from app.services.payments import create_payment, void_payment
from tests.idempotency_helpers import idem_kwargs


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db: Session) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="Lock Test Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _line(m: dict, *, bags: int = 2) -> BillLineIn:
    return BillLineIn(
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
        ordered_bags=bags,
        ordered_loose_kg=Decimal("0"),
        rate_per_kg=Decimal("100"),
    )


def _create_bill(db: Session, m: dict) -> Bill:
    out = BillFinalizeCreate(
        bill_type=BillType.purchase,
        bill_date=date(2026, 6, 1),
        customer_id=m["customer"].id,
        discount_percent=Decimal("0"),
        adjustment=Decimal("0"),
        lines=[_line(m)],
    )
    from app.routers.bills import create_finalized_bill

    created = create_finalized_bill(out, db=db, **idem_kwargs())
    bill = db.get(Bill, created.id)
    assert bill is not None
    return bill


class BillLockV1211Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        self.bill = _create_bill(self.db, self.m)

    def tearDown(self):
        self.db.close()

    def test_lock_bill_for_update_returns_bill(self):
        locked = lock_bill_for_update(self.db, self.bill.id)
        self.assertIsNotNone(locked)
        self.assertEqual(locked.id, self.bill.id)

    def test_edit_bill_returns_in_use_message_when_locked(self):
        with patch("app.routers.bills.lock_bill_for_update", side_effect=ValueError(BILL_IN_USE_MSG)):
            with self.assertRaises(HTTPException) as ctx:
                edit_finalized_bill(
                    self.bill.id, BillEditFinalized(expected_version=1), db=self.db, **idem_kwargs()
                )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, BILL_IN_USE_MSG)

    def test_create_payment_returns_in_use_message_when_locked(self):
        with patch("app.services.payments.lock_bill_for_update", side_effect=ValueError(BILL_IN_USE_MSG)):
            with self.assertRaises(ValueError) as ctx:
                create_payment(
                    self.db,
                    self.bill.id,
                    Decimal("100"),
                    payment_mode=PaymentMode.cash,
                    expected_version=1,
                )
        self.assertEqual(str(ctx.exception), BILL_IN_USE_MSG)

    def test_void_payment_returns_in_use_message_when_locked(self):
        payment = create_payment(
            self.db,
            self.bill.id,
            Decimal("100"),
            payment_mode=PaymentMode.cash,
            expected_version=1,
        )
        with patch("app.services.payments.lock_bills_for_update", side_effect=ValueError(BILL_IN_USE_MSG)):
            with self.assertRaises(ValueError) as ctx:
                void_payment(self.db, payment.id, expected_version=2)
        self.assertEqual(str(ctx.exception), BILL_IN_USE_MSG)

    def test_create_fulfillment_returns_in_use_message_when_locked(self):
        line = self.db.scalar(select(BillLine).where(BillLine.bill_id == self.bill.id))
        assert line is not None
        with patch("app.services.fulfillment.lock_bill_for_update", side_effect=ValueError(BILL_IN_USE_MSG)):
            with self.assertRaises(ValueError) as ctx:
                create_fulfillment(
                    self.db,
                    bill_line_id=line.id,
                    entry_type=FulfillmentType.deliver,
                    quantity_kg=Decimal("100"),
                    bag_count=2,
                    loose_kg=Decimal("0"),
                    location_id=self.m["location"].id,
                    expected_version=1,
                )
        self.assertEqual(str(ctx.exception), BILL_IN_USE_MSG)

    def test_void_fulfillment_returns_in_use_message_when_locked(self):
        line = self.db.scalar(select(BillLine).where(BillLine.bill_id == self.bill.id))
        assert line is not None
        entry = create_fulfillment(
            self.db,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("100"),
            bag_count=2,
            loose_kg=Decimal("0"),
            location_id=self.m["location"].id,
            expected_version=1,
        )
        with patch("app.services.fulfillment.lock_bill_for_update", side_effect=ValueError(BILL_IN_USE_MSG)):
            with self.assertRaises(ValueError) as ctx:
                void_fulfillment_entry(self.db, entry.id, expected_version=2)
        self.assertEqual(str(ctx.exception), BILL_IN_USE_MSG)


if __name__ == "__main__":
    unittest.main()
