"""Spec v17.3.28 — company isolation / IDOR: company A cannot read or mutate company B by id."""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Bill,
    BillStatus,
    BillType,
    Brand,
    Company,
    CompanyNote,
    Customer,
    Inventory,
    InventoryOwnerType,
    JobWorkOrder,
    JobWorkOrderStatus,
    Location,
    Payment,
    PaymentMode,
    PaymentStatus,
    Product,
    User,
    UserRole,
)
from tests.idempotency_helpers import ensure_test_user, new_test_idempotency_key, void_auth_header
import unittest


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class CompanyIsolationIdorV17328Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)

        self.c1_customer = Customer(name="Acme Co1", company_id=1, debit_balance=Decimal("1000"))
        self.c1_product = Product(product_name="Wheat Co1", company_id=1)
        self.c1_brand = Brand(name="Raw Co1", company_id=1)
        self.c1_location = Location(name="WH Co1", company_id=1)
        self.c1_bag = BagType(
            name="50kg Co1", weight_per_bag_kg=Decimal("50"), is_loose=False, company_id=1
        )
        self.db.add_all(
            [self.c1_customer, self.c1_product, self.c1_brand, self.c1_location, self.c1_bag]
        )
        self.db.flush()

        self.c1_bill = Bill(
            company_id=1,
            bill_number="S-000001",
            bill_type=BillType.sales,
            status=BillStatus.finalized,
            bill_date=date(2026, 7, 1),
            customer_id=self.c1_customer.id,
            location_id=self.c1_location.id,
            subtotal=Decimal("1000"),
            grand_total=Decimal("1000"),
            amount_paid=Decimal("0"),
            payment_status=PaymentStatus.unpaid,
            version=1,
        )
        self.c1_inv = Inventory(
            company_id=1,
            product_id=self.c1_product.id,
            brand_id=self.c1_brand.id,
            location_id=self.c1_location.id,
            bag_type_id=self.c1_bag.id,
            owner_type=InventoryOwnerType.owned,
            bag_count=10,
            loose_kg=Decimal("0"),
        )
        self.c1_payment = Payment(
            bill_id=None,  # set after flush
            amount=Decimal("100"),
            payment_mode=PaymentMode.cash,
            paid_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        self.db.add_all([self.c1_bill, self.c1_inv])
        self.db.flush()
        self.c1_payment.bill_id = self.c1_bill.id
        self.db.add(self.c1_payment)

        self.c1_jw = JobWorkOrder(
            company_id=1,
            job_number="JW-000001",
            customer_id=self.c1_customer.id,
            job_date=date(2026, 7, 1),
            status=JobWorkOrderStatus.open,
        )
        self.c1_note = CompanyNote(
            company_id=1,
            title="Secret note",
            body="Company 1 only",
            note_date=date(2026, 7, 1),
            created_by_user_id=1,
            updated_by_user_id=1,
        )
        self.db.add_all([self.c1_jw, self.c1_note])

        self.db.add(Company(id=2, name="Other Co", is_active=True))
        self.db.flush()
        self.user2 = User(
            id=2,
            email="other@example.com",
            name="Other Owner",
            password_hash="x",
            role=UserRole.owner,
            company_id=2,
            is_active=True,
        )
        self.c2_customer = Customer(name="Beta Co2", company_id=2)
        self.c2_product = Product(product_name="Rice Co2", company_id=2)
        self.c2_brand = Brand(name="Raw Co2", company_id=2)
        self.c2_location = Location(name="WH Co2", company_id=2)
        self.c2_bag = BagType(
            name="50kg Co2", weight_per_bag_kg=Decimal("50"), is_loose=False, company_id=2
        )
        self.db.add_all(
            [
                self.user2,
                self.c2_customer,
                self.c2_product,
                self.c2_brand,
                self.c2_location,
                self.c2_bag,
            ]
        )
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self._as_company2()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _as_company1(self):
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)

    def _as_company2(self):
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 2)

    def test_cannot_get_company1_bill(self):
        res = self.client.get(f"/api/bills/{self.c1_bill.id}")
        self.assertEqual(res.status_code, 404, res.text)

    def test_cannot_patch_company1_bill(self):
        res = self.client.patch(
            f"/api/bills/{self.c1_bill.id}",
            json={"notes": "hacked", "expected_version": 1},
            headers={**void_auth_header(), "Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertIn(res.status_code, (400, 404), res.text)

    def test_cannot_get_company1_payment(self):
        res = self.client.get(f"/api/payments/{self.c1_payment.id}")
        self.assertEqual(res.status_code, 404, res.text)

    def test_cannot_post_payment_on_company1_bill(self):
        res = self.client.post(
            "/api/payments",
            json={
                "bill_id": self.c1_bill.id,
                "amount": "10.00",
                "payment_mode": "cash",
                "paid_date": "2026-07-01",
                "expected_version": 1,
            },
            headers={**void_auth_header(), "Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertIn(res.status_code, (400, 404), res.text)

    def test_cannot_get_company1_customer(self):
        res = self.client.get(f"/api/customers/{self.c1_customer.id}")
        self.assertEqual(res.status_code, 404, res.text)

    def test_cannot_mutate_company1_inventory(self):
        res = self.client.put(
            f"/api/inventory/{self.c1_inv.id}",
            json={
                "product_id": self.c1_product.id,
                "brand_id": self.c1_brand.id,
                "location_id": self.c1_location.id,
                "bag_type_id": self.c1_bag.id,
                "bag_count": 99,
                "loose_kg": "0",
            },
            headers={**void_auth_header(), "Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 404, res.text)

    def test_cannot_get_company1_job_work(self):
        res = self.client.get(f"/api/job-work/{self.c1_jw.id}")
        self.assertEqual(res.status_code, 404, res.text)

    def test_cannot_get_or_patch_company1_note(self):
        get_res = self.client.get(f"/api/notes/{self.c1_note.id}")
        self.assertIn(get_res.status_code, (404, 405), get_res.text)

        patch_res = self.client.patch(
            f"/api/notes/{self.c1_note.id}",
            json={"body": "hacked"},
        )
        self.assertEqual(patch_res.status_code, 404, patch_res.text)

    def test_company1_still_reads_own_resources(self):
        self._as_company1()
        self.assertEqual(self.client.get(f"/api/bills/{self.c1_bill.id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/customers/{self.c1_customer.id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/payments/{self.c1_payment.id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/job-work/{self.c1_jw.id}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
