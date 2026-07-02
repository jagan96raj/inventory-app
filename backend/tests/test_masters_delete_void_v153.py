"""Spec v15.3 — master DELETE requires void authorization."""
import unittest
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.void_auth import VOID_AUTH_HEADER, VOID_AUTH_REQUIRED_MSG
from app.database import Base, get_db
from app.main import app
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
    User,
    UserRole,
)
from tests.idempotency_helpers import TEST_VOID_AUTH_PASSWORD, void_auth_header

OWNER = User(id=1, email="owner@test.com", name="Owner", role=UserRole.owner)
WRITER = User(id=2, email="writer@test.com", name="Writer", role=UserRole.writer)


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed(db: Session) -> dict:
    for u in (OWNER, WRITER):
        db.add(
            User(
                id=u.id,
                email=u.email,
                name=u.name,
                password_hash="x",
                role=u.role,
            )
        )
    product = Product(product_name="Wheat")
    brand = Brand(name="Brand A")
    customer = Customer(name="Customer One")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    db.add_all([product, brand, customer, location, bag_type])
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "customer": customer,
        "location": location,
        "bag_type": bag_type,
    }


def _add_bill(db: Session, m: dict) -> Bill:
    bill = Bill(
        bill_number="B-1",
        bill_type=BillType.sales,
        status=BillStatus.finalized,
        bill_date=date(2025, 1, 1),
        customer_id=m["customer"].id,
        location_id=m["location"].id,
        grand_total=Decimal("100"),
        subtotal=Decimal("100"),
        amount_paid=Decimal("0"),
        payment_status=PaymentStatus.unpaid,
        order_delivery_status=DeliveryStatus.not_delivered,
    )
    db.add(bill)
    db.flush()
    db.add(
        BillLine(
            bill_id=bill.id,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_type"].id,
            ordered_bags=1,
            ordered_loose_kg=Decimal("0"),
            ordered_quantity_kg=Decimal("50"),
            rate_per_kg=Decimal("2"),
            line_total=Decimal("100"),
        )
    )
    db.commit()
    return bill


class MastersDeleteVoidV153Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

        def override_db():
            yield self.db

        self._current = OWNER
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self._current
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _as(self, user: User):
        self._current = user

    def test_owner_delete_brand_without_void_header_forbidden(self):
        unused = Brand(name="Unused Brand")
        self.db.add(unused)
        self.db.commit()

        res = self.client.delete(f"/api/brands/{unused.id}")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], VOID_AUTH_REQUIRED_MSG)
        self.assertIsNotNone(self.db.get(Brand, unused.id))

    def test_owner_delete_brand_with_void_password_succeeds(self):
        unused = Brand(name="Unused Brand")
        self.db.add(unused)
        self.db.commit()

        res = self.client.delete(
            f"/api/brands/{unused.id}",
            headers=void_auth_header(TEST_VOID_AUTH_PASSWORD),
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json(), {"ok": True})
        self.assertIsNone(self.db.get(Brand, unused.id))

    def test_writer_delete_brand_forbidden(self):
        unused = Brand(name="Unused Brand")
        self.db.add(unused)
        self.db.commit()
        self._as(WRITER)

        res = self.client.delete(
            f"/api/brands/{unused.id}",
            headers=void_auth_header(TEST_VOID_AUTH_PASSWORD),
        )
        self.assertEqual(res.status_code, 403)

    def test_customer_with_bills_still_blocked_with_void_password(self):
        _add_bill(self.db, self.m)

        res = self.client.delete(
            f"/api/customers/{self.m['customer'].id}",
            headers=void_auth_header(TEST_VOID_AUTH_PASSWORD),
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("used on 1 bill", res.json()["detail"])
        self.assertIsNotNone(self.db.get(Customer, self.m["customer"].id))

    def test_invalid_void_password_rejected(self):
        unused = Brand(name="Another Unused")
        self.db.add(unused)
        self.db.commit()

        res = self.client.delete(
            f"/api/brands/{unused.id}",
            headers={VOID_AUTH_HEADER: "wrong-password"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIsNotNone(self.db.get(Brand, unused.id))


if __name__ == "__main__":
    unittest.main()
