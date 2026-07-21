"""Spec v17.0.2 — multi-tenant Phase 3: tenant-scoped API queries."""
import unittest
from decimal import Decimal

from datetime import date
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
    BillStatus,
    BillType,
    Brand,
    Company,
    Customer,
    Inventory,
    InventoryOwnerType,
    Location,
    PaymentStatus,
    Product,
    User,
    UserRole,
)
from tests.idempotency_helpers import ensure_test_user, new_test_idempotency_key, void_auth_header


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class CompaniesV1702Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)

        # Company 1 masters + bill + inventory
        self.c1_customer = Customer(name="Acme Co1", company_id=1)
        self.c1_product = Product(product_name="Wheat Co1", company_id=1)
        self.c1_brand = Brand(name="Raw Co1", company_id=1)
        self.c1_location = Location(name="WH Co1", company_id=1)
        self.c1_bag = BagType(
            name="50kg Co1", weight_per_bag_kg=Decimal("50"), is_loose=False, company_id=1
        )
        self.db.add_all(
            [self.c1_customer, self.c1_product, self.c1_brand, self.c1_location, self.c1_bag]
        )
        self.db.flush()

        self.c1_bill = Bill(
            company_id=1,
            bill_number="S-000001",
            bill_type=BillType.sales,
            status=BillStatus.finalized,
            bill_date=date(2026, 7, 1),
            customer_id=self.c1_customer.id,
            location_id=self.c1_location.id,
            subtotal=Decimal("1000"),
            grand_total=Decimal("1000"),
            amount_paid=Decimal("0"),
            payment_status=PaymentStatus.unpaid,
        )
        self.c1_inv = Inventory(
            company_id=1,
            product_id=self.c1_product.id,
            brand_id=self.c1_brand.id,
            location_id=self.c1_location.id,
            bag_type_id=self.c1_bag.id,
            owner_type=InventoryOwnerType.owned,
            bag_count=10,
            loose_kg=Decimal("0"),
        )
        self.db.add_all([self.c1_bill, self.c1_inv])

        # Company 2 + owner user + isolated masters
        self.db.add(Company(id=2, name="Other Co", is_active=True))
        self.db.flush()
        self.user2 = User(
            id=2,
            email="other@example.com",
            name="Other Owner",
            password_hash="x",
            role=UserRole.owner,
            company_id=2,
            is_active=True,
        )
        self.c2_customer = Customer(name="Beta Co2", company_id=2)
        self.c2_product = Product(product_name="Rice Co2", company_id=2)
        self.c2_brand = Brand(name="Raw Co2", company_id=2)
        self.c2_location = Location(name="WH Co2", company_id=2)
        self.c2_bag = BagType(
            name="50kg Co2", weight_per_bag_kg=Decimal("50"), is_loose=False, company_id=2
        )
        self.db.add_all(
            [
                self.user2,
                self.c2_customer,
                self.c2_product,
                self.c2_brand,
                self.c2_location,
                self.c2_bag,
            ]
        )
        self.db.flush()
        self.c2_inv = Inventory(
            company_id=2,
            product_id=self.c2_product.id,
            brand_id=self.c2_brand.id,
            location_id=self.c2_location.id,
            bag_type_id=self.c2_bag.id,
            owner_type=InventoryOwnerType.owned,
            bag_count=5,
            loose_kg=Decimal("0"),
        )
        self.db.add(self.c2_inv)
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self._as_company1()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def _as_company1(self):
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)

    def _as_company2(self):
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 2)

    def test_company2_products_list_excludes_company1(self):
        self._as_company2()
        res = self.client.get("/api/products")
        self.assertEqual(res.status_code, 200, res.text)
        names = {row["product_name"] for row in res.json()["items"]}
        self.assertIn("Rice Co2", names)
        self.assertNotIn("Wheat Co1", names)

    def test_company2_cannot_get_company1_bill(self):
        self._as_company2()
        res = self.client.get(f"/api/bills/{self.c1_bill.id}")
        self.assertEqual(res.status_code, 404, res.text)

    def test_company1_still_sees_own_masters_and_bills(self):
        self._as_company1()
        products = self.client.get("/api/products")
        self.assertEqual(products.status_code, 200, products.text)
        names = {row["product_name"] for row in products.json()["items"]}
        self.assertIn("Wheat Co1", names)
        self.assertNotIn("Rice Co2", names)

        bills = self.client.get("/api/bills")
        self.assertEqual(bills.status_code, 200, bills.text)
        bill_ids = {row["id"] for row in bills.json()["items"]}
        self.assertIn(self.c1_bill.id, bill_ids)

        bill = self.client.get(f"/api/bills/{self.c1_bill.id}")
        self.assertEqual(bill.status_code, 200, bill.text)
        self.assertEqual(bill.json()["id"], self.c1_bill.id)

    def test_company2_cannot_pay_company1_bill(self):
        self._as_company2()
        res = self.client.post(
            "/api/payments",
            json={
                "bill_id": self.c1_bill.id,
                "amount": "10.00",
                "payment_mode": "cash",
                "paid_date": "2026-07-01",
                "expected_version": 1,
            },
            headers={**void_auth_header(), "Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertIn(res.status_code, (400, 404), res.text)

    def test_inventory_list_isolation(self):
        self._as_company1()
        res1 = self.client.get("/api/inventory")
        self.assertEqual(res1.status_code, 200, res1.text)
        ids1 = {row["id"] for row in res1.json()["items"]}
        self.assertIn(self.c1_inv.id, ids1)
        self.assertNotIn(self.c2_inv.id, ids1)

        self._as_company2()
        res2 = self.client.get("/api/inventory")
        self.assertEqual(res2.status_code, 200, res2.text)
        ids2 = {row["id"] for row in res2.json()["items"]}
        self.assertIn(self.c2_inv.id, ids2)
        self.assertNotIn(self.c1_inv.id, ids2)

    def test_reports_dashboard_company2_excludes_company1_totals(self):
        self._as_company2()
        res = self.client.get("/api/reports/dashboard-bundle?year=2026&month=7")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        sales = data["summary"]["sales"]
        self.assertEqual(sales["bill_count"], 0)
        self.assertEqual(Decimal(str(sales["bill_amount"])), Decimal("0.00"))
        self.assertEqual(data["by_customer"]["rows"], [])
        self.assertNotIn("S-000001", str(data))

        # Company 1 still sees its July sales bill.
        self._as_company1()
        res1 = self.client.get("/api/reports/dashboard-bundle?year=2026&month=7")
        self.assertEqual(res1.status_code, 200, res1.text)
        sales1 = res1.json()["summary"]["sales"]
        self.assertEqual(sales1["bill_count"], 1)
        self.assertEqual(Decimal(str(sales1["bill_amount"])), Decimal("1000.00"))

        self._as_company2()
        cust_rows = self.client.get("/api/accounts/customers")
        self.assertEqual(cust_rows.status_code, 200, cust_rows.text)
        payload = cust_rows.json()
        items = payload.get("items") if isinstance(payload, dict) else payload
        cust_names = {
            row.get("name") or row.get("customer_name")
            for row in (items or [])
            if isinstance(row, dict)
        }
        self.assertNotIn("Acme Co1", cust_names)
        self.assertIn("Beta Co2", cust_names)

    def test_users_list_company_isolation(self):
        self._as_company2()
        res = self.client.get("/api/users")
        self.assertEqual(res.status_code, 200, res.text)
        emails = {row["email"] for row in res.json()}
        self.assertIn("other@example.com", emails)
        self.assertNotIn("test@example.com", emails)

        self._as_company1()
        res1 = self.client.get("/api/users")
        self.assertEqual(res1.status_code, 200, res1.text)
        emails1 = {row["email"] for row in res1.json()}
        self.assertIn("test@example.com", emails1)
        self.assertNotIn("other@example.com", emails1)

    def test_book_settings_allowed_and_isolated_for_company2(self):
        """v17.0.3: non–company-1 may access book settings (own row); covered fully in v1703."""
        self._as_company2()
        res = self.client.get("/api/book-settings")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("cash_opening_balance", res.json())

        self._as_company1()
        res1 = self.client.get("/api/book-settings")
        self.assertEqual(res1.status_code, 200, res1.text)


if __name__ == "__main__":
    unittest.main()
