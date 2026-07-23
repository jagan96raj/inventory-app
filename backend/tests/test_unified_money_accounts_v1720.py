"""Spec v17.2.0 Phase 1 — bank_accounts.kind + per-company Cash seed."""
import unittest
from datetime import date
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
    BookSettings,
    Company,
    User,
)
from app.services.bank_accounts import (
    CASH_ACCOUNT_NAME,
    create_bank_account,
    list_bank_accounts,
    seed_company_cash_account,
)
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


class UnifiedMoneyAccountsV1720Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.db.add(
            BookSettings(
                company_id=1,
                cash_opening_balance=Decimal("1250.50"),
                cash_opening_balance_at=date(2026, 1, 15),
            )
        )
        self.db.add(
            BankAccount(
                company_id=1,
                name="HDFC",
                kind=BankAccountKind.bank,
                opening_balance=Decimal("100"),
                opening_balance_at=date(2026, 1, 1),
                is_default=True,
                is_active=True,
            )
        )
        self.db.commit()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_seed_creates_cash_from_book_settings(self):
        cash = seed_company_cash_account(
            self.db,
            1,
            opening_balance=Decimal("1250.50"),
            opening_balance_at=date(2026, 1, 15),
        )
        self.db.commit()
        self.assertEqual(cash.kind, BankAccountKind.cash)
        self.assertEqual(cash.name, CASH_ACCOUNT_NAME)
        self.assertFalse(cash.is_default)
        self.assertEqual(cash.opening_balance, Decimal("1250.50"))
        self.assertEqual(cash.opening_balance_at, date(2026, 1, 15))

        again = seed_company_cash_account(self.db, 1)
        self.assertEqual(again.id, cash.id)

    def test_existing_banks_remain_bank_kind(self):
        seed_company_cash_account(self.db, 1, opening_balance=Decimal("0"))
        self.db.commit()
        banks = list(
            self.db.scalars(
                select(BankAccount).where(
                    BankAccount.company_id == 1,
                    BankAccount.kind == BankAccountKind.bank,
                )
            ).all()
        )
        self.assertEqual(len(banks), 1)
        self.assertEqual(banks[0].name, "HDFC")
        self.assertEqual(banks[0].kind, BankAccountKind.bank)

    def test_list_bank_accounts_hides_cash(self):
        seed_company_cash_account(self.db, 1, opening_balance=Decimal("0"))
        self.db.commit()
        listed = list_bank_accounts(self.db, company_id=1, active="all")
        self.assertEqual([b.name for b in listed], ["HDFC"])
        self.assertTrue(all(b.kind == BankAccountKind.bank for b in listed))

    def test_create_bank_still_auto_defaults_when_only_cash_exists(self):
        company = Company(name="Only Cash Co", is_active=True)
        self.db.add(company)
        self.db.flush()
        seed_company_cash_account(self.db, company.id, opening_balance=Decimal("0"))
        self.db.commit()
        created = create_bank_account(
            self.db,
            company_id=company.id,
            name="First Bank",
            account_number_last4=None,
            ifsc=None,
            opening_balance=Decimal("0"),
            is_default=False,
        )
        self.assertTrue(created.is_default)
        self.assertEqual(created.kind, BankAccountKind.bank)

    def test_new_company_registration_seeds_cash(self):
        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app)
        with patch("app.routers.companies.settings") as mock_settings:
            mock_settings.allow_company_registration = True
            res = client.post(
                "/api/companies/register",
                json={
                    "company_name": "Cash Seed Co",
                    "company_address_line": "1 Road",
                    "company_phone": "9000000000",
                    "owner_name": "Owner",
                    "email": "cashseed@example.com",
                    "password": STRONG_PASSWORD,
                },
            )
        self.assertEqual(res.status_code, 201, res.text)
        company_id = res.json()["company_id"]
        cash = self.db.scalar(
            select(BankAccount).where(
                BankAccount.company_id == company_id,
                BankAccount.kind == BankAccountKind.cash,
            )
        )
        self.assertIsNotNone(cash)
        self.assertEqual(cash.name, CASH_ACCOUNT_NAME)
        self.assertEqual(cash.opening_balance, Decimal("0"))
        self.assertFalse(cash.is_default)


if __name__ == "__main__":
    unittest.main()
