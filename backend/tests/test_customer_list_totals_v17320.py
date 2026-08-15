"""Spec v17.3.20 — customer list credit/debit totals over the filtered set."""
import unittest
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import Company, Customer
from tests.idempotency_helpers import TEST_USER, ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


class CustomerListTotalsV17320Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        if self.db.get(Company, 2) is None:
            self.db.add(Company(id=2, name="Other Co", is_active=True))
            self.db.flush()
        self.db.add_all(
            [
                Customer(
                    name="Alpha Mills",
                    company_id=1,
                    credit_balance=Decimal("100.00"),
                    debit_balance=Decimal("40.00"),
                ),
                Customer(
                    name="Beta Traders",
                    company_id=1,
                    credit_balance=Decimal("25.50"),
                    debit_balance=Decimal("10.00"),
                ),
                Customer(
                    name="Other Co Customer",
                    company_id=2,
                    credit_balance=Decimal("999.00"),
                    debit_balance=Decimal("888.00"),
                ),
            ]
        )
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_totals_sum_all_company_customers_not_just_page(self):
        res = self.client.get("/api/customers?limit=1&offset=0")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["total"], 2)
        self.assertEqual(_money(body["credit_total"]), Decimal("125.50"))
        self.assertEqual(_money(body["debit_total"]), Decimal("50.00"))

    def test_search_filter_narrows_totals(self):
        res = self.client.get("/api/customers?search=alpha&limit=25&offset=0")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["name"], "Alpha Mills")
        self.assertEqual(_money(body["credit_total"]), Decimal("100.00"))
        self.assertEqual(_money(body["debit_total"]), Decimal("40.00"))

    def test_accounts_customers_totals_respect_search(self):
        res = self.client.get("/api/accounts/customers?search=beta&limit=1")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(_money(body["credit_total"]), Decimal("25.50"))
        self.assertEqual(_money(body["debit_total"]), Decimal("10.00"))
