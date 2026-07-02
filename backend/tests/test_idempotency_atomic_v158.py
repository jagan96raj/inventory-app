"""Spec v15.8 — atomic idempotency claim before mutation."""
import os
import tempfile
import threading
import unittest
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Bill,
    Brand,
    Customer,
    IdempotencyRecord,
    IdempotencyStatus,
    Location,
    Payment,
    Product,
    User,
)
from app.services.idempotency import (
    IDEMPOTENCY_IN_PROGRESS_MSG,
    IDEMPOTENCY_KEY_HEADER,
    IDEMPOTENCY_KEY_REUSED_MSG,
    claim_idempotency,
    complete_idempotency,
    fail_idempotency,
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
    customer = Customer(name="Atomic Idem Co")
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


class IdempotencyAtomicServiceV158Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()

    def tearDown(self):
        self.db.close()

    def test_sequential_same_key_returns_cached(self):
        route = "POST /api/bills"
        body_hash = hash_pydantic_body(
            BillFinalizeCreate.model_validate(_bill_payload(_seed(self.db)))
        )
        claim1 = claim_idempotency(self.db, 1, "seq-key", route, body_hash)
        self.assertIsNone(claim1.cached)
        self.assertIsNotNone(claim1.record_id)
        complete_idempotency(self.db, claim1.record_id, 201, {"id": 99})

        claim2 = claim_idempotency(self.db, 1, "seq-key", route, body_hash)
        self.assertIsNotNone(claim2.cached)
        self.assertEqual(claim2.cached["status"], 201)
        self.assertEqual(claim2.cached["body"]["id"], 99)

    def test_in_progress_blocks_second_claim(self):
        route = "POST /api/payments"
        body_hash = "abc123"
        claim = claim_idempotency(self.db, 1, "prog-key", route, body_hash)
        self.assertIsNotNone(claim.record_id)

        with self.assertRaises(ValueError) as ctx:
            claim_idempotency(self.db, 1, "prog-key", route, body_hash)
        self.assertEqual(str(ctx.exception), IDEMPOTENCY_IN_PROGRESS_MSG)

    def test_fail_idempotency_allows_retry(self):
        route = "POST /api/payments"
        body_hash = "retry-hash"
        claim = claim_idempotency(self.db, 1, "retry-key", route, body_hash)
        fail_idempotency(self.db, 1, "retry-key")

        claim2 = claim_idempotency(self.db, 1, "retry-key", route, body_hash)
        self.assertIsNotNone(claim2.record_id)

    def test_completed_different_hash_raises_reused(self):
        route = "POST /api/bills"
        store_idempotent_response(self.db, 1, "reuse-key", route, "hash-a", 201, {"id": 1})
        with self.assertRaises(ValueError) as ctx:
            claim_idempotency(self.db, 1, "reuse-key", route, "hash-b")
        self.assertEqual(str(ctx.exception), IDEMPOTENCY_KEY_REUSED_MSG)

    def test_concurrent_claim_only_one_in_progress(self):
        route = "POST /api/test"
        body_hash = "concurrent"
        key = "race-key"
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)
        try:
            engine = create_engine(
                f"sqlite:///{db_path.replace(chr(92), '/')}",
                connect_args={"check_same_thread": False},
                poolclass=NullPool,
            )
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine)
            setup = session_factory()
            try:
                ensure_test_user(setup)
                setup.commit()
            finally:
                setup.close()

            barrier = threading.Barrier(2)
            results: list[str] = []
            lock = threading.Lock()

            def worker():
                db = session_factory()
                try:
                    barrier.wait(timeout=5)
                    claim_idempotency(db, 1, key, route, body_hash)
                    with lock:
                        results.append("claimed")
                except ValueError as e:
                    with lock:
                        results.append(str(e))
                except Exception as e:
                    with lock:
                        results.append(f"error:{type(e).__name__}:{e}")
                finally:
                    db.close()

            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(len(results), 2)
            db = session_factory()
            try:
                record_count = db.scalar(
                    select(func.count()).select_from(IdempotencyRecord).where(
                        IdempotencyRecord.idempotency_key == key
                    )
                )
                self.assertEqual(record_count, 1)
            finally:
                db.close()
            engine.dispose()

            claimed = [r for r in results if r == "claimed"]
            blocked = [r for r in results if r == IDEMPOTENCY_IN_PROGRESS_MSG]
            self.assertEqual(len(claimed), 1)
            self.assertEqual(len(blocked) + len(claimed), 2)
        finally:
            try:
                os.remove(db_path)
            except OSError:
                pass


class IdempotencyAtomicApiV158Tests(unittest.TestCase):
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

    def test_duplicate_payment_same_key_one_record(self):
        from app.routers.bills import create_finalized_bill

        created = create_finalized_bill(
            BillFinalizeCreate(
                bill_type="purchase",
                customer_id=self.m["customer"].id,
                lines=[
                    BillLineIn(
                        product_id=self.m["product"].id,
                        brand_id=self.m["brand"].id,
                        bag_type_id=self.m["bag_type"].id,
                        ordered_bags=10,
                        ordered_loose_kg=Decimal("0"),
                        rate_per_kg=Decimal("100"),
                    )
                ],
            ),
            db=self.db,
            **idem_kwargs("atomic-bill"),
        )
        bill = self.db.get(Bill, created.id)
        assert bill is not None

        key = str(uuid4())
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        json_body = {
            "bill_id": bill.id,
            "amount": str(bill.grand_total),
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

        record = self.db.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.status, IdempotencyStatus.completed)


if __name__ == "__main__":
    unittest.main()
