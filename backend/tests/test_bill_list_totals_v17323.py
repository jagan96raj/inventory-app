"""Spec v17.3.23 — bill list total_ordered_bags / total_ordered_kg."""
import unittest
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import BagType, BillType, Brand, Customer, Location, Product
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_kwargs


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class BillListTotalsV17323Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        product = Product(product_name="Jowar")
        brand = Brand(name="CH5")
        location = Location(name="Godown")
        bag50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
        loose = BagType(name="Loose", weight_per_bag_kg=Decimal("0"), is_loose=True)
        customer = Customer(name="List Totals Co")
        self.db.add_all([product, brand, location, bag50, loose, customer])
        self.db.flush()

        create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.sales,
                customer_id=customer.id,
                location_id=location.id,
                discount_percent=Decimal("0"),
                adjustment=Decimal("0"),
                lines=[
                    BillLineIn(
                        product_id=product.id,
                        brand_id=brand.id,
                        bag_type_id=bag50.id,
                        ordered_bags=10,
                        ordered_loose_kg=Decimal("0"),
                        rate_per_kg=Decimal("20"),
                    ),
                    BillLineIn(
                        product_id=product.id,
                        brand_id=brand.id,
                        bag_type_id=loose.id,
                        ordered_bags=0,
                        ordered_loose_kg=Decimal("12.5"),
                        rate_per_kg=Decimal("18"),
                    ),
                ],
            ),
            db=self.db,
            **idem_kwargs(),
        )

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_list_item_includes_ordered_bags_and_kg(self):
        r = self.client.get("/api/bills?bill_type=sales&limit=10&offset=0")
        self.assertEqual(r.status_code, 200)
        items = r.json()["items"]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["total_ordered_bags"], 10)
        self.assertEqual(Decimal(str(item["total_ordered_kg"])), Decimal("512.500"))


if __name__ == "__main__":
    unittest.main()
