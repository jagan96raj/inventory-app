"""Fulfillment audit log API tests."""
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import BillType, Customer, FulfillmentType
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
from app.services.fulfillment import create_fulfillment
from app.services.operations import add_inventory
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_kwargs

from tests.test_job_work_v14 import _seed_masters


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class FulfillmentAuditTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["brand"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            10,
            Decimal("0"),
        )
        self.sales_bill = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.sales,
                customer_id=self.m["internal"].id,
                location_id=self.m["location"].id,
                lines=[
                    BillLineIn(
                        product_id=self.m["product"].id,
                        brand_id=self.m["brand"].id,
                        bag_type_id=self.m["bag_type"].id,
                        ordered_bags=2,
                        ordered_loose_kg=Decimal("0"),
                        rate_per_kg=Decimal("10"),
                    )
                ],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        create_fulfillment(
            self.db,
            bill_line_id=self.sales_bill.lines[0].id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("50"),
            bag_count=1,
            loose_kg=Decimal("0"),
            location_id=self.m["location"].id,
            expected_version=self.sales_bill.version,
        )

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_audit_lists_deliver_with_bill_context(self):
        res = self.client.get("/api/fulfillment/audit?limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreaterEqual(body["total"], 1)
        row = body["items"][0]
        self.assertEqual(row["entry_type"], "deliver")
        self.assertEqual(row["bill_type"], "sales")
        self.assertEqual(row["bill_number"], self.sales_bill.bill_number)
        self.assertEqual(row["product_name"], self.m["product"].product_name)
        self.assertEqual(row["bag_count"], 1)
        self.assertEqual(row["customer_name"], self.m["internal"].name)

    def test_audit_filters_by_entry_type(self):
        res = self.client.get("/api/fulfillment/audit?entry_type=return&limit=50")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
