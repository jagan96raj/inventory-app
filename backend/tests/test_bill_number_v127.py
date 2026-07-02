"""Spec v12.7 — safe bill number generation (counter + row lock)."""
import os
import threading
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    BagType,
    Bill,
    BillNumberCounter,
    BillType,
    Brand,
    Customer,
    Location,
    Product,
)
from app.routers.bills import preview_next_bill_number
from app.schemas import BillFinalizeCreate, BillLineIn
from app.services.bills import next_bill_number, preview_bill_number


def _make_session(bind=None) -> Session:
    if bind is None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        bind = engine
    return sessionmaker(bind=bind)()


def _seed_masters(db: Session) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Brand A")
    customer = Customer(name="Bill Num Co")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    db.add_all([product, brand, customer, location, bag_type])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "customer": customer,
        "location": location,
        "bag_type": bag_type,
    }


def _line(m: dict) -> BillLineIn:
    return BillLineIn(
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
        ordered_bags=1,
        ordered_loose_kg=Decimal("0"),
        rate_per_kg=Decimal("100"),
    )


def _create_body(m: dict, bill_type: BillType) -> BillFinalizeCreate:
    return BillFinalizeCreate(
        bill_type=bill_type,
        bill_date=date(2026, 6, 1),
        customer_id=m["customer"].id,
        location_id=m["location"].id if bill_type == BillType.sales else None,
        lines=[_line(m)],
    )


class BillNumberV127Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def test_a_sequential_creates_monotonic_numbers(self):
        n1 = next_bill_number(self.db, BillType.sales)
        self.db.commit()
        n2 = next_bill_number(self.db, BillType.sales)
        self.db.commit()
        n3 = next_bill_number(self.db, BillType.purchase)
        self.db.commit()
        self.assertEqual(n1, "S-000001")
        self.assertEqual(n2, "S-000002")
        self.assertEqual(n3, "P-000001")

    def test_b_counters_independent_per_type(self):
        next_bill_number(self.db, BillType.sales)
        self.db.commit()
        next_bill_number(self.db, BillType.purchase)
        self.db.commit()
        next_bill_number(self.db, BillType.purchase)
        self.db.commit()
        sales_n = next_bill_number(self.db, BillType.sales)
        self.db.commit()
        self.assertEqual(sales_n, "S-000002")
        purchase_n = next_bill_number(self.db, BillType.purchase)
        self.db.commit()
        self.assertEqual(purchase_n, "P-000003")

    def test_d_preview_does_not_consume_counter(self):
        preview1 = preview_bill_number(self.db, BillType.sales)
        self.assertEqual(preview1, "S-000001")
        preview2 = preview_bill_number(self.db, BillType.sales)
        self.assertEqual(preview2, "S-000001")

        allocated = next_bill_number(self.db, BillType.sales)
        self.db.commit()
        self.assertEqual(allocated, "S-000001")

        preview3 = preview_bill_number(self.db, BillType.sales)
        self.assertEqual(preview3, "S-000002")

        endpoint_preview = preview_next_bill_number(BillType.sales, self.db)
        self.assertEqual(endpoint_preview["bill_number"], "S-000002")

    def test_counter_row_lock_emits_for_update(self):
        stmt = (
            select(BillNumberCounter)
            .where(BillNumberCounter.bill_type == BillType.sales)
            .with_for_update()
        )
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("FOR UPDATE", compiled.upper())

    @unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL for PostgreSQL concurrent test")
    def test_c_concurrent_create_both_succeed_different_numbers(self):
        url = os.environ["TEST_DATABASE_URL"]
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        m = _seed_masters(_make_session(engine))
        body = _create_body(m, BillType.sales)

        results: list[str] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker():
            session = _make_session(engine)
            try:
                from app.routers.bills import create_finalized_bill

                from tests.idempotency_helpers import idem_kwargs, new_test_idempotency_key

                out = create_finalized_bill(body, session, **idem_kwargs(new_test_idempotency_key()))
                with lock:
                    results.append(out.bill_number)
            except Exception as e:
                with lock:
                    errors.append(e)
            finally:
                session.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], errors)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(set(results)), 2)
        self.assertTrue(all(n.startswith("S-") for n in results))


if __name__ == "__main__":
    unittest.main()
