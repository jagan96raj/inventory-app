"""Spec v12.16 — system timestamps only (no client date/time on create)."""
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Bill,
    BillLine,
    BillType,
    Brand,
    Customer,
    Inventory,
    Location,
    Payment,
    PaymentMode,
    Product,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn, PaymentCreate
from app.services.fulfillment import FulfillmentType, create_fulfillment
from app.services.idempotency import IDEMPOTENCY_KEY_HEADER
from app.services.operations import create_bag_change
from app.services.payments import create_payment
from app.utils.time import business_today, utc_now
from tests.idempotency_helpers import TEST_USER, TEST_VOID_AUTH_PASSWORD, ensure_test_user, idem_kwargs, new_test_idempotency_key, void_auth_header


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_masters(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    bag_25 = BagType(name="25kg", weight_per_bag_kg=Decimal("25"), is_loose=False)
    customer = Customer(name="Timestamp Co")
    db.add_all([product, brand, location, bag_50, bag_25, customer])
    db.flush()
    inv = Inventory(
        product_id=product.id,
        brand_id=brand.id,
        location_id=location.id,
        bag_type_id=bag_50.id,
        bag_count=100,
        loose_kg=Decimal("0"),
        total_quantity_kg=Decimal("5000"),
    )
    db.add(inv)
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_50": bag_50,
        "bag_25": bag_25,
        "customer": customer,
    }


def _bill_line_payload(m: dict) -> list[BillLineIn]:
    return [
        BillLineIn(
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_50"].id,
            ordered_bags=10,
            ordered_loose_kg=Decimal("0"),
            rate_per_kg=Decimal("100"),
        )
    ]


def _purchase_bill_with_line(db: Session, m: dict) -> tuple[Bill, BillLine]:
    created = create_finalized_bill(
        BillFinalizeCreate(
            bill_type=BillType.purchase,
            customer_id=m["customer"].id,
            lines=_bill_line_payload(m),
        ),
        db=db,
        **idem_kwargs(),
    )
    bill = db.get(Bill, created.id)
    assert bill is not None
    line = db.scalar(select(BillLine).where(BillLine.bill_id == bill.id))
    assert line is not None
    return bill, line


class SystemTimestampSchemaV1216Tests(unittest.TestCase):
    def test_bill_finalize_create_has_optional_bill_date_field(self):
        self.assertIn("bill_date", BillFinalizeCreate.model_fields)
        self.assertIsNone(BillFinalizeCreate.model_fields["bill_date"].default)

    def test_payment_create_has_optional_paid_date_field(self):
        self.assertIn("paid_date", PaymentCreate.model_fields)
        self.assertIsNone(PaymentCreate.model_fields["paid_date"].default)


class SystemTimestampMutationV1216Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    @patch("app.routers.bills.business_today", return_value=date(2026, 6, 18))
    def test_create_bill_sets_business_today_when_omitted(self, _mock_router_today, _mock_schema_today):
        created = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.purchase,
                customer_id=self.m["customer"].id,
                lines=_bill_line_payload(self.m),
            ),
            db=self.db,
            **idem_kwargs(),
        )
        bill = self.db.get(Bill, created.id)
        assert bill is not None
        self.assertEqual(bill.bill_date, date(2026, 6, 18))

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    @patch("app.routers.bills.business_today", return_value=date(2026, 6, 18))
    def test_create_bill_accepts_past_bill_date(self, _mock_router_today, _mock_schema_today):
        created = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.purchase,
                customer_id=self.m["customer"].id,
                bill_date=date(2026, 6, 10),
                lines=_bill_line_payload(self.m),
            ),
            db=self.db,
            **idem_kwargs(),
        )
        bill = self.db.get(Bill, created.id)
        assert bill is not None
        self.assertEqual(bill.bill_date, date(2026, 6, 10))

    @patch("app.services.payments.resolve_business_entry")
    def test_create_payment_sets_paid_at(self, mock_resolve):
        fixed = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
        mock_resolve.return_value = (fixed.date(), fixed)
        bill, _ = _purchase_bill_with_line(self.db, self.m)
        payment = create_payment(
            self.db,
            bill.id,
            Decimal("100"),
            PaymentMode.cash,
            expected_version=bill.version,
        )
        stored = payment.paid_at
        if stored.tzinfo is None:
            self.assertEqual(stored, fixed.replace(tzinfo=None))
        else:
            self.assertEqual(stored, fixed)

    @patch("app.services.fulfillment.resolve_business_entry")
    def test_create_fulfillment_sets_fulfilled_at(self, mock_resolve):
        fixed = datetime(2026, 6, 18, 14, 30, 0, tzinfo=timezone.utc)
        mock_resolve.return_value = (fixed.date(), fixed)
        bill, line = _purchase_bill_with_line(self.db, self.m)
        entry = create_fulfillment(
            self.db,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("100"),
            bag_count=2,
            loose_kg=Decimal("0"),
            location_id=self.m["location"].id,
            expected_version=bill.version,
        )
        stored = entry.fulfilled_at
        if stored.tzinfo is None:
            self.assertEqual(stored, fixed.replace(tzinfo=None))
        else:
            self.assertEqual(stored, fixed)

    @patch("app.services.operations.utc_now")
    def test_bag_change_sets_operation_at(self, mock_now):
        fixed = datetime(2026, 6, 18, 9, 15, 0, tzinfo=timezone.utc)
        mock_now.return_value = fixed
        m = self.m
        row = create_bag_change(
            self.db,
            location_id=m["location"].id,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            from_bag_type_id=m["bag_50"].id,
            from_bag_count=10,
            from_loose_kg=Decimal("0"),
            quantity_loss_kg=Decimal("0"),
            to_lines=[{"to_bag_type_id": m["bag_25"].id, "bag_count": 20, "loose_kg": Decimal("0")}],
            notes=None,
        )
        stored = row.operation_at
        if stored.tzinfo is None:
            self.assertEqual(stored, fixed.replace(tzinfo=None))
        else:
            self.assertEqual(stored, fixed)


class SystemTimestampApiV1216Tests(unittest.TestCase):
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

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    @patch("app.routers.bills.business_today", return_value=date(2026, 6, 18))
    def test_post_bill_without_bill_date_succeeds(self, _mock_router_today, _mock_schema_today):
        m = self.m
        res = self.client.post(
            "/api/bills",
            json={
                "bill_type": "purchase",
                "customer_id": m["customer"].id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [
                    {
                        "product_id": m["product"].id,
                        "brand_id": m["brand"].id,
                        "bag_type_id": m["bag_50"].id,
                        "ordered_bags": 5,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "100",
                    }
                ],
            },
            headers={IDEMPOTENCY_KEY_HEADER: new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["bill_date"], "2026-06-18")

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    @patch("app.routers.bills.business_today", return_value=date(2026, 6, 18))
    def test_post_bill_accepts_past_bill_date(self, _mock_router_today, _mock_schema_today):
        m = self.m
        res = self.client.post(
            "/api/bills",
            json={
                "bill_type": "purchase",
                "bill_date": "2020-01-01",
                "customer_id": m["customer"].id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [
                    {
                        "product_id": m["product"].id,
                        "brand_id": m["brand"].id,
                        "bag_type_id": m["bag_50"].id,
                        "ordered_bags": 5,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "100",
                    }
                ],
            },
            headers={**void_auth_header(), IDEMPOTENCY_KEY_HEADER: new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["bill_date"], "2020-01-01")

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    @patch("app.routers.bills.business_today", return_value=date(2026, 6, 18))
    def test_post_bill_rejects_future_bill_date(self, _mock_router_today, _mock_schema_today):
        m = self.m
        res = self.client.post(
            "/api/bills",
            json={
                "bill_type": "purchase",
                "bill_date": "2026-06-19",
                "customer_id": m["customer"].id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [
                    {
                        "product_id": m["product"].id,
                        "brand_id": m["brand"].id,
                        "bag_type_id": m["bag_50"].id,
                        "ordered_bags": 5,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "100",
                    }
                ],
            },
            headers={IDEMPOTENCY_KEY_HEADER: new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 422)


class SystemTimestampRegressionV1216Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def test_bill_payment_fulfillment_flow_still_works(self):
        bill, line = _purchase_bill_with_line(self.db, self.m)
        payment = create_payment(
            self.db,
            bill.id,
            Decimal("500"),
            PaymentMode.cash,
            expected_version=bill.version,
        )
        self.assertIsNotNone(payment.id)
        self.db.refresh(bill)
        entry = create_fulfillment(
            self.db,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("100"),
            bag_count=2,
            loose_kg=Decimal("0"),
            location_id=self.m["location"].id,
            expected_version=bill.version,
        )
        self.assertIsNotNone(entry.id)
        pay_count = self.db.scalar(select(func.count()).select_from(Payment))
        self.assertEqual(pay_count, 1)

    def test_business_today_and_utc_now_helpers(self):
        today = business_today()
        now = utc_now()
        self.assertIsInstance(today, date)
        self.assertIsNotNone(now.tzinfo)


if __name__ == "__main__":
    unittest.main()
