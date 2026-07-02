"""Spec v12.5 — fulfillment void (reverse mistaken deliver/receive/return).

Scenarios:
A. Sales deliver 25 of 50 → void → net 0, Not delivered, stock restored
B. Purchase receive 25 of 50 → void → net 0, Not delivered, stock −25
C. Purchase receive 100 → return 30 → void receive blocked; void return → void receive OK
D. Void sales return with insufficient stock → 400
E. Double void → 400
F. Voided entries excluded from delivery status / net fulfilled
"""
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine, select
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
    FulfillmentEntry,
    Inventory,
    Location,
    PaymentStatus,
    Product,
)
from app.routers.fulfillment import void_fulfillment_endpoint
from tests.idempotency_helpers import TEST_VOID_AUTH_PASSWORD, idem_kwargs
from app.services.fulfillment import (
    FULFILLMENT_ALREADY_VOIDED_MSG,
    FULFILLMENT_VOID_RETURNS_FIRST_MSG,
    FulfillmentType,
    create_fulfillment,
    void_fulfillment_entry,
)
from app.services.operations import subtract_inventory


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_masters(db: Session, *, stock_bags: int = 100) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Brand A")
    customer = Customer(name="Test Co")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    db.add_all([product, brand, customer, location, bag_type])
    db.flush()
    inv = Inventory(
        product_id=product.id,
        brand_id=brand.id,
        location_id=location.id,
        bag_type_id=bag_type.id,
        bag_count=stock_bags,
        loose_kg=Decimal("0"),
        total_quantity_kg=Decimal(str(stock_bags * 50)),
    )
    db.add(inv)
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "customer": customer,
        "location": location,
        "bag_type": bag_type,
        "inventory": inv,
    }


def _sales_bill(db: Session, m: dict, *, ordered_bags: int = 50, bill_number: str = "S-VOID-001") -> tuple[Bill, BillLine]:
    bill = Bill(
        bill_number=bill_number,
        bill_type=BillType.sales,
        status=BillStatus.finalized,
        bill_date=date(2026, 6, 1),
        customer_id=m["customer"].id,
        location_id=m["location"].id,
        grand_total=Decimal(str(ordered_bags * 50)),
        subtotal=Decimal(str(ordered_bags * 50)),
        amount_paid=Decimal("0"),
        payment_status=PaymentStatus.unpaid,
        order_delivery_status=DeliveryStatus.not_delivered,
    )
    db.add(bill)
    db.flush()
    line = BillLine(
        bill_id=bill.id,
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
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
    return bill, line


def _purchase_bill(db: Session, m: dict, *, ordered_bags: int = 50) -> tuple[Bill, BillLine]:
    bill = Bill(
        bill_number="P-VOID-001",
        bill_type=BillType.purchase,
        status=BillStatus.finalized,
        bill_date=date(2026, 6, 1),
        customer_id=m["customer"].id,
        grand_total=Decimal(str(ordered_bags * 50)),
        subtotal=Decimal(str(ordered_bags * 50)),
        amount_paid=Decimal("0"),
        payment_status=PaymentStatus.unpaid,
        order_delivery_status=DeliveryStatus.not_delivered,
    )
    db.add(bill)
    db.flush()
    line = BillLine(
        bill_id=bill.id,
        product_id=m["product"].id,
        brand_id=m["brand"].id,
        bag_type_id=m["bag_type"].id,
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
    return bill, line


def _fulfill(db: Session, bill: Bill, **kwargs):
    db.refresh(bill)
    return create_fulfillment(db, expected_version=bill.version, **kwargs)


def _void_fulfill(db: Session, bill: Bill, entry_id: int):
    db.refresh(bill)
    return void_fulfillment_entry(db, entry_id, expected_version=bill.version)


class FulfillmentVoidV125Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def test_a_sales_deliver_void_restores_stock_and_status(self):
        bill, line = _sales_bill(self.db, self.m, ordered_bags=50)
        deliver = _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("1250"),
            bag_count=25,
        )
        self.db.refresh(bill)
        self.db.refresh(line)
        inv = self.db.get(Inventory, self.m["inventory"].id)
        self.assertEqual(inv.bag_count, 75)
        self.assertEqual(line.net_delivered_kg, Decimal("1250"))
        self.assertEqual(line.line_delivery_status, DeliveryStatus.partial)
        self.assertEqual(bill.order_delivery_status, DeliveryStatus.partial)

        _void_fulfill(self.db, bill, deliver.id)

        self.db.refresh(bill)
        self.db.refresh(line)
        inv = self.db.get(Inventory, self.m["inventory"].id)
        entry = self.db.get(FulfillmentEntry, deliver.id)
        self.assertIsNotNone(entry.voided_at)
        self.assertEqual(inv.bag_count, 100)
        self.assertEqual(line.net_delivered_kg, Decimal("0"))
        self.assertEqual(line.net_returned_kg, Decimal("0"))
        self.assertEqual(line.line_delivery_status, DeliveryStatus.not_delivered)
        self.assertEqual(bill.order_delivery_status, DeliveryStatus.not_delivered)

    def test_b_purchase_receive_void_reduces_stock_and_status(self):
        bill, line = _purchase_bill(self.db, self.m, ordered_bags=50)
        receive = _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("1250"),
            bag_count=25,
            location_id=self.m["location"].id,
        )
        self.db.refresh(bill)
        self.db.refresh(line)
        inv = self.db.get(Inventory, self.m["inventory"].id)
        self.assertEqual(inv.bag_count, 125)
        self.assertEqual(line.net_received_kg, Decimal("1250"))
        self.assertEqual(line.line_delivery_status, DeliveryStatus.partial)

        _void_fulfill(self.db, bill, receive.id)

        self.db.refresh(bill)
        self.db.refresh(line)
        inv = self.db.get(Inventory, self.m["inventory"].id)
        self.assertEqual(inv.bag_count, 100)
        self.assertEqual(line.net_received_kg, Decimal("0"))
        self.assertEqual(line.line_delivery_status, DeliveryStatus.not_delivered)
        self.assertEqual(bill.order_delivery_status, DeliveryStatus.not_delivered)

    def test_c_purchase_void_receive_blocked_until_returns_voided(self):
        bill, line = _purchase_bill(self.db, self.m, ordered_bags=100)
        receive = _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("5000"),
            bag_count=100,
            location_id=self.m["location"].id,
        )
        ret = _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.return_,
            quantity_kg=Decimal("1500"),
            bag_count=30,
            parent_entry_id=receive.id,
            location_id=self.m["location"].id,
        )
        self.db.refresh(line)
        self.assertEqual(line.net_received_kg, Decimal("5000"))
        self.assertEqual(line.net_returned_kg, Decimal("1500"))

        with self.assertRaises(ValueError) as ctx:
            _void_fulfill(self.db, bill, receive.id)
        self.assertEqual(str(ctx.exception), FULFILLMENT_VOID_RETURNS_FIRST_MSG)

        _void_fulfill(self.db, bill, ret.id)
        _void_fulfill(self.db, bill, receive.id)

        self.db.refresh(bill)
        self.db.refresh(line)
        inv = self.db.get(Inventory, self.m["inventory"].id)
        self.assertEqual(inv.bag_count, 100)
        self.assertEqual(line.net_received_kg, Decimal("0"))
        self.assertEqual(bill.order_delivery_status, DeliveryStatus.not_delivered)

    def test_d_void_sales_return_insufficient_stock(self):
        m = self.m
        bill, line = _sales_bill(self.db, m, ordered_bags=50)
        _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("2500"),
            bag_count=50,
        )
        ret = _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.return_,
            quantity_kg=Decimal("1250"),
            bag_count=25,
            location_id=m["location"].id,
        )
        inv = self.db.get(Inventory, m["inventory"].id)
        self.assertEqual(inv.bag_count, 75)

        subtract_inventory(
            self.db,
            m["product"].id,
            m["brand"].id,
            m["location"].id,
            m["bag_type"].id,
            75,
            Decimal("0"),
        )
        self.db.commit()
        inv = self.db.get(Inventory, m["inventory"].id)
        self.assertIsNone(inv)

        with self.assertRaises(ValueError) as ctx:
            _void_fulfill(self.db, bill, ret.id)
        self.assertEqual(str(ctx.exception), "Insufficient stock")

    def test_e_double_void_raises_400(self):
        bill, line = _sales_bill(self.db, self.m, ordered_bags=50)
        deliver = _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("1250"),
            bag_count=25,
        )
        _void_fulfill(self.db, bill, deliver.id)

        with self.assertRaises(ValueError) as ctx:
            _void_fulfill(self.db, bill, deliver.id)
        self.assertEqual(str(ctx.exception), FULFILLMENT_ALREADY_VOIDED_MSG)

        self.db.refresh(bill)
        with self.assertRaises(HTTPException) as http_ctx:
            void_fulfillment_endpoint(
                deliver.id,
                expected_bill_version=bill.version,
                void_password=TEST_VOID_AUTH_PASSWORD,
                db=self.db,
                **idem_kwargs(),
            )
        self.assertEqual(http_ctx.exception.status_code, 400)

    def test_f_voided_excluded_from_net_fulfilled_and_status(self):
        bill, line = _sales_bill(self.db, self.m, ordered_bags=100)
        d1 = _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("1250"),
            bag_count=25,
        )
        _fulfill(
            self.db,
            bill,
            bill_line_id=line.id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("1250"),
            bag_count=25,
        )
        self.db.refresh(line)
        self.assertEqual(line.net_delivered_kg, Decimal("2500"))
        self.assertEqual(line.line_delivery_status, DeliveryStatus.partial)

        _void_fulfill(self.db, bill, d1.id)

        self.db.refresh(bill)
        self.db.refresh(line)
        active = self.db.scalars(
            select(FulfillmentEntry).where(
                FulfillmentEntry.bill_line_id == line.id,
                FulfillmentEntry.voided_at.is_(None),
            )
        ).all()
        self.assertEqual(len(active), 1)
        self.assertEqual(line.net_delivered_kg, Decimal("1250"))
        self.assertEqual(line.line_delivery_status, DeliveryStatus.partial)
        self.assertEqual(bill.order_delivery_status, DeliveryStatus.partial)


if __name__ == "__main__":
    unittest.main()
