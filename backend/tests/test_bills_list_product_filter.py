"""Bills list can filter by product_id."""
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


class BillsListProductFilterTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.wheat = Product(company_id=1, product_name="Wheat")
        self.bajra = Product(company_id=1, product_name="Bajra")
        self.brand = Brand(company_id=1, name="Local")
        self.location = Location(company_id=1, name="Godown")
        self.bag = BagType(
            company_id=1, name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False
        )
        self.customer = Customer(company_id=1, name="Buyer Co")
        self.db.add_all(
            [self.wheat, self.bajra, self.brand, self.location, self.bag, self.customer]
        )
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)
        self.client = TestClient(app)

        self._create_bill(self.wheat.id)
        self._create_bill(self.bajra.id)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _create_bill(self, product_id: int):
        res = self.client.post(
            "/api/bills",
            json={
                "bill_type": BillType.sales.value,
                "customer_id": self.customer.id,
                "location_id": self.location.id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [
                    {
                        "product_id": product_id,
                        "brand_id": self.brand.id,
                        "bag_type_id": self.bag.id,
                        "ordered_bags": 1,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "10",
                    }
                ],
            },
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def test_filter_by_product_id(self):
        all_bills = self.client.get("/api/bills?bill_type=sales").json()
        self.assertEqual(all_bills["total"], 2)

        wheat_only = self.client.get(
            f"/api/bills?bill_type=sales&product_id={self.wheat.id}"
        ).json()
        self.assertEqual(wheat_only["total"], 1)
        self.assertEqual(wheat_only["summary"]["total_count"], 1)

        bajra_only = self.client.get(
            f"/api/bills?bill_type=sales&product_id={self.bajra.id}"
        ).json()
        self.assertEqual(bajra_only["total"], 1)

        missing = self.client.get("/api/bills?bill_type=sales&product_id=99999").json()
        self.assertEqual(missing["total"], 0)


if __name__ == "__main__":
    unittest.main()
