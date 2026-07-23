"""Spec v16.0.19 — optional backdated transaction dates (past only, not future)."""
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from pydantic import ValidationError

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    BankAccount,
    BankAccountKind,
    Bill,
    BillLine,
    BillType,
    Brand,
    CashBookEntryType,
    Customer,
    ExpenseCategory,
    ExpenseCategoryKind,
    Inventory,
    Location,
    Payment,
    PaymentMode,
    Product,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn, FulfillmentCreate, PaymentCreate
from app.services.cash_book import create_cash_book_entry
from app.services.fulfillment import FulfillmentType, create_fulfillment
from app.services.payments import create_payment
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
    customer = Customer(name="Backdate Co")
    category = ExpenseCategory(name="Misc", kind=ExpenseCategoryKind.expense, is_active=True)
    cash_account = BankAccount(
        name="Cash", kind=BankAccountKind.cash,
        opening_balance=Decimal("0"), opening_balance_at=date.today(),
        is_default=False, is_active=True,
    )
    db.add_all([product, brand, location, bag_50, customer, category, cash_account])
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
        "customer": customer,
        "category": category,
        "cash_account": cash_account,
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


class BackdateSchemaV16019Tests(unittest.TestCase):
    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    def test_payment_create_accepts_past_paid_date(self, _mock_today):
        body = PaymentCreate(
            bill_id=1,
            amount=Decimal("100"),
            payment_mode=PaymentMode.cash,
            paid_date=date(2026, 6, 10),
        )
        self.assertEqual(body.paid_date, date(2026, 6, 10))

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    def test_payment_create_rejects_future_paid_date(self, _mock_today):
        with self.assertRaises(ValidationError):
            PaymentCreate(
                bill_id=1,
                amount=Decimal("100"),
                payment_mode=PaymentMode.cash,
                paid_date=date(2026, 6, 19),
            )

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    def test_fulfillment_create_rejects_future_fulfilled_date(self, _mock_today):
        with self.assertRaises(ValidationError):
            FulfillmentCreate(
                bill_line_id=1,
                entry_type=FulfillmentType.deliver,
                quantity_kg=Decimal("50"),
                fulfilled_date=date(2026, 6, 20),
            )


class BackdateServiceV16019Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    @patch("app.utils.time.business_today", return_value=date(2026, 6, 18))
    def test_create_payment_backdated(self, _mock_today):
        bill, _ = _purchase_bill_with_line(self.db, self.m)
        payment = create_payment(
            self.db,
            bill.id,
            Decimal("100"),
            PaymentMode.cash,
            expected_version=bill.version,
            paid_date=date(2026, 6, 10),
        )
        self.assertEqual(payment.paid_at.date(), date(2026, 6, 10))

    @patch("app.utils.time.business_today", return_value=date(2026, 6, 18))
    @patch("app.services.fulfillment.utc_now")
    def test_create_fulfillment_backdated(self, mock_now, _mock_today):
        mock_now.return_value = datetime(2026, 6, 18, 10, 0, 0, tzinfo=timezone.utc)
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
            fulfilled_date=date(2026, 6, 5),
        )
        self.assertEqual(entry.fulfilled_at.date(), date(2026, 6, 5))

    @patch("app.utils.time.business_today", return_value=date(2026, 6, 18))
    def test_create_cash_book_entry_backdated(self, _mock_today):
        entry = create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["category"].id,
            amount=Decimal("250"),
            description="Backdated",
            reference_no=None,
            bill_id=None,
            source_account_id=self.m["cash_account"].id,
            entry_date=date(2026, 6, 1),
        )
        self.assertEqual(entry.entry_date, date(2026, 6, 1))
        self.assertEqual(entry.entry_at.date(), date(2026, 6, 1))


class BackdateApiV16019Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        self.db = _make_session()
        self.m = _seed_masters(self.db)
        from app.config import settings

        settings.void_auth_password = TEST_VOID_AUTH_PASSWORD

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    @patch("app.utils.time.business_today", return_value=date(2026, 6, 18))
    def test_post_payment_with_past_paid_date(self, _mock_util_today, _mock_schema_today):
        bill, _ = _purchase_bill_with_line(self.db, self.m)
        res = self.client.post(
            "/api/payments",
            json={
                "bill_id": bill.id,
                "amount": "100",
                "payment_mode": "cash",
                "expected_version": bill.version,
                "paid_date": "2026-06-10",
            },
            headers={**void_auth_header(), "Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 201)
        payment = self.db.scalar(select(Payment).where(Payment.bill_id == bill.id))
        assert payment is not None
        self.assertEqual(payment.paid_at.date(), date(2026, 6, 10))

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    def test_post_payment_rejects_future_paid_date(self, _mock_today):
        bill, _ = _purchase_bill_with_line(self.db, self.m)
        res = self.client.post(
            "/api/payments",
            json={
                "bill_id": bill.id,
                "amount": "100",
                "payment_mode": "cash",
                "expected_version": bill.version,
                "paid_date": "2026-06-19",
            },
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 422)

    @patch("app.schemas.business_today", return_value=date(2026, 6, 18))
    @patch("app.utils.time.business_today", return_value=date(2026, 6, 18))
    def test_post_payment_past_date_requires_auth(self, _mock_util_today, _mock_schema_today):
        bill, _ = _purchase_bill_with_line(self.db, self.m)
        res = self.client.post(
            "/api/payments",
            json={
                "bill_id": bill.id,
                "amount": "100",
                "payment_mode": "cash",
                "expected_version": bill.version,
                "paid_date": "2026-06-10",
            },
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
