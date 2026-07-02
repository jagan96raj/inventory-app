"""Job work order void — cancel open orders with guards."""
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
    JobWorkOrderStatus,
    Location,
    Product,
)
from app.services.job_work import (
    JW_ORDER_ALREADY_CANCELLED_MSG,
    JW_VOID_CUSTODY_MSG,
    create_job_work_order,
    receive_job_work,
    return_job_work_to_customer,
    void_job_work_order,
)
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_void_headers

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


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


class JobWorkVoidOrderTests(unittest.TestCase):
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

    def _create_order(self):
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
                    "ordered_bags": 100,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )

    def test_void_open_order_no_activity(self):
        order = self._create_order()
        voided = void_job_work_order(self.db, order.id)
        self.assertEqual(voided.status, JobWorkOrderStatus.cancelled)

    def test_void_blocked_with_custody(self):
        order = self._create_order()
        line = order.lines[0]
        receive_job_work(
            self.db,
            line_id=line.id,
            location_id=self.m["location"].id,
            bag_count=50,
            loose_kg=Decimal("0"),
        )
        with self.assertRaises(ValueError) as ctx:
            void_job_work_order(self.db, order.id)
        self.assertIn(JW_VOID_CUSTODY_MSG, str(ctx.exception))

    def test_void_after_all_material_returned(self):
        order = self._create_order()
        line = order.lines[0]
        loc = self.m["location"].id
        receive_job_work(self.db, line_id=line.id, location_id=loc, bag_count=50, loose_kg=Decimal("0"))
        return_job_work_to_customer(
            self.db, line_id=line.id, location_id=loc, bag_count=50, loose_kg=Decimal("0")
        )
        voided = void_job_work_order(self.db, order.id)
        self.assertEqual(voided.status, JobWorkOrderStatus.cancelled)

    def test_void_already_cancelled(self):
        order = self._create_order()
        void_job_work_order(self.db, order.id)
        with self.assertRaises(ValueError) as ctx:
            void_job_work_order(self.db, order.id)
        self.assertIn(JW_ORDER_ALREADY_CANCELLED_MSG, str(ctx.exception))

    def test_api_void_order(self):
        order = self._create_order()
        res = self.client.post(
            f"/api/job-work/{order.id}/void",
            headers={**idem_void_headers(), IDEMPOTENCY_KEY_HEADER: "void-order-test"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
