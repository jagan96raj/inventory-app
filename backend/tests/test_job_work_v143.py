"""Spec v14.3 — JW activity log (return events) + quantity UX tests."""
import unittest
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    JobWorkLine,
    JobWorkReceipt,
    JobWorkReceiptEntryType,
    Location,
    Product,
    User,
)
from app.services.job_work import (
    JW_VOID_RETURN_MSG,
    create_job_work_order,
    receive_job_work,
    return_job_work_to_customer,
    void_job_work_receipt,
)
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_kwargs, idem_void_headers

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


class JobWorkV143Tests(unittest.TestCase):
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

    def _order_247(self):
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
                    "ordered_bags": 247,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )

    def test_receive_return_re_receive_custody_and_activity(self):
        order = self._order_247()
        line = order.lines[0]
        loc = self.m["location"].id

        receive_job_work(self.db, line_id=line.id, location_id=loc, bag_count=247, loose_kg=Decimal("0"))
        return_job_work_to_customer(
            self.db, line_id=line.id, location_id=loc, bag_count=237, loose_kg=Decimal("0")
        )
        receive_job_work(self.db, line_id=line.id, location_id=loc, bag_count=237, loose_kg=Decimal("0"))

        line = self.db.scalar(select(JobWorkLine).where(JobWorkLine.id == line.id))
        self.assertEqual(line.received_bags, 484)
        self.assertEqual(line.returned_bags, 237)
        self.assertEqual(line.custody_bags if hasattr(line, "custody_bags") else line.received_bags - line.returned_bags, 247)

        from app.services.job_work import _jw_line_progress

        progress = _jw_line_progress(line, self.m["bag_type"])
        self.assertEqual(progress["custody_bags"], 247)
        self.assertEqual(progress["remaining_receive_bags"], 0)

        events = self.db.scalars(
            select(JobWorkReceipt).where(JobWorkReceipt.line_id == line.id).order_by(JobWorkReceipt.id)
        ).all()
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].entry_type, JobWorkReceiptEntryType.receive)
        self.assertEqual(events[0].bag_count, 247)
        self.assertEqual(events[1].entry_type, JobWorkReceiptEntryType.return_)
        self.assertEqual(events[1].bag_count, 237)
        self.assertEqual(events[2].entry_type, JobWorkReceiptEntryType.receive)
        self.assertEqual(events[2].bag_count, 237)

    def test_void_blocked_on_return_entry(self):
        order = self._order_247()
        line = order.lines[0]
        loc = self.m["location"].id
        receive_job_work(self.db, line_id=line.id, location_id=loc, bag_count=100, loose_kg=Decimal("0"))
        ret = return_job_work_to_customer(
            self.db, line_id=line.id, location_id=loc, bag_count=40, loose_kg=Decimal("0")
        )
        with self.assertRaises(ValueError) as ctx:
            void_job_work_receipt(self.db, ret.id)
        self.assertIn("Return", str(ctx.exception))

    def test_api_void_return_receipt_400(self):
        order = self._order_247()
        line = order.lines[0]
        loc = self.m["location"].id
        receive_job_work(self.db, line_id=line.id, location_id=loc, bag_count=50, loose_kg=Decimal("0"))
        ret = return_job_work_to_customer(
            self.db, line_id=line.id, location_id=loc, bag_count=10, loose_kg=Decimal("0")
        )
        res = self.client.post(
            f"/api/job-work/receipts/{ret.id}/void",
            headers={**idem_void_headers(), IDEMPOTENCY_KEY_HEADER: "void-return-test"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Return", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
