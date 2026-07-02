"""Spec v11 sales dashboard report tests."""
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


def _add_sales_bill(
    db: Session,
    masters: dict,
    *,
    bill_number: str,
    bill_date: date,
    grand_total: str,
    amount_paid: str = "0",
    payment_status: PaymentStatus = PaymentStatus.unpaid,
    delivery_status: DeliveryStatus = DeliveryStatus.not_delivered,
    qty_kg: str = "100",
    bags: int = 10,
    line_total: str | None = None,
):
    line_total = line_total or grand_total
    bill = Bill(
        bill_number=bill_number,
        bill_type=BillType.sales,
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
    )
    db.add(line)
    db.commit()
    return bill


def _add_purchase_bill(db: Session, masters: dict, bill_date: date, grand_total: str):
    bill = Bill(
        bill_number=f"P-{bill_date.isoformat()}",
        bill_type=BillType.purchase,
        status=BillStatus.finalized,
        bill_date=bill_date,
        customer_id=masters["customer"].id,
        location_id=masters["location"].id,
        grand_total=Decimal(grand_total),
        subtotal=Decimal(grand_total),
        amount_paid=Decimal("0"),
        payment_status=PaymentStatus.unpaid,
        order_delivery_status=DeliveryStatus.not_delivered,
    )
    db.add(bill)
    db.commit()


class ReportsV11Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.masters = _seed_master_data(self.db)

    def test_month_isolation_and_summary(self):
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="S-2025-01",
            bill_date=date(2025, 1, 15),
            grand_total="1000.00",
            amount_paid="400.00",
            payment_status=PaymentStatus.partial,
            qty_kg="50",
        )
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="S-2025-02",
            bill_date=date(2025, 2, 10),
            grand_total="2000.00",
            amount_paid="2000.00",
            payment_status=PaymentStatus.paid,
            qty_kg="80",
        )
        jan = reports.get_sales_summary(self.db, 2025, 1)
        feb = reports.get_sales_summary(self.db, 2025, 2)
        self.assertEqual(jan["bill_count"], 1)
        self.assertEqual(jan["total_sales"], Decimal("1000.00"))
        self.assertEqual(jan["total_collected"], Decimal("400.00"))
        self.assertEqual(jan["total_due"], Decimal("600.00"))
        self.assertEqual(feb["bill_count"], 1)
        self.assertEqual(feb["total_sales"], Decimal("2000.00"))
        self.assertEqual(feb["prev_month_sales"], Decimal("1000.00"))
        self.assertEqual(feb["mom_change_percent"], Decimal("100.00"))

    def test_product_grouping_and_share_percent(self):
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="S1",
            bill_date=date(2025, 3, 5),
            grand_total="300.00",
            qty_kg="30",
            line_total="300.00",
        )
        brand_b = Brand(name="Brand B")
        self.db.add(brand_b)
        self.db.flush()
        bill = Bill(
            bill_number="S2",
            bill_type=BillType.sales,
            status=BillStatus.finalized,
            bill_date=date(2025, 3, 8),
            customer_id=self.masters["customer"].id,
            location_id=self.masters["location"].id,
            grand_total=Decimal("700.00"),
            subtotal=Decimal("700.00"),
            amount_paid=Decimal("0"),
            payment_status=PaymentStatus.unpaid,
            order_delivery_status=DeliveryStatus.not_delivered,
        )
        self.db.add(bill)
        self.db.flush()
        self.db.add(
            BillLine(
                bill_id=bill.id,
                product_id=self.masters["product"].id,
                brand_id=brand_b.id,
                bag_type_id=self.masters["bag_type"].id,
                ordered_bags=5,
                ordered_loose_kg=Decimal("0"),
                ordered_quantity_kg=Decimal("70"),
                rate_per_kg=Decimal("10"),
                line_total=Decimal("700.00"),
            )
        )
        self.db.commit()

        by_product = reports.get_sales_by_product(self.db, 2025, 3, "product")
        self.assertEqual(len(by_product["rows"]), 1)
        self.assertEqual(by_product["rows"][0]["amount"], Decimal("1000.00"))
        self.assertEqual(by_product["rows"][0]["share_percent"], Decimal("100.00"))

        by_pb = reports.get_sales_by_product(self.db, 2025, 3, "product_brand")
        self.assertEqual(len(by_pb["rows"]), 2)
        self.assertEqual(by_pb["rows"][0]["amount"], Decimal("700.00"))
        self.assertEqual(by_pb["rows"][0]["share_percent"], Decimal("70.00"))
        self.assertEqual(by_pb["rows"][1]["share_percent"], Decimal("30.00"))

    def test_customer_and_location_aggregation(self):
        customer2 = Customer(name="Customer Two")
        self.db.add(customer2)
        self.db.flush()
        bill = Bill(
            bill_number="S-C2",
            bill_type=BillType.sales,
            status=BillStatus.finalized,
            bill_date=date(2025, 4, 12),
            customer_id=customer2.id,
            location_id=self.masters["location"].id,
            grand_total=Decimal("500.00"),
            subtotal=Decimal("500.00"),
            amount_paid=Decimal("0"),
            payment_status=PaymentStatus.unpaid,
            order_delivery_status=DeliveryStatus.delivered,
        )
        self.db.add(bill)
        self.db.flush()
        self.db.add(
            BillLine(
                bill_id=bill.id,
                product_id=self.masters["product"].id,
                brand_id=self.masters["brand"].id,
                bag_type_id=self.masters["bag_type"].id,
                ordered_bags=5,
                ordered_loose_kg=Decimal("0"),
                ordered_quantity_kg=Decimal("50"),
                rate_per_kg=Decimal("10"),
                line_total=Decimal("500.00"),
            )
        )
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="S-C1",
            bill_date=date(2025, 4, 3),
            grand_total="250.00",
            qty_kg="25",
            delivery_status=DeliveryStatus.delivered,
        )
        self.db.commit()

        customers = reports.get_sales_by_customer(self.db, 2025, 4, limit=10)
        self.assertEqual(len(customers["rows"]), 2)
        self.assertEqual(customers["rows"][0]["customer_name"], "Customer Two")
        self.assertEqual(customers["rows"][0]["amount"], Decimal("500.00"))

        locations = reports.get_sales_by_location(self.db, 2025, 4)
        self.assertEqual(len(locations["rows"]), 1)
        self.assertEqual(locations["rows"][0]["bill_count"], 2)
        self.assertEqual(locations["rows"][0]["amount"], Decimal("750.00"))

    def test_daily_breakdown_sums_to_month_total(self):
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="D1",
            bill_date=date(2025, 5, 2),
            grand_total="100.00",
            qty_kg="10",
        )
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="D2",
            bill_date=date(2025, 5, 20),
            grand_total="250.00",
            qty_kg="25",
        )
        daily = reports.get_sales_daily(self.db, 2025, 5)
        total_amount = sum(r["amount"] for r in daily["rows"])
        total_bills = sum(r["bill_count"] for r in daily["rows"])
        total_kg = sum(r["quantity_kg"] for r in daily["rows"])
        self.assertEqual(total_amount, Decimal("350.00"))
        self.assertEqual(total_bills, 2)
        self.assertEqual(total_kg, Decimal("35.000"))

    def test_compare_mom_math(self):
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="C-PREV",
            bill_date=date(2025, 6, 1),
            grand_total="100.00",
            qty_kg="10",
        )
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="C-CURR",
            bill_date=date(2025, 7, 1),
            grand_total="150.00",
            qty_kg="15",
            amount_paid="150.00",
            payment_status=PaymentStatus.paid,
        )
        compare = reports.get_sales_compare(self.db, 2025, 7)
        self.assertEqual(compare["current"]["sales"], Decimal("150.00"))
        self.assertEqual(compare["previous"]["sales"], Decimal("100.00"))
        self.assertEqual(compare["change_percent"]["sales"], Decimal("50.00"))

    def test_payment_and_delivery_breakdown(self):
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="P1",
            bill_date=date(2025, 8, 1),
            grand_total="100.00",
            payment_status=PaymentStatus.paid,
            amount_paid="100.00",
            delivery_status=DeliveryStatus.delivered,
        )
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="P2",
            bill_date=date(2025, 8, 2),
            grand_total="200.00",
            payment_status=PaymentStatus.partial,
            amount_paid="50.00",
            delivery_status=DeliveryStatus.partial,
        )
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="P3",
            bill_date=date(2025, 8, 3),
            grand_total="300.00",
            payment_status=PaymentStatus.unpaid,
            delivery_status=DeliveryStatus.not_delivered,
        )
        pay = reports.get_sales_payment_breakdown(self.db, 2025, 8)
        self.assertEqual(pay["paid"]["count"], 1)
        self.assertEqual(pay["paid"]["amount"], Decimal("100.00"))
        self.assertEqual(pay["partial"]["count"], 1)
        self.assertEqual(pay["unpaid"]["amount"], Decimal("300.00"))

        delivery = reports.get_sales_delivery_breakdown(self.db, 2025, 8)
        self.assertEqual(delivery["delivered"]["count"], 1)
        self.assertEqual(delivery["partial"]["count"], 1)
        self.assertEqual(delivery["not_delivered"]["count"], 1)

    def test_purchase_bills_excluded(self):
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="S-ONLY",
            bill_date=date(2025, 9, 1),
            grand_total="400.00",
            qty_kg="40",
        )
        _add_purchase_bill(self.db, self.masters, date(2025, 9, 2), "9999.00")
        summary = reports.get_sales_summary(self.db, 2025, 9)
        self.assertEqual(summary["bill_count"], 1)
        self.assertEqual(summary["total_sales"], Decimal("400.00"))

    def test_csv_export(self):
        _add_sales_bill(
            self.db,
            self.masters,
            bill_number="CSV1",
            bill_date=date(2025, 10, 1),
            grand_total="120.00",
            qty_kg="12",
        )
        csv_text = reports.get_sales_export_csv(self.db, 2025, 10, "product_brand")
        self.assertIn("text/csv", "text/csv")
        self.assertIn("Product,Brand,Qty ordered (kg)", csv_text)
        self.assertIn("Wheat", csv_text)
        self.assertIn("Brand A", csv_text)


if __name__ == "__main__":
    unittest.main()
