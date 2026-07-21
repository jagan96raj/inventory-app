"""Spec v16.0.16 — allow duplicate sales bill lines; block purchase duplicates."""
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
from app.models.entities import (
    BagType,
    Bill,
    BillType,
    BookSettings,
    Brand,
    Customer,
    Location,
    Product,
    User,
)
from app.routers.bills import create_finalized_bill, validate_lines
from app.schemas import BillFinalizeCreate, BillLineIn
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_kwargs


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
    product = Product(product_name="Bajra")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="Split Qty Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    if db.get(BookSettings, 1) is None:
        from datetime import date

        db.add(BookSettings(id=1, company_id=1, cash_opening_balance=Decimal("0"), cash_opening_balance_at=date.today()))
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _duplicate_lines(m: dict, *, bags_each: int = 50) -> list[BillLineIn]:
    return [
        BillLineIn(
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_type"].id,
            ordered_bags=bags_each,
            ordered_loose_kg=Decimal("0"),
            rate_per_kg=Decimal("100"),
            stock_source="owned",
        ),
        BillLineIn(
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_type"].id,
            ordered_bags=bags_each,
            ordered_loose_kg=Decimal("0"),
            rate_per_kg=Decimal("110"),
            stock_source="owned",
        ),
    ]


class ValidateLinesV16016Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

    def tearDown(self):
        self.db.close()

    def test_sales_allows_duplicate_product_lines(self):
        bill = Bill(bill_type=BillType.sales, customer_id=self.m["customer"].id, location_id=self.m["location"].id)
        lines = _duplicate_lines(self.m)
        validate_lines(self.db, bill, lines)

    def test_purchase_rejects_duplicate_product_lines(self):
        from fastapi import HTTPException

        bill = Bill(bill_type=BillType.purchase, customer_id=self.m["customer"].id)
        lines = _duplicate_lines(self.m)
        with self.assertRaises(HTTPException) as ctx:
            validate_lines(self.db, bill, lines)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Duplicate line", str(ctx.exception.detail))


class BillRunningStockApiV16016Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        self.db = _make_session()
        self.m = _seed(self.db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _post_bill(self, body: dict) -> int:
        headers = {"Idempotency-Key": str(uuid4())}
        res = self.client.post("/api/bills", json=body, headers=headers)
        return res.status_code

    def test_sales_bill_create_with_duplicate_lines_succeeds(self):
        status = self._post_bill(
            {
                "bill_type": "sales",
                "customer_id": self.m["customer"].id,
                "location_id": self.m["location"].id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [
                    {
                        "product_id": self.m["product"].id,
                        "brand_id": self.m["brand"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "ordered_bags": 50,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "100",
                        "stock_source": "owned",
                    },
                    {
                        "product_id": self.m["product"].id,
                        "brand_id": self.m["brand"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "ordered_bags": 50,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "110",
                        "stock_source": "owned",
                    },
                ],
            }
        )
        self.assertEqual(status, 201)

    def test_purchase_bill_create_with_duplicate_lines_rejected(self):
        status = self._post_bill(
            {
                "bill_type": "purchase",
                "customer_id": self.m["customer"].id,
                "discount_percent": "0",
                "adjustment": "0",
                "lines": [
                    {
                        "product_id": self.m["product"].id,
                        "brand_id": self.m["brand"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "ordered_bags": 50,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "100",
                    },
                    {
                        "product_id": self.m["product"].id,
                        "brand_id": self.m["brand"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "ordered_bags": 50,
                        "ordered_loose_kg": "0",
                        "rate_per_kg": "110",
                    },
                ],
            }
        )
        self.assertEqual(status, 400)


class BillRunningStockServiceV16016Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

    def tearDown(self):
        self.db.close()

    def test_create_sales_bill_with_two_split_lines(self):
        out = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.sales,
                customer_id=self.m["customer"].id,
                location_id=self.m["location"].id,
                lines=_duplicate_lines(self.m),
            ),
            db=self.db,
            **idem_kwargs(),
        )
        bill = self.db.get(Bill, out.id)
        assert bill is not None
        self.assertEqual(len(bill.lines), 2)


if __name__ == "__main__":
    unittest.main()
