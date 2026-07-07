"""Spec v16.0.17 — unified JW fulfillment list (tab=all) and received wording."""
import unittest
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Brand,
    Customer,
    CustomerPartyType,
    Location,
    Product,
)
from app.services.job_work import (
    JW_VOID_CUSTODY_MSG,
    create_job_work_order,
    receive_job_work,
    return_job_work_to_customer,
    void_job_work_order,
)
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
    product = Product(product_name="Bajra")
    brand = Brand(name="Unclean")
    location = Location(name="Mill")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="JW Customer", party_type=CustomerPartyType.internal)
    db.add_all([product, brand, location, bag_type, customer])
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


class JobWorkFulfillmentV16017Tests(unittest.TestCase):
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

    def _create_order(self, *, ordered_bags: int = 100):
        return create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": ordered_bags,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )

    def test_tab_all_lists_line_with_remaining(self):
        order = self._create_order()
        res = self.client.get("/api/job-work/fulfillment/orders?tab=all&visibility=actionable")
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["order_id"], order.id)
        self.assertEqual(len(items[0]["lines"]), 1)
        line = items[0]["lines"][0]
        self.assertGreater(Decimal(line["remaining_receive_kg"]), 0)

    def test_tab_all_lists_line_after_full_receive_when_net_received_positive(self):
        order = self._create_order(ordered_bags=50)
        line = order.lines[0]
        loc = self.m["location"].id
        receive_job_work(self.db, line_id=line.id, location_id=loc, bag_count=50, loose_kg=Decimal("0"))

        res = self.client.get("/api/job-work/fulfillment/orders?tab=all&visibility=actionable")
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(len(items[0]["lines"]), 1)
        row = items[0]["lines"][0]
        self.assertEqual(Decimal(row["remaining_receive_kg"]), Decimal("0"))
        self.assertGreater(Decimal(row["net_received_kg"]), 0)

    def test_tab_receive_and_return_still_work(self):
        order = self._create_order(ordered_bags=80)
        line = order.lines[0]
        loc = self.m["location"].id
        receive_job_work(self.db, line_id=line.id, location_id=loc, bag_count=30, loose_kg=Decimal("0"))

        receive_res = self.client.get("/api/job-work/fulfillment/orders?tab=receive")
        self.assertEqual(receive_res.status_code, 200)
        self.assertEqual(len(receive_res.json()["items"]), 1)

        return_res = self.client.get("/api/job-work/fulfillment/orders?tab=return")
        self.assertEqual(return_res.status_code, 200)
        self.assertEqual(len(return_res.json()["items"]), 1)

    def test_void_blocked_when_net_received_and_message_has_no_custody(self):
        order = self._create_order()
        line = order.lines[0]
        receive_job_work(
            self.db,
            line_id=line.id,
            location_id=self.m["location"].id,
            bag_count=10,
            loose_kg=Decimal("0"),
        )
        with self.assertRaises(ValueError) as ctx:
            void_job_work_order(self.db, order.id)
        msg = str(ctx.exception)
        self.assertIn(JW_VOID_CUSTODY_MSG, msg)
        self.assertNotIn("custody", msg.lower())


if __name__ == "__main__":
    unittest.main()
