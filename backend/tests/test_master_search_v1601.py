"""Spec v16.0.1 — master list search for async form comboboxes."""
import unittest
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import BagType, Brand, Customer, Location, Product
from tests.idempotency_helpers import TEST_USER, ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class MasterSearchV1601Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.db.add_all(
            [
                Product(product_name="Wheat Flour"),
                Product(product_name="Rice Raw"),
                Brand(name="Raj Agro"),
                Brand(name="Mill Brand"),
                Location(name="Main Mill"),
                Location(name="Warehouse A"),
                BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False),
                BagType(name="Loose", weight_per_bag_kg=Decimal("0"), is_loose=True),
                Customer(name="Murugan Traders"),
                Customer(name="Sri Lakshmi Stores"),
            ]
        )
        self.db.commit()

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_product_search_subset(self):
        res = self.client.get("/api/products?search=wheat&limit=30&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["items"]), 1)
        self.assertIn("wheat", body["items"][0]["product_name"].lower())

    def test_brand_search_case_insensitive(self):
        res = self.client.get("/api/brands?search=raj&limit=30&offset=0")
        self.assertEqual(res.status_code, 200)
        names = [b["name"] for b in res.json()["items"]]
        self.assertIn("Raj Agro", names)

    def test_empty_search_returns_paginated_default(self):
        res = self.client.get("/api/products?limit=30&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 2)
        self.assertLessEqual(len(body["items"]), 30)

    def test_limit_respected(self):
        res = self.client.get("/api/customers?limit=1&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["limit"], 1)

    def test_get_product_by_id(self):
        pid = self.db.scalars(select(Product).where(Product.product_name == "Rice Raw")).one().id
        res = self.client.get(f"/api/products/{pid}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["product_name"], "Rice Raw")

    def test_get_bag_type_by_id(self):
        btid = self.db.scalars(select(BagType).where(BagType.name == "50kg")).one().id
        res = self.client.get(f"/api/bag-types/{btid}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["name"])


if __name__ == "__main__":
    unittest.main()
