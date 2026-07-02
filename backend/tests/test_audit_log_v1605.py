"""Spec v16.0.5 — central audit log."""
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    AuditEvent,
    BagType,
    Bill,
    BillType,
    Brand,
    Customer,
    Location,
    Product,
    User,
    UserRole,
    PaymentMode,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
from app.services.audit_log import AuditAction, AuditEntityType
from app.services.bills import void_bill
from app.services.payments import create_payment, void_payment
from tests.idempotency_helpers import configure_test_void_auth, idem_kwargs


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


OWNER = User(id=1, email="owner@test.com", name="Owner", role=UserRole.owner)
WRITER = User(id=2, email="writer@test.com", name="Writer", role=UserRole.writer)


def _seed(db: Session) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="Audit Customer")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _create_bill(db: Session, m: dict, user: User, bill_type: BillType = BillType.purchase) -> Bill:
    body = BillFinalizeCreate(
        bill_type=bill_type,
        customer_id=m["customer"].id,
        location_id=m["location"].id if bill_type == BillType.sales else None,
        discount_percent=Decimal("0"),
        adjustment=Decimal("0"),
        lines=[
            BillLineIn(
                product_id=m["product"].id,
                brand_id=m["brand"].id,
                bag_type_id=m["bag_type"].id,
                ordered_bags=10,
                ordered_loose_kg=Decimal("0"),
                rate_per_kg=Decimal("100"),
            )
        ],
    )
    out = create_finalized_bill(body, db=db, user=user, idempotency_key=idem_kwargs()["idempotency_key"])
    bill = db.get(Bill, out.id)
    assert bill is not None
    return bill


class TestAuditLogV1605(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_test_void_auth()

    def setUp(self):
        self.db = _make_session()
        self.db.add_all(
            [
                User(
                    id=OWNER.id,
                    email=OWNER.email,
                    name=OWNER.name,
                    password_hash="x",
                    role=OWNER.role,
                ),
                User(
                    id=WRITER.id,
                    email=WRITER.email,
                    name=WRITER.name,
                    password_hash="x",
                    role=WRITER.role,
                ),
            ]
        )
        self.db.commit()
        self.m = _seed(self.db)
        self.bill = _create_bill(self.db, self.m, OWNER)

        def override_db():
            yield self.db

        self._current = OWNER
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self._current
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _as(self, user: User):
        self._current = user

    def test_void_payment_creates_audit_row(self):
        pay = create_payment(
            self.db,
            self.bill.id,
            Decimal("100"),
            PaymentMode.cash,
            expected_version=self.bill.version,
        )
        void_payment(self.db, pay.id, expected_version=self.bill.version, actor=OWNER)
        row = self.db.scalar(
            select(AuditEvent).where(AuditEvent.action == AuditAction.PAYMENT_VOIDED)
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.user_email, OWNER.email)
        self.assertEqual(row.entity_type, AuditEntityType.PAYMENT)
        self.assertEqual(row.entity_id, pay.id)

    def test_void_bill_creates_audit_row(self):
        bill = _create_bill(self.db, self.m, OWNER)
        void_bill(self.db, bill.id, expected_version=bill.version, actor=OWNER)
        row = self.db.scalar(select(AuditEvent).where(AuditEvent.action == AuditAction.BILL_VOIDED))
        self.assertIsNotNone(row)
        self.assertEqual(row.entity_label, bill.bill_number)

    def test_list_audit_events_owner_ok(self):
        bill = _create_bill(self.db, self.m, OWNER)
        void_bill(self.db, bill.id, expected_version=bill.version, actor=OWNER)
        self._as(OWNER)
        res = self.client.get("/api/audit/events?limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertTrue(any(i["action"] == AuditAction.BILL_VOIDED for i in body["items"]))

    def test_list_audit_events_writer_forbidden(self):
        self._as(WRITER)
        res = self.client.get("/api/audit/events")
        self.assertEqual(res.status_code, 403)

    def test_filters_by_action_and_date(self):
        old = AuditEvent(
            user_id=OWNER.id,
            user_email=OWNER.email,
            action=AuditAction.PAYMENT_VOIDED,
            entity_type=AuditEntityType.PAYMENT,
            entity_id=99,
            entity_label="old",
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        new = AuditEvent(
            user_id=OWNER.id,
            user_email=OWNER.email,
            action=AuditAction.BILL_VOIDED,
            entity_type=AuditEntityType.BILL,
            entity_id=self.bill.id,
            entity_label=self.bill.bill_number,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add_all([old, new])
        self.db.commit()
        self._as(OWNER)

        res = self.client.get(f"/api/audit/events?action={AuditAction.BILL_VOIDED}")
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertTrue(all(i["action"] == AuditAction.BILL_VOIDED for i in items))

        today = date.today().isoformat()
        res2 = self.client.get(f"/api/audit/events?date_from={today}&date_to={today}")
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(any(i["action"] == AuditAction.BILL_VOIDED for i in res2.json()["items"]))
        self.assertFalse(any(i["action"] == AuditAction.PAYMENT_VOIDED for i in res2.json()["items"]))


if __name__ == "__main__":
    unittest.main()
