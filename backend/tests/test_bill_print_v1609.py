"""Spec v16.0.9 — bill print & PDF."""
import unittest
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import COOKIE_NAME, create_access_token, get_current_user
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
    UserRole,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
from tests.idempotency_helpers import configure_test_void_auth, idem_kwargs

STRONG_PASSWORD = "Test@123"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


OWNER = User(id=1, email="owner@test.com", name="Owner", role=UserRole.owner)


class TestBillPrintV1609(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_test_void_auth()

    def setUp(self):
        self.db = _make_session()
        self.db.add(
            User(
                id=OWNER.id,
                email=OWNER.email,
                name=OWNER.name,
                password_hash="x",
                role=OWNER.role,
            )
        )
        product = Product(product_name="Wheat")
        brand = Brand(name="Raw")
        location = Location(name="Warehouse")
        bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
        customer = Customer(
            name="Murugan Traders",
            address_line="12 Market Road",
            district="Coimbatore",
            state="Tamil Nadu",
            pin_code="641001",
            phone="9876543210",
        )
        self.db.add_all([product, brand, location, bag_type, customer])
        self.db.commit()
        self.masters = {
            "product": product,
            "brand": brand,
            "location": location,
            "bag_type": bag_type,
            "customer": customer,
        }

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: OWNER
        self.client = TestClient(app)
        token = create_access_token(OWNER.id)
        self.client.cookies.set(COOKIE_NAME, token)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_book_settings_company_fields_persist(self):
        res = self.client.patch(
            "/api/book-settings",
            json={
                "company_name": "Raj Agro Traders",
                "company_address_line": "45 Warehouse Lane, Coimbatore",
                "company_phone": "0422-1234567",
            },
            headers={"Idempotency-Key": "book-settings-company-v1609"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["company_name"], "Raj Agro Traders")
        self.assertEqual(body["company_address_line"], "45 Warehouse Lane, Coimbatore")
        self.assertEqual(body["company_phone"], "0422-1234567")

        get_res = self.client.get("/api/book-settings")
        self.assertEqual(get_res.status_code, 200)
        got = get_res.json()
        self.assertEqual(got["company_name"], "Raj Agro Traders")

    def test_bill_includes_customer_address_fields(self):
        body = BillFinalizeCreate(
            bill_type=BillType.purchase,
            customer_id=self.masters["customer"].id,
            discount_percent=Decimal("0"),
            adjustment=Decimal("0"),
            lines=[
                BillLineIn(
                    product_id=self.masters["product"].id,
                    brand_id=self.masters["brand"].id,
                    bag_type_id=self.masters["bag_type"].id,
                    ordered_bags=10,
                    ordered_loose_kg=Decimal("0"),
                    rate_per_kg=Decimal("100"),
                )
            ],
        )
        out = create_finalized_bill(body, db=self.db, user=OWNER, idempotency_key=idem_kwargs()["idempotency_key"])
        res = self.client.get(f"/api/bills/{out.id}")
        self.assertEqual(res.status_code, 200)
        bill = res.json()
        self.assertEqual(bill["customer_name"], "Murugan Traders")
        self.assertEqual(bill["customer_address_line"], "12 Market Road")
        self.assertEqual(bill["customer_district"], "Coimbatore")
        self.assertEqual(bill["customer_state"], "Tamil Nadu")
        self.assertEqual(bill["customer_pin_code"], "641001")
        self.assertEqual(bill["customer_phone"], "9876543210")
        self.assertGreaterEqual(len(bill["lines"]), 1)


if __name__ == "__main__":
    unittest.main()
