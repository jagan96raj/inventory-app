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
        from app.services.accounts import money_now_snapshot

        self.assertEqual(bundle["money_now"], money_now_snapshot(self.db, company_id=1))

    def test_money_now_independent_of_year_month(self):
        may = reports.get_dashboard_bundle(self.db, 2025, 5, BillType.sales, "product_brand")
        june = reports.get_dashboard_bundle(self.db, 2025, 6, BillType.purchase, "product")
        self.assertEqual(may["money_now"], june["money_now"])
        self.assertNotEqual(may["summary"], june["summary"])

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

    def test_summary_includes_expense_and_gross_profit(self):
        from datetime import datetime, timezone

        from app.models.entities import (
            BankAccount,
            BankAccountKind,
            CashBookEntry,
            CashBookEntryType,
            ExpenseCategory,
            ExpenseCategoryKind,
        )

        cat = ExpenseCategory(name="Rent", kind=ExpenseCategoryKind.expense, is_system=False)
        cash = BankAccount(
            company_id=1,
            name="Cash",
            kind=BankAccountKind.cash,
            opening_balance=Decimal("0"),
            opening_balance_at=date(2025, 1, 1),
            is_default=False,
            is_active=True,
        )
        self.db.add_all([cat, cash])
        self.db.flush()
        self.db.add(
            CashBookEntry(
                entry_type=CashBookEntryType.expense,
                category_id=cat.id,
                amount=Decimal("150.00"),
                entry_date=date(2025, 5, 8),
                entry_at=datetime(2025, 5, 8, 12, 0, tzinfo=timezone.utc),
                description="May rent",
                source_account_id=cash.id,
            )
        )
        self.db.commit()

        summary = reports.get_business_summary(self.db, 2025, 5)
        self.assertEqual(summary["expense_total"], Decimal("150.00"))
        self.assertEqual(summary["self_withdrawal_total"], Decimal("0.00"))
        # Sales 1000 − purchase 500 − expense 150 = 350
        self.assertEqual(summary["gross_profit"], Decimal("350.00"))
        self.assertEqual(summary["net_profit"], Decimal("350.00"))

        res = self.client.get(
            "/api/reports/dashboard-bundle?year=2025&month=5&bill_type=sales&group_by=product"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["summary"]["expense_total"], "150.00")
        self.assertEqual(body["summary"]["self_withdrawal_total"], "0.00")
        self.assertEqual(body["summary"]["gross_profit"], "350.00")
        self.assertEqual(body["summary"]["net_profit"], "350.00")

    def test_self_withdrawal_excluded_from_expense_adds_net_profit(self):
        from datetime import datetime, timezone

        from app.models.entities import (
            BankAccount,
            BankAccountKind,
            CashBookEntry,
            CashBookEntryType,
            ExpenseCategory,
            ExpenseCategoryKind,
        )

        rent = ExpenseCategory(name="Rent", kind=ExpenseCategoryKind.expense, is_system=False)
        # Mixed case / whitespace should still match as Self Withdrawal.
        sw = ExpenseCategory(
            name="  Self Withdrawal  ",
            kind=ExpenseCategoryKind.expense,
            is_system=False,
        )
        cash = BankAccount(
            company_id=1,
            name="Cash SW",
            kind=BankAccountKind.cash,
            opening_balance=Decimal("0"),
            opening_balance_at=date(2025, 1, 1),
            is_default=False,
            is_active=True,
        )
        self.db.add_all([rent, sw, cash])
        self.db.flush()
        self.db.add_all(
            [
                CashBookEntry(
                    entry_type=CashBookEntryType.expense,
                    category_id=rent.id,
                    amount=Decimal("150.00"),
                    entry_date=date(2025, 5, 8),
                    entry_at=datetime(2025, 5, 8, 12, 0, tzinfo=timezone.utc),
                    description="May rent",
                    source_account_id=cash.id,
                ),
                CashBookEntry(
                    entry_type=CashBookEntryType.expense,
                    category_id=sw.id,
                    amount=Decimal("200.00"),
                    entry_date=date(2025, 5, 9),
                    entry_at=datetime(2025, 5, 9, 12, 0, tzinfo=timezone.utc),
                    description="Owner draw",
                    source_account_id=cash.id,
                ),
            ]
        )
        self.db.commit()

        summary = reports.get_business_summary(self.db, 2025, 5)
        self.assertEqual(summary["expense_total"], Decimal("150.00"))
        self.assertEqual(summary["self_withdrawal_total"], Decimal("200.00"))
        # Gross: 1000 − 500 − 150 = 350 (SW excluded)
        self.assertEqual(summary["gross_profit"], Decimal("350.00"))
        # Net: 1000 − 500 − 150 − 200 = 150
        self.assertEqual(summary["net_profit"], Decimal("150.00"))

        body = self.client.get(
            "/api/reports/dashboard-bundle?year=2025&month=5&bill_type=sales&group_by=product"
        ).json()
        self.assertEqual(body["summary"]["expense_total"], "150.00")
        self.assertEqual(body["summary"]["self_withdrawal_total"], "200.00")
        self.assertEqual(body["summary"]["gross_profit"], "350.00")
        self.assertEqual(body["summary"]["net_profit"], "150.00")

        fy = reports.get_fiscal_year_summary(self.db, 2025)
        # Seeded FY also has Jun sales 100 from setUp; May SW/rent only in May.
        # Sales May+Jun = 1100, purchase 500, expense excl SW 150, SW 200
        # → gross 1100−500−150=450; net 450−200=250
        self.assertEqual(fy["expense_total"], Decimal("150.00"))
        self.assertEqual(fy["self_withdrawal_total"], Decimal("200.00"))
        may = next(r for r in fy["months"] if r["year"] == 2025 and r["month"] == 5)
        self.assertEqual(may["expense_total"], Decimal("150.00"))
        self.assertEqual(may["self_withdrawal_total"], Decimal("200.00"))
        self.assertEqual(may["gross_profit"], Decimal("350.00"))
        self.assertEqual(may["net_profit"], Decimal("150.00"))

    def test_fiscal_year_summary_april_to_march(self):
        from datetime import datetime, timezone

        from app.models.entities import (
            BankAccount,
            BankAccountKind,
            CashBookEntry,
            CashBookEntryType,
            ExpenseCategory,
            ExpenseCategoryKind,
        )

        # May 2025 sales/purchase already seeded in setUp (1000 / 500).
        # Add Mar 2026 bill (same FY) and Mar 2025 bill (previous FY — excluded).
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-MAR26",
            bill_type=BillType.sales,
            bill_date=date(2026, 3, 15),
            grand_total="200.00",
            qty_kg="20",
            bags=2,
        )
        _add_bill(
            self.db,
            self.masters,
            bill_number="S-MAR25",
            bill_type=BillType.sales,
            bill_date=date(2025, 3, 15),
            grand_total="999.00",
            qty_kg="99",
            bags=9,
        )
        cat = ExpenseCategory(name="Wages", kind=ExpenseCategoryKind.expense, is_system=False)
        cash = BankAccount(
            company_id=1,
            name="FY Cash",
            kind=BankAccountKind.cash,
            opening_balance=Decimal("0"),
            opening_balance_at=date(2025, 1, 1),
            is_default=False,
            is_active=True,
        )
        self.db.add_all([cat, cash])
        self.db.flush()
        self.db.add(
            CashBookEntry(
                entry_type=CashBookEntryType.expense,
                category_id=cat.id,
                amount=Decimal("100.00"),
                entry_date=date(2025, 6, 1),
                entry_at=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
                description="Wages",
                source_account_id=cash.id,
            )
        )
        self.db.commit()

        self.assertEqual(reports.fiscal_year_start_year(2025, 5), 2025)
        self.assertEqual(reports.fiscal_year_start_year(2026, 3), 2025)
        self.assertEqual(reports.fiscal_year_start_year(2026, 4), 2026)

        fy = reports.get_fiscal_year_summary(self.db, 2025)
        self.assertEqual(fy["label"], "FY 2025-26")
        self.assertEqual(fy["date_from"], date(2025, 4, 1))
        self.assertEqual(fy["date_to"], date(2026, 3, 31))
        # Sales: May 1000 + Jun 100 (setUp) + Mar26 200 = 1300. Mar25 excluded.
        # Purchase: May 500. Expense: 100. Gross = 1300 − 500 − 100 = 700.
        self.assertEqual(fy["sales"]["bill_amount"], Decimal("1300.00"))
        self.assertEqual(fy["purchase"]["bill_amount"], Decimal("500.00"))
        self.assertEqual(fy["expense_total"], Decimal("100.00"))
        self.assertEqual(fy["self_withdrawal_total"], Decimal("0.00"))
        self.assertEqual(fy["gross_profit"], Decimal("700.00"))
        self.assertEqual(fy["net_profit"], Decimal("700.00"))
        self.assertEqual(len(fy["months"]), 12)

        res = self.client.get("/api/reports/fiscal-year-summary?start_year=2025")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["gross_profit"], "700.00")
        self.assertEqual(res.json()["net_profit"], "700.00")

        derived = self.client.get("/api/reports/fiscal-year-summary?year=2026&month=2")
        self.assertEqual(derived.status_code, 200)
        self.assertEqual(derived.json()["start_year"], 2025)

        bundle = self.client.get(
            "/api/reports/dashboard-bundle?year=2025&month=5&bill_type=sales&group_by=product"
        ).json()
        self.assertEqual(bundle["fiscal_year"]["gross_profit"], "700.00")
        self.assertEqual(bundle["fiscal_year"]["net_profit"], "700.00")

    def test_job_work_section_aggregates_month_orders(self):
        from app.models.entities import JobWorkLine, JobWorkOrder, JobWorkOrderStatus

        order = JobWorkOrder(
            job_number="JW-001",
            customer_id=self.masters["customer"].id,
            job_date=date(2025, 5, 20),
            status=JobWorkOrderStatus.open,
        )
        cancelled = JobWorkOrder(
            job_number="JW-002",
            customer_id=self.masters["customer"].id,
            job_date=date(2025, 5, 21),
            status=JobWorkOrderStatus.cancelled,
        )
        self.db.add_all([order, cancelled])
        self.db.flush()
        self.db.add_all(
            [
                JobWorkLine(
                    order_id=order.id,
                    product_id=self.masters["product"].id,
                    brand_id=self.masters["brand"].id,
                    bag_type_id=self.masters["bag_type"].id,
                    ordered_bags=8,
                    ordered_quantity_kg=Decimal("400"),
                    received_quantity_kg=Decimal("250"),
                    returned_quantity_kg=Decimal("100"),
                ),
                JobWorkLine(
                    order_id=cancelled.id,
                    product_id=self.masters["product"].id,
                    brand_id=self.masters["brand"].id,
                    bag_type_id=self.masters["bag_type"].id,
                    ordered_bags=5,
                    ordered_quantity_kg=Decimal("999"),
                ),
            ]
        )
        self.db.commit()

        jw = reports.get_job_work_by_product(self.db, 2025, 5, "product")
        self.assertEqual(jw["order_count"], 1)
        self.assertEqual(jw["ordered_quantity_kg"], Decimal("400.000"))
        self.assertEqual(jw["ordered_bags"], 8)
        self.assertEqual(jw["received_quantity_kg"], Decimal("250.000"))
        self.assertEqual(jw["returned_quantity_kg"], Decimal("100.000"))
        self.assertEqual(jw["in_custody_kg"], Decimal("150.000"))
        self.assertEqual(len(jw["rows"]), 1)
        self.assertIsNone(jw["rows"][0]["brand_id"])

        brandwise = reports.get_job_work_by_product(self.db, 2025, 5, "product_brand")
        self.assertEqual(brandwise["rows"][0]["brand_id"], self.masters["brand"].id)

        # Other months see no job work.
        self.assertEqual(reports.get_job_work_by_product(self.db, 2025, 6, "product")["order_count"], 0)

        res = self.client.get(
            "/api/reports/dashboard-bundle?year=2025&month=5&bill_type=sales&group_by=product"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["job_work"]["in_custody_kg"], "150.000")

    def test_product_breakdown_filters_by_customer(self):
        customer2 = Customer(name="Customer Two")
        self.db.add(customer2)
        self.db.flush()
        _add_bill(
            self.db,
            {**self.masters, "customer": customer2},
            bill_number="S-MAY-2",
            bill_type=BillType.sales,
            bill_date=date(2025, 5, 15),
            grand_total="200.00",
            qty_kg="20",
            bags=2,
        )

        all_rows = reports.get_bills_by_product(
            self.db, 2025, 5, BillType.sales, "product"
        )
        filtered = reports.get_bills_by_product(
            self.db,
            2025,
            5,
            BillType.sales,
            "product",
            customer_id=customer2.id,
        )
        self.assertEqual(all_rows["lines_subtotal"], Decimal("1200.00"))
        self.assertEqual(filtered["lines_subtotal"], Decimal("200.00"))
        self.assertEqual(filtered["rows"][0]["quantity_kg"], Decimal("20.000"))

        res = self.client.get(
            f"/api/reports/dashboard-bundle?year=2025&month=5&bill_type=sales"
            f"&group_by=product&customer_id={customer2.id}"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["by_product"]["lines_subtotal"], "200.00")
        # Customer filter must not change company-wide summary KPIs.
        unfiltered = self.client.get(
            "/api/reports/dashboard-bundle?year=2025&month=5&bill_type=sales&group_by=product"
        ).json()
        self.assertEqual(body["summary"], unfiltered["summary"])


if __name__ == "__main__":
    unittest.main()
