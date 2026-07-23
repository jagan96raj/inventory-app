"""Spec v17.2.1 Phase 2 — money account_id dual-write + backfill helpers."""
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import (
    BankAccount,
    BankAccountKind,
    Bill,
    BillStatus,
    BillType,
    CashBookEntry,
    CashBookEntryType,
    CashBookSourceMode,
    Customer,
    ExpenseCategory,
    ExpenseCategoryKind,
    Location,
    Payment,
    PaymentMode,
    PaymentStatus,
)
from app.utils.time import utc_now
from app.services.bank_accounts import (
    resolve_money_account_id,
    seed_company_cash_account,
)
from app.services.cash_book import create_cash_book_entry, edit_cash_book_entry
from app.services.payments import create_payment
from tests.idempotency_helpers import ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class MoneyAccountIdsV1721Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.cash = seed_company_cash_account(
            self.db, 1, opening_balance=Decimal("500"), opening_balance_at=date(2026, 1, 1)
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
        self.location = Location(company_id=1, name="Godown")
        self.customer = Customer(company_id=1, name="Buyer")
        self.rent = ExpenseCategory(
            company_id=1, name="Rent", kind=ExpenseCategoryKind.expense, is_system=False
        )
        self.transfer = ExpenseCategory(
            company_id=1, name="Transfer", kind=ExpenseCategoryKind.transfer, is_system=True
        )
        self.db.add_all(
            [
                self.bank,
                self.location,
                self.customer,
                self.rent,
                self.transfer,
            ]
        )
        self.db.flush()
        self.bill = Bill(
            company_id=1,
            bill_number="S-000001",
            bill_type=BillType.sales,
            status=BillStatus.finalized,
            bill_date=date(2026, 1, 10),
            customer_id=self.customer.id,
            location_id=self.location.id,
            subtotal=Decimal("1000"),
            grand_total=Decimal("1000"),
            amount_paid=Decimal("0"),
            payment_status=PaymentStatus.unpaid,
            version=1,
        )
        self.db.add(self.bill)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_resolve_cash_and_bank(self):
        self.assertEqual(
            resolve_money_account_id(self.db, 1, mode=CashBookSourceMode.cash),
            self.cash.id,
        )
        self.assertEqual(
            resolve_money_account_id(
                self.db, 1, mode=CashBookSourceMode.bank, bank_account_id=self.bank.id
            ),
            self.bank.id,
        )
        self.assertIsNone(resolve_money_account_id(self.db, 1, mode=PaymentMode.credit))

    def test_cash_book_dual_write_expense_cash(self):
        entry = create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.expense,
            category_id=self.rent.id,
            amount=Decimal("50"),
            description="Rent",
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        self.assertEqual(entry.source_payment_mode, CashBookSourceMode.cash)
        self.assertIsNone(entry.source_bank_account_id)
        self.assertEqual(entry.source_account_id, self.cash.id)
        self.assertIsNone(entry.dest_account_id)

    def test_cash_book_dual_write_transfer_and_edit(self):
        entry = create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.transfer,
            category_id=self.transfer.id,
            amount=Decimal("25"),
            description="Move",
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=CashBookSourceMode.bank,
            dest_bank_account_id=self.bank.id,
        )
        self.assertEqual(entry.source_account_id, self.cash.id)
        self.assertEqual(entry.dest_account_id, self.bank.id)

        edited = edit_cash_book_entry(
            self.db,
            entry.id,
            company_id=1,
            expected_version=entry.version,
            entry_type=CashBookEntryType.transfer,
            category_id=self.transfer.id,
            amount=Decimal("30"),
            description="Move2",
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.bank,
            source_bank_account_id=self.bank.id,
            dest_payment_mode=CashBookSourceMode.cash,
            dest_bank_account_id=None,
        )
        self.assertEqual(edited.source_account_id, self.bank.id)
        self.assertEqual(edited.dest_account_id, self.cash.id)
        self.assertEqual(edited.source_bank_account_id, self.bank.id)

    def test_payment_dual_write_cash_and_bank(self):
        cash_pay = create_payment(
            self.db,
            self.bill.id,
            Decimal("100"),
            PaymentMode.cash,
            expected_version=1,
            company_id=1,
        )
        self.assertIsNone(cash_pay.bank_account_id)
        self.assertEqual(cash_pay.account_id, self.cash.id)

        self.db.refresh(self.bill)
        bank_pay = create_payment(
            self.db,
            self.bill.id,
            Decimal("200"),
            PaymentMode.bank,
            expected_version=self.bill.version,
            bank_account_id=self.bank.id,
            company_id=1,
        )
        self.assertEqual(bank_pay.bank_account_id, self.bank.id)
        self.assertEqual(bank_pay.account_id, self.bank.id)

    def test_backfill_sql_rules_on_sqlite(self):
        """Simulate migration backfill rules against SQLite rows written without account_id."""
        legacy = CashBookEntry(
            company_id=1,
            entry_type=CashBookEntryType.expense,
            category_id=self.rent.id,
            amount=Decimal("10"),
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            entry_date=date(2026, 1, 1),
            entry_at=date(2026, 1, 1).isoformat(),
            version=1,
        )
        legacy.entry_at = utc_now()
        self.db.add(legacy)
        legacy_bank = CashBookEntry(
            company_id=1,
            entry_type=CashBookEntryType.expense,
            category_id=self.rent.id,
            amount=Decimal("15"),
            source_payment_mode=CashBookSourceMode.bank,
            source_bank_account_id=self.bank.id,
            entry_date=date(2026, 1, 2),
            entry_at=utc_now(),
            version=1,
        )
        self.db.add(legacy_bank)
        legacy_pay = Payment(
            bill_id=self.bill.id,
            amount=Decimal("5"),
            payment_mode=PaymentMode.cash,
            paid_at=utc_now(),
        )
        self.db.add(legacy_pay)
        self.db.commit()

        self.db.execute(
            text(
                "UPDATE cash_book_entries "
                "SET source_account_id = source_bank_account_id "
                "WHERE source_payment_mode = 'bank' AND source_bank_account_id IS NOT NULL"
            )
        )
        self.db.execute(
            text(
                "UPDATE cash_book_entries "
                "SET source_account_id = ("
                "  SELECT ba.id FROM bank_accounts ba "
                "  WHERE ba.company_id = cash_book_entries.company_id AND ba.kind = 'cash' "
                "  LIMIT 1"
                ") "
                "WHERE source_payment_mode = 'cash' AND source_account_id IS NULL"
            )
        )
        self.db.execute(
            text(
                "UPDATE payments "
                "SET account_id = ("
                "  SELECT ba.id FROM bank_accounts ba "
                "  JOIN bills b ON b.id = payments.bill_id "
                "  WHERE ba.company_id = b.company_id AND ba.kind = 'cash' "
                "  LIMIT 1"
                ") "
                "WHERE payment_mode = 'cash' AND account_id IS NULL"
            )
        )
        self.db.commit()

        self.db.refresh(legacy)
        self.db.refresh(legacy_bank)
        self.db.refresh(legacy_pay)
        self.assertEqual(legacy.source_account_id, self.cash.id)
        self.assertEqual(legacy_bank.source_account_id, self.bank.id)
        self.assertEqual(legacy_pay.account_id, self.cash.id)


if __name__ == "__main__":
    unittest.main()
