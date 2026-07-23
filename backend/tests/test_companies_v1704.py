"""Spec v17.0.4 — multi-tenant Phase 5: public company registration."""
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BankAccount,
    BankAccountKind,
    BillNumberCounter,
    BillType,
    BookSettings,
    Company,
    ExpenseCategory,
    JWNumberCounter,
    Product,
    User,
    UserRole,
)
from app.services.bills import next_bill_number
from app.services.companies import COMPANY_REGISTRATION_CLOSED
from tests.idempotency_helpers import ensure_test_user

STRONG_PASSWORD = "Test@1234Ab!"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class CompaniesV1704Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        # Raj Agro seed data so isolation is visible
        self.db.add(Product(company_id=1, product_name="Raj Agro Wheat"))
        self.db.add(
            BillNumberCounter(company_id=1, bill_type=BillType.sales, last_number=42)
        )
        self.db.add(
            BillNumberCounter(company_id=1, bill_type=BillType.purchase, last_number=5)
        )
        self.db.add(JWNumberCounter(company_id=1, last_number=9))
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        # Public register must not rely on get_current_user; clear any leftover overrides
        app.dependency_overrides.pop(get_current_user, None)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _register_payload(self, email: str = "newco@example.com", **overrides):
        body = {
            "company_name": "New Traders",
            "company_address_line": "12 Market Road",
            "company_phone": "9000000000",
            "owner_name": "Owner One",
            "email": email,
            "password": STRONG_PASSWORD,
        }
        body.update(overrides)
        return body

    def test_flag_false_register_403(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = False
            res = self.client.post("/api/companies/register", json=self._register_payload())
        self.assertEqual(res.status_code, 403, res.text)
        self.assertIn(COMPANY_REGISTRATION_CLOSED, res.json()["detail"])

    def test_registration_status_reflects_flag(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = False
            res = self.client.get("/api/companies/registration-status")
            self.assertEqual(res.status_code, 200)
            self.assertFalse(res.json()["allowed"])

            mock_settings.allow_company_registration = True
            res = self.client.get("/api/companies/registration-status")
            self.assertTrue(res.json()["allowed"])

    def test_flag_true_creates_company_and_owner(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = True
            res = self.client.post("/api/companies/register", json=self._register_payload())
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertEqual(data["email"], "newco@example.com")
        self.assertEqual(data["role"], "owner")
        self.assertEqual(data["company_name"], "New Traders")
        self.assertNotEqual(data["company_id"], 1)

        user = self.db.scalar(select(User).where(User.email == "newco@example.com"))
        self.assertIsNotNone(user)
        self.assertEqual(user.role, UserRole.owner)
        company = self.db.get(Company, user.company_id)
        self.assertEqual(company.name, "New Traders")
        self.assertEqual(company.address_line, "12 Market Road")
        self.assertEqual(company.phone, "9000000000")

    def test_new_company_masters_empty_and_settings(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = True
            res = self.client.post("/api/companies/register", json=self._register_payload())
        self.assertEqual(res.status_code, 201, res.text)
        user = self.db.scalar(select(User).where(User.email == "newco@example.com"))
        company_id = user.company_id

        products = list(
            self.db.scalars(select(Product).where(Product.company_id == company_id)).all()
        )
        self.assertEqual(products, [])
        categories = list(
            self.db.scalars(select(ExpenseCategory).where(ExpenseCategory.company_id == company_id)).all()
        )
        self.assertGreater(len(categories), 0)
        self.assertIn("Transfer", {row.name for row in categories})

        settings_row = self.db.scalar(
            select(BookSettings).where(BookSettings.company_id == company_id)
        )
        self.assertIsNotNone(settings_row)
        # Legacy book_settings company_* columns are not populated on register.
        self.assertIsNone(settings_row.company_name)
        self.assertIsNone(settings_row.company_address_line)
        self.assertIsNone(settings_row.company_phone)
        self.assertEqual(Decimal(str(settings_row.cash_opening_balance)), Decimal("0"))

        cash = self.db.scalar(
            select(BankAccount).where(
                BankAccount.company_id == company_id,
                BankAccount.kind == BankAccountKind.cash,
            )
        )
        self.assertIsNotNone(cash)
        self.assertEqual(cash.name, "Cash")
        self.assertFalse(cash.is_default)

        # API isolation: list products as new owner
        app.dependency_overrides[get_current_user] = lambda: user
        list_res = self.client.get("/api/products")
        self.assertEqual(list_res.status_code, 200, list_res.text)
        self.assertEqual(list_res.json().get("items", list_res.json()), [])

        book_res = self.client.get("/api/book-settings")
        self.assertEqual(book_res.status_code, 200, book_res.text)
        self.assertEqual(book_res.json()["company_name"], "New Traders")
        self.assertEqual(Decimal(str(book_res.json()["cash_opening_balance"])), Decimal("0"))

    def test_new_company_allocates_sb_000001_independently(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = True
            res = self.client.post("/api/companies/register", json=self._register_payload())
        self.assertEqual(res.status_code, 201, res.text)
        user = self.db.scalar(select(User).where(User.email == "newco@example.com"))
        num = next_bill_number(self.db, BillType.sales, user.company_id)
        self.assertEqual(num, "S-000001")
        # Company 1 counter untouched
        c1 = self.db.scalar(
            select(BillNumberCounter).where(
                BillNumberCounter.company_id == 1,
                BillNumberCounter.bill_type == BillType.sales,
            )
        )
        self.assertEqual(c1.last_number, 42)

    def test_duplicate_email_409(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = True
            first = self.client.post("/api/companies/register", json=self._register_payload())
            self.assertEqual(first.status_code, 201, first.text)
            second = self.client.post(
                "/api/companies/register",
                json=self._register_payload(company_name="Other Co"),
            )
        self.assertEqual(second.status_code, 409, second.text)

    def test_weak_password_400(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = True
            res = self.client.post(
                "/api/companies/register",
                json=self._register_payload(password="NoSpecial1"),
            )
        self.assertEqual(res.status_code, 400, res.text)

    def test_empty_company_name_rejected(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = True
            res = self.client.post(
                "/api/companies/register",
                json=self._register_payload(company_name="   "),
            )
        self.assertIn(res.status_code, (400, 422), res.text)

    def test_cross_company_isolation_after_register(self):
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = True
            res = self.client.post("/api/companies/register", json=self._register_payload())
        self.assertEqual(res.status_code, 201, res.text)
        new_user = self.db.scalar(select(User).where(User.email == "newco@example.com"))

        # Company 1 still sees its product
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)
        c1_list = self.client.get("/api/products")
        self.assertEqual(c1_list.status_code, 200)
        c1_body = c1_list.json()
        c1_items = c1_body.get("items", c1_body)
        names = [p["product_name"] for p in c1_items]
        self.assertIn("Raj Agro Wheat", names)

        # New company does not
        app.dependency_overrides[get_current_user] = lambda: new_user
        c2_list = self.client.get("/api/products")
        c2_body = c2_list.json()
        self.assertEqual(c2_body.get("items", c2_body), [])


if __name__ == "__main__":
    unittest.main()
