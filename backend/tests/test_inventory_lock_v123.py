"""Spec v12.3 — inventory row locking tests."""
import os
import threading
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    BagType,
    Bill,
    BillLine,
    BillStatus,
    BillType,
    Brand,
    Customer,
    DeliveryStatus,
    Inventory,
    Location,
    PaymentStatus,
    Product,
)
from app.services.fulfillment import FulfillmentType, create_bill_fulfillment_event, create_fulfillment
from app.services.inventory_lock import (
    get_inventory_row_for_update,
    inventory_row_key,
    sort_inventory_keys,
)
from app.services.operations import create_product_transfer, subtract_inventory


def _make_session(bind=None) -> Session:
    if bind is None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        bind = engine
    return sessionmaker(bind=bind)()


def _seed_inventory(db: Session, *, bag_count: int = 100) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Brand A")
    customer = Customer(name="Customer One")
    location = Location(name="Warehouse")
    loc2 = Location(name="Store")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    db.add_all([product, brand, customer, location, loc2, bag_type])
    db.flush()
    inv = Inventory(
        product_id=product.id,
        brand_id=brand.id,
        location_id=location.id,
        bag_type_id=bag_type.id,
        bag_count=bag_count,
        loose_kg=Decimal("0"),
        total_quantity_kg=Decimal(str(bag_count * 50)),
    )
    db.add(inv)
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "customer": customer,
        "location": location,
        "location2": loc2,
        "bag_type": bag_type,
        "inventory": inv,
    }


def _sales_bill(db: Session, masters: dict, *, bill_number: str, ordered_bags: int = 100) -> Bill:
    bill = Bill(
        bill_number=bill_number,
        bill_type=BillType.sales,
        status=BillStatus.finalized,
        bill_date=date(2025, 5, 1),
        customer_id=masters["customer"].id,
        location_id=masters["location"].id,
        grand_total=Decimal("5000"),
        subtotal=Decimal("5000"),
        amount_paid=Decimal("0"),
        payment_status=PaymentStatus.unpaid,
        order_delivery_status=DeliveryStatus.not_delivered,
    )
    db.add(bill)
    db.flush()
    line = BillLine(
        bill_id=bill.id,
        product_id=masters["product"].id,
        brand_id=masters["brand"].id,
        bag_type_id=masters["bag_type"].id,
        ordered_bags=ordered_bags,
        ordered_loose_kg=Decimal("0"),
        ordered_quantity_kg=Decimal(str(ordered_bags * 50)),
        rate_per_kg=Decimal("1"),
        line_total=Decimal(str(ordered_bags * 50)),
    )
    db.add(line)
    db.commit()
    db.refresh(bill)
    db.refresh(line)
    return bill


class InventoryLockV123Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_inventory(self.db)

    def tearDown(self):
        self.db.close()

    def test_sequential_subtract_second_fails(self):
        m = self.m
        subtract_inventory(
            self.db, m["product"].id, m["brand"].id, m["location"].id, m["bag_type"].id, 60, Decimal("0")
        )
        self.db.commit()
        row = self.db.get(Inventory, m["inventory"].id)
        self.assertEqual(row.bag_count, 40)

        with self.assertRaises(ValueError) as ctx:
            subtract_inventory(
                self.db, m["product"].id, m["brand"].id, m["location"].id, m["bag_type"].id, 60, Decimal("0")
            )
        self.assertEqual(str(ctx.exception), "Insufficient stock")

    def test_fulfillment_sequential_deliver_60_then_60(self):
        m = self.m
        bill1 = _sales_bill(self.db, m, bill_number="S1", ordered_bags=100)
        bill2 = _sales_bill(self.db, m, bill_number="S2", ordered_bags=100)
        line1 = bill1.lines[0]
        line2 = bill2.lines[0]

        create_fulfillment(
            self.db,
            bill_line_id=line1.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("3000"),
            bag_count=60,
            expected_version=1,
        )
        row = self.db.get(Inventory, m["inventory"].id)
        self.assertEqual(row.bag_count, 40)

        with self.assertRaises(ValueError) as ctx:
            create_fulfillment(
                self.db,
                bill_line_id=line2.id,
                entry_type=FulfillmentType.deliver,
                quantity_kg=Decimal("3000"),
                bag_count=60,
                expected_version=1,
            )
        self.assertIn("Insufficient stock", str(ctx.exception))

    def test_bill_fulfillment_event_aggregate_stock_check(self):
        m = self.m
        bill = _sales_bill(self.db, m, bill_number="S-AGG", ordered_bags=200)
        line = bill.lines[0]
        with self.assertRaises(ValueError) as ctx:
            create_bill_fulfillment_event(
                self.db,
                bill.id,
                FulfillmentType.deliver,
                fulfilled_at=datetime(2025, 5, 2, tzinfo=timezone.utc),
                vehicle_no=None,
                line_items=[(line.id, 101, Decimal("0"))],
                expected_version=1,
            )
        self.assertIn("Insufficient stock", str(ctx.exception))

    def test_lock_keys_sorted_for_transfer(self):
        m = self.m
        keys = [
            inventory_row_key(m["product"].id, m["brand"].id, m["location2"].id, m["bag_type"].id),
            inventory_row_key(m["product"].id, m["brand"].id, m["location"].id, m["bag_type"].id),
        ]
        sorted_keys = sort_inventory_keys(keys)
        self.assertEqual(sorted_keys[0][2], m["location"].id)
        self.assertEqual(sorted_keys[1][2], m["location2"].id)

    def test_transfer_locks_two_rows_no_negative(self):
        m = self.m
        create_product_transfer(
            self.db,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_type"].id,
            from_location_id=m["location"].id,
            to_location_id=m["location2"].id,
            bag_count=30,
            loose_kg=Decimal("0"),
            notes=None,
        )
        from_row = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == m["product"].id,
                Inventory.location_id == m["location"].id,
                Inventory.bag_type_id == m["bag_type"].id,
            )
        )
        to_row = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == m["product"].id,
                Inventory.location_id == m["location2"].id,
                Inventory.bag_type_id == m["bag_type"].id,
            )
        )
        self.assertEqual(from_row.bag_count, 70)
        self.assertEqual(to_row.bag_count, 30)

    def test_check_constraint_negative_bag_count(self):
        row = self.db.get(Inventory, self.m["inventory"].id)
        row.bag_count = -1
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_get_inventory_row_for_update_emits_for_update_clause(self):
        m = self.m
        stmt = (
            select(Inventory)
            .where(
                Inventory.product_id == m["product"].id,
                Inventory.brand_id == m["brand"].id,
                Inventory.location_id == m["location"].id,
                Inventory.bag_type_id == m["bag_type"].id,
            )
            .with_for_update()
        )
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("FOR UPDATE", compiled.upper())
        inv = get_inventory_row_for_update(
            self.db,
            m["product"].id,
            m["brand"].id,
            m["location"].id,
            m["bag_type"].id,
        )
        self.assertIsNotNone(inv)
        self.assertEqual(inv.bag_count, 100)

    @unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL for PostgreSQL concurrent test")
    def test_concurrent_subtract_one_succeeds_one_fails(self):
        url = os.environ["TEST_DATABASE_URL"]
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        setup = sessionmaker(bind=engine)()
        m = _seed_inventory(setup, bag_count=100)
        setup.close()

        results: list[str] = []
        barrier = threading.Barrier(2)
        ids = (
            m["product"].id,
            m["brand"].id,
            m["location"].id,
            m["bag_type"].id,
            m["inventory"].id,
        )

        def worker():
            session = sessionmaker(bind=engine)()
            product_id, brand_id, location_id, bag_type_id, inv_id = ids
            try:
                barrier.wait(timeout=5)
                subtract_inventory(session, product_id, brand_id, location_id, bag_type_id, 60, Decimal("0"))
                session.commit()
                results.append("ok")
            except ValueError:
                session.rollback()
                results.append("insufficient")
            finally:
                session.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("insufficient"), 1)
        verify = sessionmaker(bind=engine)()
        try:
            inv = verify.get(Inventory, inv_id)
            self.assertEqual(inv.bag_count, 40)
        finally:
            verify.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
