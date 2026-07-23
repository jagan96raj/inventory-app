"""Spec v17.2.2 Phase 5 — money-account balances via unified account_id FKs."""
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
    BookSettings,
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
from app.services.accounts import (
    get_account_balance,
    get_cash_balance,
    get_bank_account_balance,
    get_total_bank_balance,
)
from app.services.bank_accounts import seed_company_cash_account
from app.services.cash_book import create_cash_book_entry
from app.services.payments import create_payment
from app.utils.time import utc_now
from tests.idempotency_helpers import ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class MoneyAccountBalancesV1722Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.db.add(
            BookSettings(
                company_id=1,
                cash_opening_balance=Decimal("10000"),
                cash_opening_balance_at=date(2026, 1, 1),
            )
        )
        self.cash = seed_company_cash_account(
            self.db,
            1,
            opening_balance=Decimal("10000"),
            opening_balance_at=date(2026, 1, 1),
        )
        self.bank = BankAccount(
            company_id=1,
            name="HDFC",
            kind=BankAccountKind.bank,
            opening_balance=Decimal("5000"),
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
            [self.bank, self.location, self.customer, self.rent, self.transfer]
        )
        self.db.flush()
        self.sales = Bill(
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
        self.purchase = Bill(
            company_id=1,
            bill_number="P-000001",
            bill_type=BillType.purchase,
            status=BillStatus.finalized,
            bill_date=date(2026, 1, 11),
            customer_id=self.customer.id,
            location_id=self.location.id,
            subtotal=Decimal("800"),
            grand_total=Decimal("800"),
            amount_paid=Decimal("0"),
            payment_status=PaymentStatus.unpaid,
            version=1,
        )
        self.db.add_all([self.sales, self.purchase])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_parity_after_sales_cash_bank_transfer_expense(self):
        create_payment(
            self.db,
            self.sales.id,
            Decimal("400"),
            PaymentMode.cash,
            expected_version=1,
            company_id=1,
        )
        self.db.refresh(self.sales)
        create_payment(
            self.db,
            self.sales.id,
            Decimal("300"),
            PaymentMode.bank,
            expected_version=self.sales.version,
            account_id=self.bank.id,
            company_id=1,
        )
        create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.transfer,
            category_id=self.transfer.id,
            amount=Decimal("250"),
            description="Cash to bank",
            reference_no=None,
            bill_id=None,
            source_account_id=self.cash.id,
            dest_account_id=self.bank.id,
        )
        create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.expense,
            category_id=self.rent.id,
            amount=Decimal("150"),
            description="Rent",
            reference_no=None,
            bill_id=None,
            source_account_id=self.cash.id,
        )
        # Explicit expected values:
        # cash: 10000 + 400 - 250 - 150 = 10000
        # bank: 5000 + 300 + 250 = 5550
        self.assertEqual(get_cash_balance(self.db), Decimal("10000.00"))
        self.assertEqual(get_bank_account_balance(self.db, self.bank.id), Decimal("5550.00"))
        self.assertEqual(get_total_bank_balance(self.db), Decimal("5550.00"))
        # get_account_balance matches
        self.assertEqual(get_account_balance(self.db, self.cash.id), Decimal("10000.00"))
        self.assertEqual(get_account_balance(self.db, self.bank.id), Decimal("5550.00"))

    def test_purchase_payment_decreases_account_balance(self):
        create_payment(
            self.db,
            self.purchase.id,
            Decimal("200"),
            PaymentMode.bank,
            expected_version=1,
            account_id=self.bank.id,
            company_id=1,
        )
        self.assertEqual(get_bank_account_balance(self.db, self.bank.id), Decimal("4800.00"))

    def test_income_entry_increases_cash(self):
        income_cat = ExpenseCategory(
            company_id=1, name="Capital", kind=ExpenseCategoryKind.income, is_system=False
        )
        self.db.add(income_cat)
        self.db.commit()
        create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.income,
            category_id=income_cat.id,
            amount=Decimal("500"),
            description="Capital in",
            reference_no=None,
            bill_id=None,
            source_account_id=self.cash.id,
        )
        self.assertEqual(get_cash_balance(self.db), Decimal("10500.00"))

    def test_transfer_bank_to_cash_updates_both(self):
        create_cash_book_entry(
            self.db,
            company_id=1,
            entry_type=CashBookEntryType.transfer,
            category_id=self.transfer.id,
            amount=Decimal("1000"),
            description="Bank to cash",
            reference_no=None,
            bill_id=None,
            source_account_id=self.bank.id,
            dest_account_id=self.cash.id,
        )
        self.assertEqual(get_cash_balance(self.db), Decimal("11000.00"))
        self.assertEqual(get_bank_account_balance(self.db, self.bank.id), Decimal("4000.00"))


if __name__ == "__main__":
    unittest.main()
