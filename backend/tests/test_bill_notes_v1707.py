"""Spec v17.0.7 — optional notes on bills create/edit."""
import unittest
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
    BillType,
    Brand,
    Customer,
    Location,
    Product,
    User,
)
from tests.idempotency_helpers import ensure_test_user, new_test_idempotency_key


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class BillNotesV1707Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.product = Product(company_id=1, product_name="Wheat")
        self.brand = Brand(company_id=1, name="Local")
        self.location = Location(company_id=1, name="Godown")
        self.bag = BagType(company_id=1, name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
        self.customer = Customer(company_id=1, name="Buyer Co")
        self.db.add_all([self.product, self.brand, self.location, self.bag, self.customer])
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _create_payload(self, notes: str | None = "Deliver after 5pm"):
        return {
            "bill_type": BillType.sales.value,
            "customer_id": self.customer.id,
            "location_id": self.location.id,
            "discount_percent": "0",
            "adjustment": "0",
            "notes": notes,
            "lines": [
                {
                    "product_id": self.product.id,
                    "brand_id": self.brand.id,
                    "bag_type_id": self.bag.id,
                    "ordered_bags": 1,
                    "ordered_loose_kg": "0",
                    "rate_per_kg": "10",
                }
            ],
        }

    def test_create_bill_with_notes(self):
        res = self.client.post(
            "/api/bills",
            json=self._create_payload("Urgent delivery"),
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertEqual(data["notes"], "Urgent delivery")

        get_res = self.client.get(f"/api/bills/{data['id']}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["notes"], "Urgent delivery")

    def test_edit_bill_notes(self):
        created = self.client.post(
            "/api/bills",
            json=self._create_payload("First note"),
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(created.status_code, 201, created.text)
        bill = created.json()

        patched = self.client.patch(
            f"/api/bills/{bill['id']}",
            json={"expected_version": bill["version"], "notes": "Updated note"},
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["notes"], "Updated note")

    def test_blank_notes_stored_as_null(self):
        res = self.client.post(
            "/api/bills",
            json=self._create_payload("   "),
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 201, res.text)
        self.assertIsNone(res.json()["notes"])

    def test_list_includes_notes(self):
        created = self.client.post(
            "/api/bills",
            json=self._create_payload("Call before delivery"),
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(created.status_code, 201, created.text)
        bill_id = created.json()["id"]

        listed = self.client.get("/api/bills?bill_type=sales&limit=50")
        self.assertEqual(listed.status_code, 200, listed.text)
        item = next((b for b in listed.json()["items"] if b["id"] == bill_id), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["notes"], "Call before delivery")


if __name__ == "__main__":
    unittest.main()
