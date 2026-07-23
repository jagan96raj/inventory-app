"""Spec v17.2.4 Phase 5 — money account_id is the primary FK on Payment and CashBookEntry."""
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
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
    Customer,
    ExpenseCategory,
    ExpenseCategoryKind,
    Location,
    Payment,
    PaymentMode,
    PaymentStatus,
)
from app.utils.time import utc_now
from app.services.bank_accounts import seed_company_cash_account
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

    def test_cash_book_expense_cash_sets_source_account_id(self):
        entry = create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.expense,
            category_id=self.rent.id,
            amount=Decimal("50"),
            description="Rent",
            reference_no=None,
            bill_id=None,
            source_account_id=self.cash.id,
        )
        self.assertEqual(entry.source_account_id, self.cash.id)
        self.assertIsNone(entry.dest_account_id)

    def test_cash_book_transfer_and_edit(self):
        entry = create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.transfer,
            category_id=self.transfer.id,
            amount=Decimal("25"),
            description="Move",
            reference_no=None,
            bill_id=None,
            source_account_id=self.cash.id,
            dest_account_id=self.bank.id,
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
            source_account_id=self.bank.id,
            dest_account_id=self.cash.id,
        )
        self.assertEqual(edited.source_account_id, self.bank.id)
        self.assertEqual(edited.dest_account_id, self.cash.id)

    def test_payment_cash_and_bank_account_id(self):
        cash_pay = create_payment(
            self.db,
            self.bill.id,
            Decimal("100"),
            PaymentMode.cash,
            expected_version=1,
            company_id=1,
        )
        self.assertEqual(cash_pay.account_id, self.cash.id)

        self.db.refresh(self.bill)
        bank_pay = create_payment(
            self.db,
            self.bill.id,
            Decimal("200"),
            PaymentMode.bank,
            expected_version=self.bill.version,
            account_id=self.bank.id,
            company_id=1,
        )
        self.assertEqual(bank_pay.account_id, self.bank.id)

    def test_cash_book_expense_bank_sets_source_account_id(self):
        entry = create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.expense,
            category_id=self.rent.id,
            amount=Decimal("15"),
            description="Bank expense",
            reference_no=None,
            bill_id=None,
            source_account_id=self.bank.id,
        )
        self.assertEqual(entry.source_account_id, self.bank.id)
        self.assertIsNone(entry.dest_account_id)

    def test_transfer_rejects_same_bank_account(self):
        with self.assertRaises(ValueError):
            create_cash_book_entry(
                self.db,
                company_id=1,
                entry_type=CashBookEntryType.transfer,
                category_id=self.transfer.id,
                amount=Decimal("10"),
                description="Same",
                reference_no=None,
                bill_id=None,
                source_account_id=self.bank.id,
                dest_account_id=self.bank.id,
            )

    def test_expense_rejects_dest_account(self):
        with self.assertRaises(ValueError):
            create_cash_book_entry(
                self.db,
                company_id=1,
                entry_type=CashBookEntryType.expense,
                category_id=self.rent.id,
                amount=Decimal("10"),
                description="Bad",
                reference_no=None,
                bill_id=None,
                source_account_id=self.cash.id,
                dest_account_id=self.bank.id,
            )


if __name__ == "__main__":
    unittest.main()
