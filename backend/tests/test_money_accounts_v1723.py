"""Spec v17.2.3 Phase 4 — money accounts API kind=cash|bank list/create."""
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import BankAccount, BankAccountKind, BookSettings, User
from app.services.bank_accounts import (
    create_bank_account,
    edit_bank_account,
    list_bank_accounts,
    seed_company_cash_account,
)
from tests.idempotency_helpers import ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class MoneyAccountsApiV1723Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.db.add(
            BookSettings(
                company_id=1,
                cash_opening_balance=Decimal("100"),
                cash_opening_balance_at=date(2026, 1, 1),
            )
        )
        self.bank = BankAccount(
            company_id=1,
            name="HDFC",
            kind=BankAccountKind.bank,
            opening_balance=Decimal("0"),
            opening_balance_at=date(2026, 1, 1),
            is_default=True,
            is_active=True,
        )
        self.db.add(self.bank)
        self.db.commit()
        self.cash = seed_company_cash_account(
            self.db, 1, opening_balance=Decimal("100"), opening_balance_at=date(2026, 1, 1)
        )
        self.db.commit()

        def override_db():
            yield self.db

        user = self.db.get(User, 1)
        assert user is not None
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: user
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_list_default_bank_only(self):
        listed = list_bank_accounts(self.db, company_id=1, active="all", kind="bank")
        self.assertEqual([b.name for b in listed], ["HDFC"])

    def test_list_all_includes_cash(self):
        listed = list_bank_accounts(self.db, company_id=1, active="all", kind="all")
        names = [b.name for b in listed]
        self.assertIn("Cash", names)
        self.assertIn("HDFC", names)
        self.assertEqual(listed[0].kind, BankAccountKind.cash)

    def test_create_cash_rejects_second(self):
        with self.assertRaises(ValueError):
            create_bank_account(
                self.db,
                company_id=1,
                name="Petty cash",
                kind=BankAccountKind.cash,
                account_number_last4=None,
                ifsc=None,
                opening_balance=Decimal("0"),
                is_default=False,
            )

    def test_edit_cash_opening_syncs_book_settings(self):
        edited = edit_bank_account(
            self.db,
            self.cash.id,
            company_id=1,
            name="Cash",
            account_number_last4=None,
            ifsc=None,
            is_active=None,
            opening_balance=Decimal("250"),
        )
        self.assertEqual(edited.opening_balance, Decimal("250"))
        settings = self.db.scalar(select(BookSettings).where(BookSettings.company_id == 1))
        assert settings is not None
        self.assertEqual(settings.cash_opening_balance, Decimal("250"))

    def test_api_list_kind_all_and_create_bank(self):
        r = self.client.get("/api/bank-accounts?kind=all&active=all&limit=50")
        self.assertEqual(r.status_code, 200, r.text)
        kinds = {row["kind"] for row in r.json()["items"]}
        self.assertEqual(kinds, {"cash", "bank"})
        for row in r.json()["items"]:
            self.assertIn("kind", row)

        r2 = self.client.post(
            "/api/bank-accounts",
            json={
                "name": f"ICICI-{uuid4().hex[:6]}",
                "kind": "bank",
                "opening_balance": "10",
                "is_default": False,
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(r2.status_code, 201, r2.text)
        self.assertEqual(r2.json()["kind"], "bank")


if __name__ == "__main__":
    unittest.main()
