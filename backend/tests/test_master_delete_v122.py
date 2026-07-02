"""Spec v12.2 — master delete reference guards."""
import unittest
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine
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
from app.routers.masters import (
    delete_bag_type,
    delete_brand,
    delete_customer,
    delete_location,
    delete_product,
)
from tests.idempotency_helpers import TEST_USER, TEST_VOID_AUTH_PASSWORD


def _void_delete_kwargs() -> dict:
    return {"user": TEST_USER, "void_password": TEST_VOID_AUTH_PASSWORD}


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_masters(db: Session) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Brand A")
    customer = Customer(name="Customer One")
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


def _add_bill(db: Session, masters: dict, *, customer: Customer | None = None, location: Location | None = None):
    bill = Bill(
        bill_number=f"B-{customer.id if customer else masters['customer'].id}",
        bill_type=BillType.sales,
        status=BillStatus.finalized,
        bill_date=date(2025, 1, 1),
        customer_id=(customer or masters["customer"]).id,
        location_id=(location or masters["location"]).id,
        grand_total=Decimal("100"),
        subtotal=Decimal("100"),
        amount_paid=Decimal("0"),
        payment_status=PaymentStatus.unpaid,
        order_delivery_status=DeliveryStatus.not_delivered,
    )
    db.add(bill)
    db.flush()
    db.add(
        BillLine(
            bill_id=bill.id,
            product_id=masters["product"].id,
            brand_id=masters["brand"].id,
            bag_type_id=masters["bag_type"].id,
            ordered_bags=1,
            ordered_loose_kg=Decimal("0"),
            ordered_quantity_kg=Decimal("50"),
            rate_per_kg=Decimal("2"),
            line_total=Decimal("100"),
        )
    )
    db.commit()
    return bill


class MasterDeleteV122Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def test_customer_balance_blocked(self):
        self.m["customer"].credit_balance = Decimal("100")
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            delete_customer(self.m["customer"].id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Cannot delete customer with non-zero balance")

    def test_customer_with_bills_blocked(self):
        _add_bill(self.db, self.m)
        with self.assertRaises(HTTPException) as ctx:
            delete_customer(self.m["customer"].id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("used on 1 bill", ctx.exception.detail)

    def test_unused_customer_deleted(self):
        unused = Customer(name="Unused Co")
        self.db.add(unused)
        self.db.commit()
        result = delete_customer(unused.id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(result, {"ok": True})
        self.assertIsNone(self.db.get(Customer, unused.id))

    def test_product_inventory_blocked(self):
        db = self.db
        m = self.m
        db.add(
            Inventory(
                product_id=m["product"].id,
                brand_id=m["brand"].id,
                location_id=m["location"].id,
                bag_type_id=m["bag_type"].id,
                bag_count=1,
                loose_kg=Decimal("0"),
                total_quantity_kg=Decimal("50"),
            )
        )
        db.commit()
        with self.assertRaises(HTTPException) as ctx:
            delete_product(m["product"].id, db=db, **_void_delete_kwargs())
        self.assertEqual(ctx.exception.detail, "Product in use (inventory)")

    def test_product_on_bill_blocked(self):
        _add_bill(self.db, self.m)
        with self.assertRaises(HTTPException) as ctx:
            delete_product(self.m["product"].id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(ctx.exception.detail, "Product in use (bills)")

    def test_unused_product_deleted(self):
        p = Product(product_name="Unused Product")
        self.db.add(p)
        self.db.commit()
        result = delete_product(p.id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(result, {"ok": True})
        self.assertIsNone(self.db.get(Product, p.id))

    def test_brand_on_bill_blocked(self):
        _add_bill(self.db, self.m)
        with self.assertRaises(HTTPException) as ctx:
            delete_brand(self.m["brand"].id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(ctx.exception.detail, "Brand in use (bills)")

    def test_location_on_bill_blocked(self):
        _add_bill(self.db, self.m)
        with self.assertRaises(HTTPException) as ctx:
            delete_location(self.m["location"].id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(ctx.exception.detail, "Location in use (bills)")

    def test_bag_type_on_bill_blocked(self):
        _add_bill(self.db, self.m)
        with self.assertRaises(HTTPException) as ctx:
            delete_bag_type(self.m["bag_type"].id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(ctx.exception.detail, "Bag type in use (bills)")

    def test_bag_type_on_inventory_blocked(self):
        self.db.add(
            Inventory(
                product_id=self.m["product"].id,
                brand_id=self.m["brand"].id,
                location_id=self.m["location"].id,
                bag_type_id=self.m["bag_type"].id,
                bag_count=2,
                loose_kg=Decimal("0"),
                total_quantity_kg=Decimal("100"),
            )
        )
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            delete_bag_type(self.m["bag_type"].id, db=self.db, **_void_delete_kwargs())
        self.assertEqual(ctx.exception.detail, "Bag type in use (inventory)")


if __name__ == "__main__":
    unittest.main()
