"""Spec v11.1 business dashboard bill-date reporting tests."""
import unittest
from datetime import date
from decimal import Decimal

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
    Location,
    PaymentStatus,
    Product,
)
from app.services import reports


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_master_data(db: Session) -> dict:
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


def _add_bill(
    db: Session,
    masters: dict,
    *,
    bill_number: str,
    bill_type: BillType,
    bill_date: date,
    grand_total: str,
    amount_paid: str = "0",
    payment_status: PaymentStatus = PaymentStatus.unpaid,
    delivery_status: DeliveryStatus = DeliveryStatus.not_delivered,
    qty_kg: str = "100",
    bags: int = 10,
    line_total: str | None = None,
    net_delivered_kg: str | None = None,
):
    line_total = line_total or grand_total
    bill = Bill(
        bill_number=bill_number,
        bill_type=bill_type,
        status=BillStatus.finalized,
        bill_date=bill_date,
        customer_id=masters["customer"].id,
        location_id=masters["location"].id,
        grand_total=Decimal(grand_total),
        subtotal=Decimal(line_total),
        amount_paid=Decimal(amount_paid),
        payment_status=payment_status,
        order_delivery_status=delivery_status,
    )
    db.add(bill)
    db.flush()
    line = BillLine(
        bill_id=bill.id,
        product_id=masters["product"].id,
        brand_id=masters["brand"].id,
        bag_type_id=masters["bag_type"].id,
        ordered_bags=bags,
        ordered_loose_kg=Decimal("0"),
        ordered_quantity_kg=Decimal(qty_kg),
        rate_per_kg=Decimal("10"),
        line_total=Decimal(line_total),
        net_delivered_kg=Decimal(net_delivered_kg) if net_delivered_kg is not None else Decimal("0"),
    )
    db.add(line)
    db.commit()
    return bill


class ReportsV111Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.masters = _seed_master_data(self.db)

    def test_business_summary_sales_and_purchase(self):
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-MAY",
            bill_type=BillType.sales,
            bill_date=date(2025, 5, 10),
            grand_total="1000.00",
            qty_kg="100",
        )
        _add_bill(
            self.db,
            self.masters,
            bill_number="P-MAY",
            bill_type=BillType.purchase,
            bill_date=date(2025, 5, 12),
            grand_total="500.00",
            qty_kg="50",
        )
        summary = reports.get_business_summary(self.db, 2025, 5)
        self.assertEqual(summary["sales"]["bill_amount"], Decimal("1000.00"))
        self.assertEqual(summary["sales"]["qty_ordered_kg"], Decimal("100.000"))
        self.assertEqual(summary["sales"]["bags_ordered"], 10)
        self.assertEqual(summary["sales"]["bill_count"], 1)
        self.assertEqual(summary["purchase"]["bill_amount"], Decimal("500.00"))
        self.assertEqual(summary["purchase"]["qty_ordered_kg"], Decimal("50.000"))
        self.assertEqual(summary["purchase"]["bags_ordered"], 10)
        self.assertEqual(summary["purchase"]["bill_count"], 1)
        self.assertNotIn("total_collected", summary["sales"])
        self.assertNotIn("collected", summary)

    def test_may_bill_june_payment_bill_amount_unchanged(self):
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-MAY-PAY-JUN",
            bill_type=BillType.sales,
            bill_date=date(2025, 5, 15),
            grand_total="2000.00",
            amount_paid="2000.00",
            payment_status=PaymentStatus.paid,
            qty_kg="200",
        )
        may = reports.get_business_summary(self.db, 2025, 5)
        self.assertEqual(may["sales"]["bill_amount"], Decimal("2000.00"))
        self.assertNotIn("total_collected", may["sales"])

    def test_partial_delivery_uses_ordered_qty_not_delivered(self):
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-PARTIAL",
            bill_type=BillType.sales,
            bill_date=date(2025, 5, 20),
            grand_total="1000.00",
            qty_kg="1000",
            delivery_status=DeliveryStatus.partial,
            net_delivered_kg="400",
        )
        summary = reports.get_business_summary(self.db, 2025, 5)
        self.assertEqual(summary["sales"]["qty_ordered_kg"], Decimal("1000.000"))

    def test_business_compare_previous_month(self):
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-JUN",
            bill_type=BillType.sales,
            bill_date=date(2025, 6, 1),
            grand_total="100.00",
            qty_kg="10",
        )
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-JUL",
            bill_type=BillType.sales,
            bill_date=date(2025, 7, 1),
            grand_total="150.00",
            qty_kg="15",
        )
        _add_bill(
            self.db,
            self.masters,
            bill_number="P-JUL",
            bill_type=BillType.purchase,
            bill_date=date(2025, 7, 5),
            grand_total="80.00",
            qty_kg="8",
        )
        compare = reports.get_business_compare(self.db, 2025, 7)
        self.assertEqual(compare["current"]["sales_bill_amount"], Decimal("150.00"))
        self.assertEqual(compare["previous"]["sales_bill_amount"], Decimal("100.00"))
        self.assertEqual(compare["change_percent"]["sales_bill_amount"], Decimal("50.00"))
        self.assertEqual(compare["current"]["purchase_bill_amount"], Decimal("80.00"))
        self.assertEqual(compare["previous"]["purchase_bill_amount"], Decimal("0.00"))
        self.assertNotIn("collected", compare["current"])

    def test_daily_bill_amounts_both_types(self):
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-D1",
            bill_type=BillType.sales,
            bill_date=date(2025, 8, 3),
            grand_total="100.00",
            qty_kg="10",
        )
        _add_bill(
            self.db,
            self.masters,
            bill_number="P-D1",
            bill_type=BillType.purchase,
            bill_date=date(2025, 8, 3),
            grand_total="60.00",
            qty_kg="6",
        )
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-D2",
            bill_type=BillType.sales,
            bill_date=date(2025, 8, 10),
            grand_total="40.00",
            qty_kg="4",
        )
        daily = reports.get_daily_bill_amounts(self.db, 2025, 8)
        day3 = next(r for r in daily["rows"] if r["day"] == 3)
        day10 = next(r for r in daily["rows"] if r["day"] == 10)
        self.assertEqual(day3["sales_amount"], Decimal("100.00"))
        self.assertEqual(day3["purchase_amount"], Decimal("60.00"))
        self.assertEqual(day10["sales_amount"], Decimal("40.00"))
        self.assertEqual(day10["purchase_amount"], Decimal("0.00"))

    def test_by_product_purchase_bill_type(self):
        _add_bill(
            self.db,
            self.masters,
            bill_number="P-PROD",
            bill_type=BillType.purchase,
            bill_date=date(2025, 9, 1),
            grand_total="300.00",
            qty_kg="30",
            line_total="300.00",
        )
        sales_data = reports.get_bills_by_product(self.db, 2025, 9, BillType.sales, "product")
        purchase_data = reports.get_bills_by_product(self.db, 2025, 9, BillType.purchase, "product")
        self.assertEqual(len(sales_data["rows"]), 0)
        self.assertEqual(len(purchase_data["rows"]), 1)
        self.assertEqual(purchase_data["rows"][0]["quantity_kg"], Decimal("30.000"))
        self.assertEqual(purchase_data["rows"][0]["amount"], Decimal("300.00"))
        self.assertEqual(purchase_data["bill_type"], "purchase")


if __name__ == "__main__":
    unittest.main()
