"""Allow zero bags/qty on bill lines (drop a product on edit)."""
import unittest
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import BagType, BillType, Brand, Customer, Location, Product, User
from tests.idempotency_helpers import ensure_test_user, new_test_idempotency_key


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class BillZeroQtyTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.bajra = Product(company_id=1, product_name="Bajra")
        self.horse = Product(company_id=1, product_name="Horse Gram")
        self.brand = Brand(company_id=1, name="Local")
        self.location = Location(company_id=1, name="Godown")
        self.bag = BagType(company_id=1, name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
        self.customer = Customer(company_id=1, name="Buyer Co")
        self.db.add_all([self.bajra, self.horse, self.brand, self.location, self.bag, self.customer])
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _line(self, product_id: int, bags: int) -> dict:
        return {
            "product_id": product_id,
            "brand_id": self.brand.id,
            "bag_type_id": self.bag.id,
            "ordered_bags": bags,
            "ordered_loose_kg": "0",
            "rate_per_kg": "10",
        }

    def test_edit_can_zero_out_one_line(self):
        created = self.client.post(
            "/api/bills",
            json={
                "bill_type": BillType.sales.value,
                "customer_id": self.customer.id,
                "location_id": self.location.id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [self._line(self.bajra.id, 10), self._line(self.horse.id, 5)],
            },
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(created.status_code, 201, created.text)
        bill = created.json()
        self.assertEqual(len(bill["lines"]), 2)
        horse_line = next(ln for ln in bill["lines"] if ln["product_id"] == self.horse.id)
        bajra_line = next(ln for ln in bill["lines"] if ln["product_id"] == self.bajra.id)

        patched = self.client.patch(
            f"/api/bills/{bill['id']}",
            json={
                "expected_version": bill["version"],
                "lines": [
                    {"id": bajra_line["id"], "ordered_bags": 10, "rate_per_kg": "10"},
                    {"id": horse_line["id"], "ordered_bags": 0, "rate_per_kg": "10"},
                ],
            },
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        data = patched.json()
        horse_after = next(ln for ln in data["lines"] if ln["id"] == horse_line["id"])
        self.assertEqual(horse_after["ordered_bags"], 0)
        self.assertEqual(Decimal(horse_after["ordered_quantity_kg"]), Decimal("0"))
        self.assertEqual(Decimal(data["grand_total"]), Decimal("5000"))  # 10*50*10

    def test_cannot_zero_all_lines(self):
        created = self.client.post(
            "/api/bills",
            json={
                "bill_type": BillType.sales.value,
                "customer_id": self.customer.id,
                "location_id": self.location.id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [self._line(self.bajra.id, 2)],
            },
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(created.status_code, 201, created.text)
        bill = created.json()
        line_id = bill["lines"][0]["id"]

        patched = self.client.patch(
            f"/api/bills/{bill['id']}",
            json={
                "expected_version": bill["version"],
                "lines": [{"id": line_id, "ordered_bags": 0, "rate_per_kg": "10"}],
            },
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(patched.status_code, 400, patched.text)
        self.assertIn("greater than zero", patched.json()["detail"].lower())

    def test_create_rejects_all_zero_lines(self):
        res = self.client.post(
            "/api/bills",
            json={
                "bill_type": BillType.sales.value,
                "customer_id": self.customer.id,
                "location_id": self.location.id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [self._line(self.bajra.id, 0)],
            },
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 400, res.text)
        self.assertIn("greater than zero", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
