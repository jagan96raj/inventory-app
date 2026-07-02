"""Spec v12.15 — idempotency keys on mutation POSTs."""
import unittest
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Bill,
    BillType,
    Brand,
    Customer,
    Location,
    Payment,
    PaymentMode,
    Product,
    User,
)
from app.services.idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    IDEMPOTENCY_KEY_REQUIRED_MSG,
    IDEMPOTENCY_KEY_REUSED_MSG,
    assert_idempotent_request,
    canonical_request_hash,
    hash_pydantic_body,
    store_idempotent_response,
)
from app.schemas import BillFinalizeCreate, BillLineIn, PaymentCreate
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_kwargs, new_test_idempotency_key


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
    customer = Customer(name="Idempotency Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _bill_payload(m: dict) -> dict:
    return {
        "bill_type": "purchase",
        "customer_id": m["customer"].id,
        "discount_percent": "0",
        "adjustment": "0",
        "lines": [
            {
                "product_id": m["product"].id,
                "brand_id": m["brand"].id,
                "bag_type_id": m["bag_type"].id,
                "ordered_bags": 10,
                "ordered_loose_kg": "0",
                "rate_per_kg": "100",
            }
        ],
    }


def _bill_create_schema(m: dict) -> BillFinalizeCreate:
    return BillFinalizeCreate(
        bill_type=BillType.purchase,
        customer_id=m["customer"].id,
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


class IdempotencyServiceV1215Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()

    def tearDown(self):
        self.db.close()

    def test_same_key_same_body_returns_cached(self):
        route = "POST /api/bills"
        body_hash = canonical_request_hash(b'{"a":1}')
        store_idempotent_response(
            self.db, 1, "key-1", route, body_hash, 201, {"id": 42, "bill_number": "P-1"}
        )
        cached = assert_idempotent_request(self.db, 1, "key-1", route, body_hash)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["status"], 201)
        self.assertEqual(cached["body"]["id"], 42)

    def test_same_key_different_body_raises_reused(self):
        route = "POST /api/bills"
        store_idempotent_response(
            self.db, 1, "key-2", route, canonical_request_hash(b'{"a":1}'), 201, {"id": 1}
        )
        with self.assertRaises(ValueError) as ctx:
            assert_idempotent_request(self.db, 1, "key-2", route, canonical_request_hash(b'{"a":2}'))
        self.assertEqual(str(ctx.exception), IDEMPOTENCY_KEY_REUSED_MSG)

    def test_different_keys_both_miss_cache(self):
        route = "POST /api/bills"
        h = canonical_request_hash(b'{}')
        self.assertIsNone(assert_idempotent_request(self.db, 1, "key-a", route, h))
        self.assertIsNone(assert_idempotent_request(self.db, 1, "key-b", route, h))


class IdempotencyApiV1215Tests(unittest.TestCase):
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

    def test_post_bill_without_idempotency_key_returns_400(self):
        res = self.client.post("/api/bills", json=_bill_payload(self.m))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], IDEMPOTENCY_KEY_REQUIRED_MSG)

    def test_duplicate_post_bills_same_key_creates_one_bill(self):
        key = str(uuid4())
        payload = _bill_payload(self.m)
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        res1 = self.client.post("/api/bills", json=payload, headers=headers)
        self.assertEqual(res1.status_code, 201)
        res2 = self.client.post("/api/bills", json=payload, headers=headers)
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(res1.json()["id"], res2.json()["id"])
        self.assertEqual(res1.json()["bill_number"], res2.json()["bill_number"])
        count = self.db.scalar(select(func.count()).select_from(Bill))
        self.assertEqual(count, 1)

    def test_duplicate_payment_replay_cached_no_overpayment(self):
        from app.routers.bills import create_finalized_bill

        created = create_finalized_bill(
            _bill_create_schema(self.m),
            db=self.db,
            **idem_kwargs("bill-for-pay"),
        )
        bill = self.db.get(Bill, created.id)
        assert bill is not None
        due = bill.grand_total

        pay_body = PaymentCreate(
            bill_id=bill.id,
            amount=due,
            payment_mode=PaymentMode.cash,
            expected_version=bill.version,
        )
        key = str(uuid4())
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        json_body = {
            "bill_id": bill.id,
            "amount": str(due),
            "payment_mode": "cash",
            "expected_version": bill.version,
        }
        res1 = self.client.post("/api/payments", json=json_body, headers=headers)
        self.assertEqual(res1.status_code, 201)
        res2 = self.client.post("/api/payments", json=json_body, headers=headers)
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(res1.json()["id"], res2.json()["id"])
        pay_count = self.db.scalar(select(func.count()).select_from(Payment))
        self.assertEqual(pay_count, 1)

    def test_payment_same_key_different_amount_returns_409(self):
        from app.routers.bills import create_finalized_bill

        created = create_finalized_bill(
            _bill_create_schema(self.m),
            db=self.db,
            **idem_kwargs("bill-for-pay-mismatch"),
        )
        bill = self.db.get(Bill, created.id)
        assert bill is not None

        key = str(uuid4())
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        res1 = self.client.post(
            "/api/payments",
            json={
                "bill_id": bill.id,
                "amount": "100",
                "payment_mode": "cash",
                "expected_version": bill.version,
            },
            headers=headers,
        )
        self.assertEqual(res1.status_code, 201)
        res2 = self.client.post(
            "/api/payments",
            json={
                "bill_id": bill.id,
                "amount": "200",
                "payment_mode": "cash",
                "expected_version": bill.version,
            },
            headers=headers,
        )
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.json()["detail"], IDEMPOTENCY_KEY_REUSED_MSG)


if __name__ == "__main__":
    unittest.main()
