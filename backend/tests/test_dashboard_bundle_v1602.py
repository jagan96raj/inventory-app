"""Spec v16.0.2 — dashboard bundle API."""
import unittest
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
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
from app.schemas import DashboardBundleOut
from app.services import reports
from tests.idempotency_helpers import TEST_USER, ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    qty_kg: str = "100",
    bags: int = 10,
    line_total: str | None = None,
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
            ordered_bags=bags,
            ordered_loose_kg=Decimal("0"),
            ordered_quantity_kg=Decimal(qty_kg),
            rate_per_kg=Decimal("10"),
            line_total=Decimal(line_total),
            net_delivered_kg=Decimal("0"),
        )
    )
    db.commit()
    return bill


class DashboardBundleV1602Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.masters = _seed_master_data(self.db)
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
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-JUN",
            bill_type=BillType.sales,
            bill_date=date(2025, 6, 1),
            grand_total="100.00",
            qty_kg="10",
        )

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_dashboard_bundle_service_matches_individuals(self):
        bundle = reports.get_dashboard_bundle(
            self.db, 2025, 5, BillType.sales, "product_brand"
        )
        self.assertEqual(bundle["summary"], reports.get_business_summary(self.db, 2025, 5))
        self.assertEqual(bundle["compare"], reports.get_business_compare(self.db, 2025, 5))
        self.assertEqual(bundle["daily"], reports.get_daily_bill_amounts(self.db, 2025, 5))
        self.assertEqual(
            bundle["by_product"],
            reports.get_bills_by_product(self.db, 2025, 5, BillType.sales, "product_brand"),
        )
        self.assertEqual(
            bundle["by_customer"],
            reports.get_bills_by_customer(self.db, 2025, 5, BillType.sales, limit=10),
        )
        self.assertEqual(
            bundle["by_location"],
            reports.get_bills_by_location(self.db, 2025, 5, BillType.sales),
        )

    def test_dashboard_bundle_http_matches_individual_endpoints(self):
        qs = "year=2025&month=5&bill_type=sales&group_by=product_brand"
        bundle_res = self.client.get(f"/api/reports/dashboard-bundle?{qs}")
        self.assertEqual(bundle_res.status_code, 200)
        bundle = bundle_res.json()
        expected = DashboardBundleOut.model_validate(
            reports.get_dashboard_bundle(self.db, 2025, 5, BillType.sales, "product_brand")
        ).model_dump(mode="json")
        self.assertEqual(bundle, expected)

    def test_bill_type_and_group_by_only_affect_breakdown_sections(self):
        sales_pb = self.client.get(
            "/api/reports/dashboard-bundle?year=2025&month=5&bill_type=sales&group_by=product_brand"
        ).json()
        purchase_product = self.client.get(
            "/api/reports/dashboard-bundle?year=2025&month=5&bill_type=purchase&group_by=product"
        ).json()

        self.assertEqual(sales_pb["summary"], purchase_product["summary"])
        self.assertEqual(sales_pb["compare"], purchase_product["compare"])
        self.assertEqual(sales_pb["daily"], purchase_product["daily"])
        self.assertNotEqual(sales_pb["by_product"], purchase_product["by_product"])
        self.assertNotEqual(sales_pb["by_customer"], purchase_product["by_customer"])
        self.assertNotEqual(sales_pb["by_location"], purchase_product["by_location"])

    def test_invalid_year_month_rejected(self):
        res = self.client.get(
            "/api/reports/dashboard-bundle?year=1999&month=5&bill_type=sales&group_by=product"
        )
        self.assertEqual(res.status_code, 400)
        res2 = self.client.get(
            "/api/reports/dashboard-bundle?year=2025&month=0&bill_type=sales&group_by=product"
        )
        self.assertEqual(res2.status_code, 422)


if __name__ == "__main__":
    unittest.main()
