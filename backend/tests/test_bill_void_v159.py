"""Spec v15.9 — conditional bill void (go-live drawback #19)."""
import unittest
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.services.bill_concurrency import EXPECTED_BILL_VERSION_HEADER
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Bill,
    BillStatus,
    BillType,
    BookSettings,
    Brand,
    CashBookEntryType,
    CashBookSourceMode,
    Customer,
    ExpenseCategory,
    ExpenseCategoryKind,
    Location,
    Product,
    PaymentMode,
    User,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
from app.services.bills import (
    BILL_VOID_HAS_FULFILLMENT_MSG,
    BILL_VOID_HAS_LINKED_CASHBOOK_MSG,
    BILL_VOID_HAS_PAYMENTS_MSG,
)
from app.services.cash_book import create_cash_book_entry
from app.services.fulfillment import FulfillmentType, create_fulfillment
from app.services.payments import create_payment
from tests.idempotency_helpers import (
    TEST_USER,
    TEST_VOID_AUTH_PASSWORD,
    ensure_test_user,
    idem_kwargs,
    idem_void_headers,
)


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="Void Test Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    if db.get(BookSettings, 1) is None:
        from datetime import date

        db.add(BookSettings(id=1, company_id=1, cash_opening_balance=Decimal("0"), cash_opening_balance_at=date.today()))
    freight = ExpenseCategory(name="Freight", kind=ExpenseCategoryKind.expense, is_system=False, is_active=True)
    db.add(freight)
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
        "freight": freight,
    }


def _bill_schema(m: dict, bill_type: BillType = BillType.purchase) -> BillFinalizeCreate:
    return BillFinalizeCreate(
        bill_type=bill_type,
        customer_id=m["customer"].id,
        location_id=m["location"].id if bill_type == BillType.sales else None,
        lines=[
            BillLineIn(
                product_id=m["product"].id,
                brand_id=m["brand"].id,
                bag_type_id=m["bag_type"].id,
                ordered_bags=10,
                ordered_loose_kg=Decimal("0"),
                rate_per_kg=Decimal("100"),
            )
        ],
    )


def _create_bill(db: Session, m: dict, bill_type: BillType = BillType.purchase) -> Bill:
    out = create_finalized_bill(_bill_schema(m, bill_type), db=db, **idem_kwargs())
    bill = db.get(Bill, out.id)
    assert bill is not None
    return bill


class BillVoidV159Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        self.db = _make_session()
        self.m = _seed(self.db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _void_headers(self, bill: Bill, key: str | None = None) -> dict:
        return {
            **idem_void_headers(key or str(uuid4()), TEST_VOID_AUTH_PASSWORD),
            EXPECTED_BILL_VERSION_HEADER: str(bill.version),
        }

    def test_clean_bill_void_ok(self):
        bill = _create_bill(self.db, self.m)
        pre = self.client.get(f"/api/bills/{bill.id}/void-precheck")
        self.assertEqual(pre.status_code, 200)
        self.assertTrue(pre.json()["can_void"])
        self.assertEqual(pre.json()["block_reasons"], [])

        credit_before = self.db.get(Customer, self.m["customer"].id).credit_balance
        res = self.client.post(f"/api/bills/{bill.id}/void", headers=self._void_headers(bill))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], BillStatus.voided.value)

        bill = self.db.get(Bill, bill.id)
        assert bill is not None
        self.assertEqual(bill.status, BillStatus.voided)
        self.assertIsNotNone(bill.voided_at)
        credit_after = self.db.get(Customer, self.m["customer"].id).credit_balance
        self.assertEqual(credit_after, credit_before - bill.grand_total)

        list_res = self.client.get("/api/bills?bill_type=purchase")
        self.assertEqual(list_res.json()["total"], 0)

    def test_reject_void_with_payment(self):
        bill = _create_bill(self.db, self.m)
        create_payment(self.db, bill.id, Decimal("100"), PaymentMode.cash, expected_version=bill.version)
        bill = self.db.get(Bill, bill.id)
        assert bill is not None

        pre = self.client.get(f"/api/bills/{bill.id}/void-precheck")
        self.assertFalse(pre.json()["can_void"])
        self.assertIn(BILL_VOID_HAS_PAYMENTS_MSG, pre.json()["block_reasons"])

        res = self.client.post(f"/api/bills/{bill.id}/void", headers=self._void_headers(bill))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["detail"], BILL_VOID_HAS_PAYMENTS_MSG)

    def test_reject_void_with_fulfillment(self):
        bill = _create_bill(self.db, self.m, BillType.purchase)
        line = bill.lines[0]
        create_fulfillment(
            self.db,
            line.id,
            FulfillmentType.deliver,
            Decimal("50"),
            1,
            Decimal("0"),
            location_id=self.m["location"].id,
            expected_version=bill.version,
        )
        bill = self.db.get(Bill, bill.id)
        assert bill is not None

        pre = self.client.get(f"/api/bills/{bill.id}/void-precheck")
        self.assertFalse(pre.json()["can_void"])
        self.assertIn(BILL_VOID_HAS_FULFILLMENT_MSG, pre.json()["block_reasons"])

        res = self.client.post(f"/api/bills/{bill.id}/void", headers=self._void_headers(bill))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["detail"], BILL_VOID_HAS_FULFILLMENT_MSG)

    def test_reject_void_with_linked_cashbook(self):
        bill = _create_bill(self.db, self.m)
        create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["freight"].id,
            amount=Decimal("50"),
            description="Freight",
            reference_no=None,
            bill_id=bill.id,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        bill = self.db.get(Bill, bill.id)
        assert bill is not None

        pre = self.client.get(f"/api/bills/{bill.id}/void-precheck")
        self.assertFalse(pre.json()["can_void"])
        self.assertIn(BILL_VOID_HAS_LINKED_CASHBOOK_MSG, pre.json()["block_reasons"])
        self.assertEqual(pre.json()["linked_active_entries_count"], 1)

        res = self.client.post(f"/api/bills/{bill.id}/void", headers=self._void_headers(bill))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["detail"], BILL_VOID_HAS_LINKED_CASHBOOK_MSG)

    def test_void_requires_auth(self):
        bill = _create_bill(self.db, self.m)
        headers = {EXPECTED_BILL_VERSION_HEADER: str(bill.version), "Idempotency-Key": str(uuid4())}
        res = self.client.post(f"/api/bills/{bill.id}/void", headers=headers)
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
