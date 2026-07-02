"""Spec v12.12 — schema-level non-negative guards on input quantities/rates/money."""
import unittest
from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    BillType,
    Brand,
    Customer,
    FulfillmentType,
    Location,
    PaymentMode,
    Product,
    User,
)
from app.routers.bills import create_finalized_bill
from app.schemas import (
    BagChangeCreate,
    BagChangeToLineIn,
    BagTypeCreate,
    BillEditLineIn,
    BillFinalizeCreate,
    BillLineIn,
    FulfillmentCreate,
    PaymentCreate,
    ProcessingBatchSubmit,
)
from app.services.idempotency import IDEMPOTENCY_KEY_HEADER
from tests.idempotency_helpers import TEST_USER, idem_kwargs, new_test_idempotency_key


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_masters(db: Session) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="Schema Guard Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _valid_line(m: dict) -> BillLineIn:
    return BillLineIn(
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
        ordered_bags=100,
        ordered_loose_kg=Decimal("0"),
        rate_per_kg=Decimal("100"),
    )


class SchemaNonnegV1212ValidationTests(unittest.TestCase):
    def test_bill_line_negative_rate_rejected(self):
        with self.assertRaises(ValidationError):
            BillLineIn(
                product_id=1,
                brand_id=1,
                bag_type_id=1,
                rate_per_kg=Decimal("-100"),
            )

    def test_bill_line_negative_bags_rejected(self):
        with self.assertRaises(ValidationError):
            BillLineIn(
                product_id=1,
                brand_id=1,
                bag_type_id=1,
                ordered_bags=-5,
                rate_per_kg=Decimal("100"),
            )

    def test_bill_line_negative_loose_kg_rejected(self):
        with self.assertRaises(ValidationError):
            BillLineIn(
                product_id=1,
                brand_id=1,
                bag_type_id=1,
                ordered_loose_kg=Decimal("-1"),
                rate_per_kg=Decimal("100"),
            )

    def test_bill_finalize_negative_discount_rejected(self):
        with self.assertRaises(ValidationError):
            BillFinalizeCreate(
                bill_type=BillType.purchase,
                customer_id=1,
                discount_percent=Decimal("-1"),
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

    def test_bill_finalize_discount_over_100_rejected(self):
        with self.assertRaises(ValidationError):
            BillFinalizeCreate(
                bill_type=BillType.purchase,
                customer_id=1,
                discount_percent=Decimal("101"),
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

    def test_bill_edit_line_negative_rate_rejected(self):
        with self.assertRaises(ValidationError):
            BillEditLineIn(id=1, rate_per_kg=Decimal("-1"))

    def test_payment_zero_amount_rejected(self):
        with self.assertRaises(ValidationError):
            PaymentCreate(
                bill_id=1,
                amount=Decimal("0"),
                payment_mode=PaymentMode.cash,
            )

    def test_payment_negative_amount_rejected(self):
        with self.assertRaises(ValidationError):
            PaymentCreate(
                bill_id=1,
                amount=Decimal("-500"),
                payment_mode=PaymentMode.cash,
            )

    def test_fulfillment_negative_quantity_rejected(self):
        with self.assertRaises(ValidationError):
            FulfillmentCreate(
                bill_line_id=1,
                entry_type=FulfillmentType.deliver,
                quantity_kg=Decimal("-10"),
            )

    def test_bag_change_negative_loss_rejected(self):
        with self.assertRaises(ValidationError):
            BagChangeCreate(
                location_id=1,
                product_id=1,
                brand_id=1,
                from_bag_type_id=1,
                quantity_loss_kg=Decimal("-1"),
                to_lines=[BagChangeToLineIn(to_bag_type_id=2)],
            )

    def test_processing_batch_negative_dust_rejected(self):
        with self.assertRaises(ValidationError):
            ProcessingBatchSubmit(dust_kg=Decimal("-1"))

    def test_bag_type_negative_weight_rejected(self):
        with self.assertRaises(ValidationError):
            BagTypeCreate(name="Bad", weight_per_bag_kg=Decimal("-50"))


class SchemaNonnegV1212RegressionTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def test_valid_bill_finalize_create_succeeds(self):
        created = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.purchase,
                customer_id=self.m["customer"].id,
                lines=[_valid_line(self.m)],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        self.assertGreater(created.grand_total, 0)

    def test_valid_payment_create_schema_accepts_positive_amount(self):
        payment = PaymentCreate(
            bill_id=1,
            amount=Decimal("100"),
            payment_mode=PaymentMode.cash,
        )
        self.assertEqual(payment.amount, Decimal("100"))


class SchemaNonnegV1212ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        self.db = _make_session()
        self.m = _seed_masters(self.db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_post_bill_negative_rate_returns_422(self):
        res = self.client.post(
            "/api/bills",
            json={
                "bill_type": "purchase",
                "customer_id": self.m["customer"].id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [
                    {
                        "product_id": self.m["product"].id,
                        "brand_id": self.m["brand"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "ordered_bags": 10,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "-100",
                    }
                ],
            },
            headers={IDEMPOTENCY_KEY_HEADER: new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 422)
        detail = res.json()["detail"]
        self.assertTrue(any("rate_per_kg" in str(err.get("loc", [])) for err in detail))


if __name__ == "__main__":
    unittest.main()
