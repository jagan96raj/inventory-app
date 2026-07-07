"""Spec v12.18 — app-wide list pagination."""
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

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
    BillLine,
    BillType,
    Brand,
    Customer,
    DeliveryStatus,
    Location,
    PaymentStatus,
    Product,
    PaymentMode,
)
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


def _seed(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer_a = Customer(name="Alpha Traders")
    customer_b = Customer(name="Beta Mills")
    db.add_all([product, brand, location, bag_type, customer_a, customer_b])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer_a": customer_a,
        "customer_b": customer_b,
    }


def _line(m: dict) -> BillLineIn:
    return BillLineIn(
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
        ordered_bags=10,
        ordered_loose_kg=Decimal("0"),
        rate_per_kg=Decimal("100"),
    )


def _create_bill(db: Session, m: dict, *, customer: Customer, bill_type: BillType, suffix: str) -> Bill:
    out = create_finalized_bill(
        BillFinalizeCreate(
            bill_type=bill_type,
            customer_id=customer.id,
            location_id=m["location"].id if bill_type == BillType.sales else None,
            discount_percent=Decimal("0"),
            adjustment=Decimal("0"),
            lines=[_line(m)],
        ),
        db=db,
        **idem_kwargs(),
    )
    bill = db.get(Bill, out.id)
    assert bill is not None
    bill.bill_number = f"{bill.bill_number}-{suffix}"
    db.commit()
    return bill


class PaginationV1218Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        self.bills: list[Bill] = []
        for i in range(5):
            customer = self.m["customer_a"] if i % 2 == 0 else self.m["customer_b"]
            btype = BillType.sales if i < 3 else BillType.purchase
            self.bills.append(_create_bill(self.db, self.m, customer=customer, bill_type=btype, suffix=str(i)))
        self.bills[0].payment_status = PaymentStatus.unpaid
        self.bills[0].order_delivery_status = DeliveryStatus.not_delivered
        self.bills[1].payment_status = PaymentStatus.partial
        self.bills[1].amount_paid = Decimal("500")
        self.bills[2].payment_status = PaymentStatus.paid
        self.bills[2].amount_paid = self.bills[2].grand_total
        self.bills[2].order_delivery_status = DeliveryStatus.delivered
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_bills_limit_offset_and_total(self):
        r1 = self.client.get("/api/bills?bill_type=sales&limit=2&offset=0")
        self.assertEqual(r1.status_code, 200)
        p1 = r1.json()
        self.assertEqual(len(p1["items"]), 2)
        self.assertEqual(p1["total"], 3)
        self.assertEqual(p1["limit"], 2)
        self.assertEqual(p1["offset"], 0)

        r2 = self.client.get("/api/bills?bill_type=sales&limit=2&offset=2")
        p2 = r2.json()
        self.assertEqual(len(p2["items"]), 1)
        self.assertEqual(p2["total"], 3)
        ids_page1 = {i["id"] for i in p1["items"]}
        ids_page2 = {i["id"] for i in p2["items"]}
        self.assertTrue(ids_page1.isdisjoint(ids_page2))

    def test_bills_list_items_slim_no_lines_no_opposite_due(self):
        res = self.client.get("/api/bills?limit=50")
        self.assertEqual(res.status_code, 200)
        for item in res.json()["items"]:
            self.assertNotIn("lines", item)
            self.assertNotIn("opposite_due_total", item)
            self.assertIn("bill_number", item)
            self.assertIn("amount_due", item)

    def test_bill_detail_still_has_opposite_due(self):
        bill_id = self.bills[0].id
        res = self.client.get(f"/api/bills/{bill_id}")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("opposite_due_total", body)
        self.assertGreater(len(body["lines"]), 0)

    @patch("app.routers.bills.opposite_bills_due_total")
    def test_bills_list_does_not_call_opposite_due(self, mock_opposite):
        res = self.client.get("/api/bills?limit=50")
        self.assertEqual(res.status_code, 200)
        mock_opposite.assert_not_called()

    def test_bills_summary_matches_filtered_set(self):
        res = self.client.get("/api/bills?bill_type=sales&payment_status=unpaid")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        summary = body["summary"]
        self.assertEqual(summary["total_count"], body["total"])
        self.assertGreaterEqual(summary["unpaid_count"], 1)
        self.assertGreaterEqual(float(summary["total_due"]), 0)

    def test_bills_search_and_payment_filter(self):
        res = self.client.get("/api/bills?search=alpha&payment_status=unpaid&limit=50")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        for item in body["items"]:
            self.assertIn("alpha", item["customer_name"].lower())

    def test_bills_date_filter(self):
        self.bills[0].bill_date = date(2026, 1, 15)
        self.bills[1].bill_date = date(2026, 2, 10)
        self.bills[2].bill_date = date(2026, 3, 20)
        self.db.commit()

        res = self.client.get("/api/bills?bill_type=sales&date_from=2026-02-01&date_to=2026-02-28")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["id"], self.bills[1].id)
        self.assertEqual(body["summary"]["total_count"], 1)

        bad = self.client.get("/api/bills?date_from=2026-03-01&date_to=2026-02-01")
        self.assertEqual(bad.status_code, 400)

    def test_payments_paginated(self):
        bill = self.bills[0]
        from app.services.payments import create_payment

        create_payment(self.db, bill.id, Decimal("100"), PaymentMode.cash, expected_version=1)
        res = self.client.get("/api/payments?limit=10&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("items", body)
        self.assertGreaterEqual(body["total"], 1)

    def test_inventory_paginated(self):
        from app.models.entities import Inventory

        inv = Inventory(
            product_id=self.m["product"].id,
            brand_id=self.m["brand"].id,
            location_id=self.m["location"].id,
            bag_type_id=self.m["bag_type"].id,
            bag_count=5,
            loose_kg=Decimal("0"),
            total_quantity_kg=Decimal("250"),
        )
        self.db.add(inv)
        self.db.commit()
        res = self.client.get("/api/inventory?limit=10&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["total"], 1)

    def test_customers_paginated(self):
        res = self.client.get("/api/customers?limit=1&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["total"], 2)

    def test_bag_change_paginated(self):
        res = self.client.get("/api/operations/bag-change?limit=10&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("items", body)
        self.assertIn("total", body)
        self.assertIsInstance(body["items"], list)

    def test_fulfillment_entries_paginated(self):
        line = self.db.query(BillLine).filter(BillLine.bill_id == self.bills[0].id).first()
        assert line is not None
        res = self.client.get(f"/api/fulfillment/entries?bill_line_id={line.id}&limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("items", body)
        self.assertIn("total", body)


if __name__ == "__main__":
    unittest.main()
