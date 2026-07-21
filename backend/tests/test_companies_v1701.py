"""Spec v17.0.1 — multi-tenant Phase 2: company_id on business tables."""
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import Bill, BillType, Company, Customer, Product, User
from app.utils.time import business_today
from tests.idempotency_helpers import ensure_test_user, new_test_idempotency_key, void_auth_header


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class CompaniesV1701Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.db.add(Customer(name="Acme", company_id=1))
        self.db.add(Product(product_name="Wheat", company_id=1))
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_bootstrap_masters_and_bills_have_company_id_1(self):
        product = self.db.scalar(select(Product).where(Product.product_name == "Wheat"))
        customer = self.db.scalar(select(Customer).where(Customer.name == "Acme"))
        self.assertEqual(product.company_id, 1)
        self.assertEqual(customer.company_id, 1)

        bill = Bill(
            company_id=1,
            bill_number="S-000001",
            bill_type=BillType.sales,
            bill_date=__import__("datetime").date(2026, 7, 1),
            customer_id=customer.id,
        )
        self.db.add(bill)
        self.db.commit()
        self.assertEqual(self.db.get(Bill, bill.id).company_id, 1)

    def test_create_product_stamps_user_company_id(self):
        res = self.client.post("/api/products", json={"product_name": "Rice"})
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        created = self.db.get(Product, data["id"])
        self.assertEqual(created.company_id, 1)

    def test_same_product_name_allowed_in_different_companies(self):
        other = Company(id=2, name="Other Co", is_active=True)
        self.db.add(other)
        self.db.flush()
        self.db.add(Product(product_name="Wheat", company_id=2))
        self.db.commit()
        rows = self.db.scalars(select(Product).where(Product.product_name == "Wheat")).all()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r.company_id for r in rows}, {1, 2})

    def test_cross_company_customer_on_bill_create_rejected(self):
        other = Company(id=2, name="Other Co", is_active=True)
        self.db.add(other)
        self.db.flush()
        foreign = Customer(name="Foreign Customer", company_id=2)
        self.db.add(foreign)
        from app.models.entities import BagType, Brand, Location

        brand = Brand(name="Raw", company_id=1)
        location = Location(name="WH", company_id=1)
        bag = BagType(name="50kg", weight_per_bag_kg=50, is_loose=False, company_id=1)
        self.db.add_all([brand, location, bag])
        self.db.commit()
        product = self.db.scalar(select(Product).where(Product.product_name == "Wheat"))

        res = self.client.post(
            "/api/bills",
            json={
                "bill_type": "sales",
                "bill_date": business_today().isoformat(),
                "customer_id": foreign.id,
                "location_id": location.id,
                "discount_percent": 0,
                "adjustment": 0,
                "lines": [
                    {
                        "product_id": product.id,
                        "brand_id": brand.id,
                        "bag_type_id": bag.id,
                        "ordered_bags": 1,
                        "ordered_loose_kg": 0,
                        "rate_per_kg": 10,
                    }
                ],
            },
            headers={**void_auth_header(), "Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 400, res.text)
        self.assertIn("company", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
