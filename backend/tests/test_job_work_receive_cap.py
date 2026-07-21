"""Receive cannot exceed remaining ordered bags / loose kg."""
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
    JW_RECEIVE_EXCEEDS_MSG,
    create_job_work_order,
    list_job_work_orders,
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
    loose_type = BagType(name="Loose", weight_per_bag_kg=Decimal("0"), is_loose=True)
    customer = Customer(name="JW Customer", party_type=CustomerPartyType.internal)
    db.add_all([product, brand, location, bag_type, loose_type, customer])
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "loose_type": loose_type,
        "customer": customer,
    }


class JobWorkReceiveCapTests(unittest.TestCase):
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

    def test_cannot_receive_more_bags_than_ordered(self):
        order = create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 10,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        line = order.lines[0]
        loc = self.m["location"].id
        with self.assertRaises(ValueError) as ctx:
            receive_job_work(
                self.db, line_id=line.id, location_id=loc, bag_count=11, loose_kg=Decimal("0")
            )
        self.assertIn(JW_RECEIVE_EXCEEDS_MSG, str(ctx.exception))

    def test_cannot_receive_more_loose_than_ordered(self):
        order = create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["loose_type"].id,
                    "ordered_bags": 0,
                    "ordered_loose_kg": Decimal("100"),
                }
            ],
        )
        line = order.lines[0]
        loc = self.m["location"].id
        with self.assertRaises(ValueError) as ctx:
            receive_job_work(
                self.db, line_id=line.id, location_id=loc, bag_count=0, loose_kg=Decimal("100.001")
            )
        self.assertIn(JW_RECEIVE_EXCEEDS_MSG, str(ctx.exception))

    def test_partial_then_over_receive_blocked(self):
        order = create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 10,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        line = order.lines[0]
        loc = self.m["location"].id
        receive_job_work(
            self.db, line_id=line.id, location_id=loc, bag_count=7, loose_kg=Decimal("0")
        )
        with self.assertRaises(ValueError) as ctx:
            receive_job_work(
                self.db, line_id=line.id, location_id=loc, bag_count=4, loose_kg=Decimal("0")
            )
        self.assertIn(JW_RECEIVE_EXCEEDS_MSG, str(ctx.exception))
        receive_job_work(
            self.db, line_id=line.id, location_id=loc, bag_count=3, loose_kg=Decimal("0")
        )

    def test_return_reopens_receive_up_to_returned(self):
        order = create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 10,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        line = order.lines[0]
        loc = self.m["location"].id
        receive_job_work(
            self.db, line_id=line.id, location_id=loc, bag_count=10, loose_kg=Decimal("0")
        )
        return_job_work_to_customer(
            self.db, line_id=line.id, location_id=loc, bag_count=4, loose_kg=Decimal("0")
        )
        with self.assertRaises(ValueError):
            receive_job_work(
                self.db, line_id=line.id, location_id=loc, bag_count=5, loose_kg=Decimal("0")
            )
        receive_job_work(
            self.db, line_id=line.id, location_id=loc, bag_count=4, loose_kg=Decimal("0")
        )

    def test_list_hides_voided_by_default(self):
        open_order = create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 5,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        voided = create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 2,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        void_job_work_order(self.db, voided.id)

        rows, total = list_job_work_orders(self.db)
        ids = {o.id for o in rows}
        self.assertIn(open_order.id, ids)
        self.assertNotIn(voided.id, ids)
        self.assertEqual(total, 1)

        voided_rows, voided_total = list_job_work_orders(
            self.db, status=JobWorkOrderStatus.cancelled
        )
        self.assertEqual(voided_total, 1)
        self.assertEqual(voided_rows[0].id, voided.id)


if __name__ == "__main__":
    unittest.main()
