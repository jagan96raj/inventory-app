"""Spec v17.0.3 — multi-tenant Phase 4: per-company book settings + bill/JW counters."""
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
    BillNumberCounter,
    BillType,
    BookSettings,
    Company,
    JWNumberCounter,
    User,
    UserRole,
)
from app.services.accounts import get_book_settings, get_cash_balance
from app.services.bills import next_bill_number, preview_bill_number
from app.services.job_work import next_job_number, preview_job_number
from tests.idempotency_helpers import ensure_test_user, new_test_idempotency_key


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class CompaniesV1703Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)

        # Company 1 settings with distinctive opening + header (simulate post-migration state)
        c1 = self.db.get(Company, 1)
        c1.phone = "111"
        self.db.add(
            BookSettings(
                id=1,
                company_id=1,
                cash_opening_balance=Decimal("500.00"),
                cash_opening_balance_at=date(2026, 1, 1),
                company_name="Raj Agro",
                company_phone="111",
            )
        )
        self.db.add(
            BillNumberCounter(company_id=1, bill_type=BillType.sales, last_number=10)
        )
        self.db.add(
            BillNumberCounter(company_id=1, bill_type=BillType.purchase, last_number=3)
        )
        self.db.add(JWNumberCounter(company_id=1, last_number=7))

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
        self.db.add(self.user2)
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

    def test_company1_book_settings_preserved(self):
        self._as_company1()
        res = self.client.get("/api/book-settings")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(Decimal(str(data["cash_opening_balance"])), Decimal("500.00"))
        self.assertEqual(data["company_name"], "Raj Agro")
        self.assertEqual(data["company_phone"], "111")

    def test_company2_book_settings_auto_created_not_403(self):
        self._as_company2()
        res = self.client.get("/api/book-settings")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(Decimal(str(data["cash_opening_balance"])), Decimal("0"))
        self.assertEqual(data["company_name"], "Other Co")
        # Distinct row from company 1
        c1 = self.db.scalar(select(BookSettings).where(BookSettings.company_id == 1))
        c2 = self.db.scalar(select(BookSettings).where(BookSettings.company_id == 2))
        self.assertIsNotNone(c2)
        self.assertNotEqual(c1.id, c2.id)

    def test_company2_patch_does_not_change_company1(self):
        self._as_company2()
        res = self.client.patch(
            "/api/book-settings",
            json={"company_name": "Patched Other", "cash_opening_balance": "25.00"},
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["company_name"], "Patched Other")

        c1 = self.db.scalar(select(BookSettings).where(BookSettings.company_id == 1))
        self.assertEqual(c1.company_name, "Raj Agro")
        self.assertEqual(c1.cash_opening_balance, Decimal("500.00"))

    def test_two_companies_both_allocate_sb_000001(self):
        n1 = next_bill_number(self.db, BillType.sales, company_id=2)
        n2 = next_bill_number(self.db, BillType.sales, company_id=2)
        self.db.commit()
        self.assertEqual(n1, "S-000001")
        self.assertEqual(n2, "S-000002")

        # Company 1 continues from preserved last_number=10
        preview_c1 = preview_bill_number(self.db, BillType.sales, company_id=1)
        self.assertEqual(preview_c1, "S-000011")
        allocated_c1 = next_bill_number(self.db, BillType.sales, company_id=1)
        self.db.commit()
        self.assertEqual(allocated_c1, "S-000011")

        # Both can hold S-000001 conceptually (company 2 already did; company-scoped unique)
        rows = self.db.scalars(select(BillNumberCounter)).all()
        by_company = {(r.company_id, r.bill_type): r.last_number for r in rows}
        self.assertEqual(by_company[(2, BillType.sales)], 2)
        self.assertEqual(by_company[(1, BillType.sales)], 11)

    def test_company1_bill_number_continues_not_reset(self):
        self.assertEqual(
            preview_bill_number(self.db, BillType.sales, company_id=1), "S-000011"
        )
        self.assertEqual(
            preview_bill_number(self.db, BillType.purchase, company_id=1), "P-000004"
        )

    def test_jw_preview_allocate_scoped_per_company(self):
        self.assertEqual(preview_job_number(self.db, company_id=1), "JW-000008")
        self.assertEqual(preview_job_number(self.db, company_id=2), "JW-000001")
        jw2 = next_job_number(self.db, company_id=2)
        self.db.commit()
        self.assertEqual(jw2, "JW-000001")
        jw1 = next_job_number(self.db, company_id=1)
        self.db.commit()
        self.assertEqual(jw1, "JW-000008")

        self._as_company2()
        res = self.client.get("/api/job-work/next-number")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["job_number"], "JW-000002")

    def test_accounts_cash_opening_uses_own_settings(self):
        # Seed company 2 opening without going through HTTP
        get_book_settings(self.db, 2)
        c2 = self.db.scalar(select(BookSettings).where(BookSettings.company_id == 2))
        c2.cash_opening_balance = Decimal("99.00")
        self.db.commit()

        bal1 = get_cash_balance(self.db, company_id=1)
        bal2 = get_cash_balance(self.db, company_id=2)
        self.assertEqual(bal1, Decimal("500.00"))
        self.assertEqual(bal2, Decimal("99.00"))


if __name__ == "__main__":
    unittest.main()
