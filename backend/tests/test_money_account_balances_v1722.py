"""Spec v17.2.2 Phase 3 — money-account balances match legacy formulas."""
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, create_engine, func, select
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
    CashBookSourceMode,
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


def _legacy_cash_balance(db: Session, company_id: int = 1) -> Decimal:
    """Pre-Phase-3 formula (book_settings + mode=cash movements)."""
    settings = db.scalar(select(BookSettings).where(BookSettings.company_id == company_id))
    opening = Decimal(settings.cash_opening_balance) if settings else Decimal("0")
    sales_in_expr = case(
        (
            and_(Bill.bill_type == BillType.sales, Payment.payment_mode == PaymentMode.cash),
            Payment.amount,
        ),
        else_=Decimal("0"),
    )
    purchase_out_expr = case(
        (
            and_(
                Bill.bill_type == BillType.purchase,
                Payment.payment_mode == PaymentMode.cash,
            ),
            Payment.amount,
        ),
        else_=Decimal("0"),
    )
    row = db.execute(
        select(
            func.coalesce(func.sum(sales_in_expr), 0),
            func.coalesce(func.sum(purchase_out_expr), 0),
        )
        .select_from(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(Payment.voided_at.is_(None), Bill.company_id == company_id)
    ).one()
    sales_in = Decimal(str(row[0] or 0))
    purchase_out = Decimal(str(row[1] or 0))

    income_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.income,
                CashBookEntry.source_payment_mode == CashBookSourceMode.cash,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    expense_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.expense,
                CashBookEntry.source_payment_mode == CashBookSourceMode.cash,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                CashBookEntry.dest_payment_mode == CashBookSourceMode.cash,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                CashBookEntry.source_payment_mode == CashBookSourceMode.cash,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    row2 = db.execute(
        select(
            func.coalesce(func.sum(income_in_expr), 0),
            func.coalesce(func.sum(expense_out_expr), 0),
            func.coalesce(func.sum(transfer_in_expr), 0),
            func.coalesce(func.sum(transfer_out_expr), 0),
        ).where(CashBookEntry.voided_at.is_(None), CashBookEntry.company_id == company_id)
    ).one()
    total = (
        opening
        + sales_in
        - purchase_out
        + Decimal(str(row2[0] or 0))
        - Decimal(str(row2[1] or 0))
        + Decimal(str(row2[2] or 0))
        - Decimal(str(row2[3] or 0))
    )
    return total.quantize(Decimal("0.01"))


def _legacy_bank_balance(db: Session, bank_account_id: int, company_id: int = 1) -> Decimal:
    bank = db.get(BankAccount, bank_account_id)
    opening = Decimal(bank.opening_balance)
    sales_in_expr = case(
        (
            and_(
                Bill.bill_type == BillType.sales,
                Payment.payment_mode == PaymentMode.bank,
                Payment.bank_account_id == bank_account_id,
            ),
            Payment.amount,
        ),
        else_=Decimal("0"),
    )
    purchase_out_expr = case(
        (
            and_(
                Bill.bill_type == BillType.purchase,
                Payment.payment_mode == PaymentMode.bank,
                Payment.bank_account_id == bank_account_id,
            ),
            Payment.amount,
        ),
        else_=Decimal("0"),
    )
    row = db.execute(
        select(
            func.coalesce(func.sum(sales_in_expr), 0),
            func.coalesce(func.sum(purchase_out_expr), 0),
        )
        .select_from(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(Payment.voided_at.is_(None), Bill.company_id == company_id)
    ).one()
    income_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.income,
                CashBookEntry.source_payment_mode == CashBookSourceMode.bank,
                CashBookEntry.source_bank_account_id == bank_account_id,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    expense_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.expense,
                CashBookEntry.source_payment_mode == CashBookSourceMode.bank,
                CashBookEntry.source_bank_account_id == bank_account_id,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                CashBookEntry.dest_payment_mode == CashBookSourceMode.bank,
                CashBookEntry.dest_bank_account_id == bank_account_id,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                CashBookEntry.source_payment_mode == CashBookSourceMode.bank,
                CashBookEntry.source_bank_account_id == bank_account_id,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    row2 = db.execute(
        select(
            func.coalesce(func.sum(income_in_expr), 0),
            func.coalesce(func.sum(expense_out_expr), 0),
            func.coalesce(func.sum(transfer_in_expr), 0),
            func.coalesce(func.sum(transfer_out_expr), 0),
        ).where(CashBookEntry.voided_at.is_(None), CashBookEntry.company_id == company_id)
    ).one()
    total = (
        opening
        + Decimal(str(row[0] or 0))
        - Decimal(str(row[1] or 0))
        + Decimal(str(row2[0] or 0))
        - Decimal(str(row2[1] or 0))
        + Decimal(str(row2[2] or 0))
        - Decimal(str(row2[3] or 0))
    )
    return total.quantize(Decimal("0.01"))


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

    def _assert_parity(self):
        new_cash = get_cash_balance(self.db, company_id=1)
        legacy_cash = _legacy_cash_balance(self.db, 1)
        self.assertEqual(new_cash, legacy_cash)
        self.assertEqual(
            get_account_balance(self.db, self.cash.id),
            legacy_cash,
        )
        new_bank = get_bank_account_balance(self.db, self.bank.id, company_id=1)
        legacy_bank = _legacy_bank_balance(self.db, self.bank.id, 1)
        self.assertEqual(new_bank, legacy_bank)
        self.assertEqual(get_account_balance(self.db, self.bank.id), legacy_bank)

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
            bank_account_id=self.bank.id,
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
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=CashBookSourceMode.bank,
            dest_bank_account_id=self.bank.id,
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
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        self._assert_parity()
        # Explicit expected values from the shared formula:
        # cash: 10000 + 400 - 250 - 150 = 10000
        # bank: 5000 + 300 + 250 = 5550
        self.assertEqual(get_cash_balance(self.db), Decimal("10000.00"))
        self.assertEqual(get_bank_account_balance(self.db, self.bank.id), Decimal("5550.00"))
        self.assertEqual(get_total_bank_balance(self.db), Decimal("5550.00"))

    def test_parity_legacy_only_rows_without_account_id(self):
        """Rows with null unified FKs still count via legacy fallback."""
        legacy_pay = Payment(
            bill_id=self.sales.id,
            amount=Decimal("100"),
            payment_mode=PaymentMode.cash,
            paid_at=utc_now(),
            account_id=None,
            bank_account_id=None,
        )
        legacy_exp = CashBookEntry(
            company_id=1,
            entry_type=CashBookEntryType.expense,
            category_id=self.rent.id,
            amount=Decimal("40"),
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            source_account_id=None,
            entry_date=date(2026, 1, 12),
            entry_at=utc_now(),
            version=1,
        )
        self.db.add_all([legacy_pay, legacy_exp])
        self.db.commit()
        self._assert_parity()
        self.assertEqual(get_cash_balance(self.db), Decimal("10060.00"))


if __name__ == "__main__":
    unittest.main()
