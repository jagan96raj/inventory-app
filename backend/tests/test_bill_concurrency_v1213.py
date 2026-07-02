"""Spec v12.13 — bill row lock + optimistic version (stale-write guard)."""
import threading
import unittest
from unittest import skip
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    FulfillmentType,
    Location,
    PaymentMode,
    Product,
    User,
)
from app.routers.bills import create_finalized_bill, edit_finalized_bill
from app.schemas import BillEditFinalized, BillEditLineIn, BillFinalizeCreate, BillLineIn, PaymentCreate
from app.services.bill_concurrency import EXPECTED_BILL_VERSION_HEADER, STALE_BILL_MSG
from app.services.bill_lock import BILL_IN_USE_MSG, lock_bill_for_update
from app.services.fulfillment import create_fulfillment
from app.services.idempotency import IDEMPOTENCY_KEY_HEADER
from app.services.payments import create_payment
from tests.idempotency_helpers import TEST_USER, idem_kwargs, new_test_idempotency_key


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db: Session) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="Concurrency Co")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
    }


def _line(m: dict, *, bags: int = 2) -> BillLineIn:
    return BillLineIn(
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
        ordered_bags=bags,
        ordered_loose_kg=Decimal("0"),
        rate_per_kg=Decimal("100"),
    )


def _create_bill(db: Session, m: dict) -> Bill:
    created = create_finalized_bill(
        BillFinalizeCreate(
            bill_type=BillType.purchase,
            bill_date=date(2026, 6, 1),
            customer_id=m["customer"].id,
            lines=[_line(m)],
        ),
        db=db,
        **idem_kwargs(),
    )
    bill = db.get(Bill, created.id)
    assert bill is not None
    return bill


def _bill_line(db: Session, bill_id: int) -> BillLine:
    line = db.scalar(select(BillLine).where(BillLine.bill_id == bill_id))
    assert line is not None
    return line


class BillConcurrencyV1213Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        self.bill = _create_bill(self.db, self.m)

    def tearDown(self):
        self.db.close()

    def test_lock_conflict_maps_to_409(self):
        with patch("app.routers.bills.lock_bill_for_update", side_effect=ValueError(BILL_IN_USE_MSG)):
            with self.assertRaises(HTTPException) as ctx:
                edit_finalized_bill(
                    self.bill.id,
                    BillEditFinalized(expected_version=1),
                    db=self.db,
                    **idem_kwargs(),
                )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, BILL_IN_USE_MSG)

    def test_stale_edit_after_prior_save(self):
        line = _bill_line(self.db, self.bill.id)
        edit_finalized_bill(
            self.bill.id,
            BillEditFinalized(
                expected_version=1,
                lines=[BillEditLineIn(id=line.id, rate_per_kg=Decimal("110"))],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        self.db.refresh(self.bill)
        self.assertEqual(self.bill.version, 2)

        with self.assertRaises(HTTPException) as ctx:
            edit_finalized_bill(
                self.bill.id,
                BillEditFinalized(
                    expected_version=1,
                    lines=[BillEditLineIn(id=line.id, rate_per_kg=Decimal("120"))],
                ),
                db=self.db,
                **idem_kwargs(),
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, STALE_BILL_MSG)

        self.db.refresh(line)
        self.assertEqual(line.rate_per_kg, Decimal("110"))

    def test_stale_payment_rejected(self):
        create_payment(
            self.db,
            self.bill.id,
            Decimal("100"),
            PaymentMode.cash,
            expected_version=1,
        )
        self.db.refresh(self.bill)
        self.assertEqual(self.bill.version, 2)

        with self.assertRaises(ValueError) as ctx:
            create_payment(
                self.db,
                self.bill.id,
                Decimal("50"),
                PaymentMode.cash,
                expected_version=1,
            )
        self.assertEqual(str(ctx.exception), STALE_BILL_MSG)

    def test_stale_fulfillment_rejected(self):
        line = _bill_line(self.db, self.bill.id)
        create_fulfillment(
            self.db,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("100"),
            bag_count=2,
            loose_kg=Decimal("0"),
            location_id=self.m["location"].id,
            expected_version=1,
        )
        self.db.refresh(self.bill)
        self.assertEqual(self.bill.version, 2)

        with self.assertRaises(ValueError) as ctx:
            create_fulfillment(
                self.db,
                bill_line_id=line.id,
                entry_type=FulfillmentType.deliver,
                quantity_kg=Decimal("50"),
                bag_count=1,
                loose_kg=Decimal("0"),
                location_id=self.m["location"].id,
                expected_version=1,
            )
        self.assertEqual(str(ctx.exception), STALE_BILL_MSG)

    def test_successive_writes_increment_version(self):
        line = _bill_line(self.db, self.bill.id)
        edit_finalized_bill(
            self.bill.id,
            BillEditFinalized(
                expected_version=1,
                lines=[BillEditLineIn(id=line.id, rate_per_kg=Decimal("105"))],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        self.db.refresh(self.bill)
        self.assertEqual(self.bill.version, 2)

        create_payment(
            self.db,
            self.bill.id,
            Decimal("100"),
            PaymentMode.cash,
            expected_version=2,
        )
        self.db.refresh(self.bill)
        self.assertEqual(self.bill.version, 3)

    def test_different_bills_unaffected(self):
        bill_b = _create_bill(self.db, self.m)
        line_a = _bill_line(self.db, self.bill.id)
        line_b = _bill_line(self.db, bill_b.id)

        edit_finalized_bill(
            self.bill.id,
            BillEditFinalized(
                expected_version=1,
                lines=[BillEditLineIn(id=line_a.id, rate_per_kg=Decimal("110"))],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        edit_finalized_bill(
            bill_b.id,
            BillEditFinalized(
                expected_version=1,
                lines=[BillEditLineIn(id=line_b.id, rate_per_kg=Decimal("120"))],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        self.db.refresh(self.bill)
        self.db.refresh(bill_b)
        self.assertEqual(self.bill.version, 2)
        self.assertEqual(bill_b.version, 2)

    def test_api_stale_edit_returns_409(self):
        client = TestClient(app)
        app.dependency_overrides.clear()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

        line = _bill_line(self.db, self.bill.id)
        first = client.patch(
            f"/api/bills/{self.bill.id}",
            json={
                "expected_version": 1,
                "lines": [{"id": line.id, "rate_per_kg": "110"}],
            },
            headers={IDEMPOTENCY_KEY_HEADER: new_test_idempotency_key()},
        )
        self.assertEqual(first.status_code, 200)

        stale = client.patch(
            f"/api/bills/{self.bill.id}",
            json={
                "expected_version": 1,
                "lines": [{"id": line.id, "rate_per_kg": "120"}],
            },
            headers={IDEMPOTENCY_KEY_HEADER: new_test_idempotency_key()},
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"], STALE_BILL_MSG)
        app.dependency_overrides.clear()


class BillConcurrencyLockOverlapTests(unittest.TestCase):
    @skip("SQLite does not enforce FOR UPDATE NOWAIT overlap reliably")
    def test_concurrent_lock_one_succeeds_one_conflicts(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        setup = sessionmaker(bind=engine)()
        m = _seed(setup)
        bill = _create_bill(setup, m)
        bill_id = bill.id
        setup.close()

        results: list[str] = []
        barrier = threading.Barrier(2)

        def worker():
            session = sessionmaker(bind=engine)()
            try:
                barrier.wait(timeout=5)
                lock_bill_for_update(session, bill_id)
                session.commit()
                results.append("ok")
            except ValueError as exc:
                session.rollback()
                if str(exc) == BILL_IN_USE_MSG:
                    results.append("locked")
                else:
                    results.append("error")
            finally:
                session.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("locked"), 1)


if __name__ == "__main__":
    unittest.main()
