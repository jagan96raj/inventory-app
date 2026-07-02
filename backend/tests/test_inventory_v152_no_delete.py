"""Spec v15.2 — inventory rows cannot be hard-deleted."""
import unittest
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import BagType, Brand, Inventory, Location, Product
from app.routers.inventory import INVENTORY_DELETE_FORBIDDEN_MSG
from app.services.idempotency import IDEMPOTENCY_KEY_HEADER
from tests.idempotency_helpers import TEST_USER, ensure_test_user


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
    bag_50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    db.add_all([product, brand, location, bag_50])
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_50": bag_50,
    }


class InventoryV152NoDeleteTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _create_inventory(self, *, bag_count: int = 10) -> dict:
        m = self.m
        res = self.client.post(
            "/api/inventory",
            json={
                "product_id": m["product"].id,
                "brand_id": m["brand"].id,
                "location_id": m["location"].id,
                "bag_type_id": m["bag_50"].id,
                "bag_count": bag_count,
                "loose_kg": "0",
            },
            headers={IDEMPOTENCY_KEY_HEADER: str(uuid4())},
        )
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def test_delete_inventory_forbidden_as_owner(self):
        created = self._create_inventory()
        inv_id = created["id"]

        res = self.client.delete(f"/api/inventory/{inv_id}")
        self.assertIn(res.status_code, (403, 405))
        self.assertEqual(res.json()["detail"], INVENTORY_DELETE_FORBIDDEN_MSG)

        row = self.db.get(Inventory, inv_id)
        self.assertIsNotNone(row)
        self.assertEqual(row.bag_count, 10)

    def test_opening_stock_post_still_works(self):
        created = self._create_inventory(bag_count=5)
        self.assertEqual(created["bag_count"], 5)
        self.assertEqual(Decimal(str(created["total_quantity_kg"])), Decimal("250"))

    def test_stock_disposal_reduces_stock(self):
        created = self._create_inventory(bag_count=10)
        m = self.m
        res = self.client.post(
            "/api/operations/stock-disposal",
            json={
                "location_id": m["location"].id,
                "product_id": m["product"].id,
                "brand_id": m["brand"].id,
                "bag_type_id": m["bag_50"].id,
                "bag_count": 10,
                "loose_kg": "0",
                "reason": "cleared",
                "notes": None,
            },
            headers={IDEMPOTENCY_KEY_HEADER: str(uuid4())},
        )
        self.assertEqual(res.status_code, 201, res.text)

        row = self.db.get(Inventory, created["id"])
        self.assertIsNone(row)

    def test_partial_disposal_leaves_row(self):
        created = self._create_inventory(bag_count=10)
        m = self.m
        res = self.client.post(
            "/api/operations/stock-disposal",
            json={
                "location_id": m["location"].id,
                "product_id": m["product"].id,
                "brand_id": m["brand"].id,
                "bag_type_id": m["bag_50"].id,
                "bag_count": 3,
                "loose_kg": "0",
                "reason": "damaged",
                "notes": None,
            },
            headers={IDEMPOTENCY_KEY_HEADER: str(uuid4())},
        )
        self.assertEqual(res.status_code, 201, res.text)

        row = self.db.get(Inventory, created["id"])
        self.assertIsNotNone(row)
        self.assertEqual(row.bag_count, 7)


if __name__ == "__main__":
    unittest.main()
