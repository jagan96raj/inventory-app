"""Spec v12.21 — Accounts, Cash Book & Multi-Bank tests."""
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    BankAccount,
    Bill,
    BillType,
    BookSettings,
    Brand,
    CashBookEntry,
    CashBookEntryType,
    CashBookSourceMode,
    Customer,
    ExpenseCategory,
    ExpenseCategoryKind,
    Company,
    Location,
    Payment,
    PaymentMode,
    Product,
    User,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
from app.services.accounts import (
    get_accounts_summary,
    get_bank_account_balance,
    get_cash_balance,
    get_customer_statement,
)
from app.services.bank_accounts import (
    create_bank_account,
    delete_bank_account,
    edit_bank_account,
    make_default_bank_account,
)
from app.services.cash_book import (
    create_cash_book_entry,
    edit_cash_book_entry,
    void_cash_book_entry,
)
from app.services.expense_categories import create_category, delete_category, edit_category
from app.services.payments import create_payment, void_payment
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_kwargs, idem_void_headers


IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
EXPECTED_CASH_BOOK_VERSION_HEADER = "X-Expected-Cash-Book-Version"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed_masters(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="Acme")
    db.add_all([product, brand, location, bag_type, customer])
    db.flush()
    # cash book singleton
    if db.get(BookSettings, 1) is None:
        db.add(BookSettings(id=1, company_id=1, cash_opening_balance=Decimal("0"), cash_opening_balance_at=date.today()))
    # categories
    cats = {
        ("Freight Charges", ExpenseCategoryKind.expense, False),
        ("Rent", ExpenseCategoryKind.expense, False),
        ("Capital Increase", ExpenseCategoryKind.income, False),
        ("Cash <-> Bank Transfer", ExpenseCategoryKind.transfer, True),
    }
    out_cats: dict[str, ExpenseCategory] = {}
    for name, kind, is_system in cats:
        ec = ExpenseCategory(name=name, kind=kind, is_system=is_system, is_active=True)
        db.add(ec)
        db.flush()
        out_cats[name] = ec
    # banks
    bank_default = BankAccount(
        name="Default Bank",
        opening_balance=Decimal("0"),
        opening_balance_at=date.today(),
        is_default=True,
        is_active=True,
    )
    bank_secondary = BankAccount(
        name="Secondary Bank",
        opening_balance=Decimal("0"),
        opening_balance_at=date.today(),
        is_default=False,
        is_active=True,
    )
    db.add_all([bank_default, bank_secondary])
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "customer": customer,
        "freight": out_cats["Freight Charges"],
        "rent": out_cats["Rent"],
        "capital": out_cats["Capital Increase"],
        "transfer": out_cats["Cash <-> Bank Transfer"],
        "bank_default": bank_default,
        "bank_secondary": bank_secondary,
    }


def _make_sales_bill(db: Session, m: dict, *, grand_total: Decimal) -> Bill:
    rate = grand_total / Decimal("50")
    schema = BillFinalizeCreate(
        bill_type=BillType.sales,
        customer_id=m["customer"].id,
        location_id=m["location"].id,
        lines=[
            BillLineIn(
                product_id=m["product"].id,
                brand_id=m["brand"].id,
                bag_type_id=m["bag_type"].id,
                ordered_bags=1,
                ordered_loose_kg=Decimal("0"),
                rate_per_kg=rate.quantize(Decimal("0.01")),
            )
        ],
    )
    bill_out = create_finalized_bill(schema, db=db, **idem_kwargs())
    bill = db.get(Bill, bill_out.id)
    assert bill is not None
    return bill


def _make_purchase_bill(db: Session, m: dict, *, grand_total: Decimal) -> Bill:
    rate = grand_total / Decimal("50")
    schema = BillFinalizeCreate(
        bill_type=BillType.purchase,
        customer_id=m["customer"].id,
        lines=[
            BillLineIn(
                product_id=m["product"].id,
                brand_id=m["brand"].id,
                bag_type_id=m["bag_type"].id,
                ordered_bags=1,
                ordered_loose_kg=Decimal("0"),
                rate_per_kg=rate.quantize(Decimal("0.01")),
            )
        ],
    )
    bill_out = create_finalized_bill(schema, db=db, **idem_kwargs())
    bill = db.get(Bill, bill_out.id)
    assert bill is not None
    return bill


# ---------------------------------------------------------------------------
# Bank Accounts service
# ---------------------------------------------------------------------------


class BankAccountServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def test_only_one_default_at_a_time(self):
        new_bank = create_bank_account(
            self.db,
            name="ICICI Current",
            account_number_last4="1234",
            ifsc=None,
            opening_balance=Decimal("0"),
            is_default=True,
        )
        defaults = list(self.db.scalars(select(BankAccount).where(BankAccount.is_default.is_(True))))
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0].id, new_bank.id)

    def test_make_default_atomically_flips_previous(self):
        first = self.m["bank_default"]
        second = self.m["bank_secondary"]
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)
        make_default_bank_account(self.db, second.id)
        self.db.refresh(first)
        self.db.refresh(second)
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        defaults = list(self.db.scalars(select(BankAccount).where(BankAccount.is_default.is_(True))))
        self.assertEqual(len(defaults), 1)

    def test_cannot_delete_bank_used_by_payment(self):
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("1000"))
        create_payment(
            self.db,
            bill.id,
            Decimal("500"),
            PaymentMode.bank,
            expected_version=bill.version,
            bank_account_id=self.m["bank_secondary"].id,
        )
        with self.assertRaises(ValueError) as ctx:
            delete_bank_account(self.db, self.m["bank_secondary"].id)
        self.assertIn("in use", str(ctx.exception).lower())

    def test_cannot_delete_default_bank(self):
        with self.assertRaises(ValueError):
            delete_bank_account(self.db, self.m["bank_default"].id)

    def test_soft_delete_unused_bank(self):
        new_bank = create_bank_account(
            self.db, name="Unused", account_number_last4=None, ifsc=None,
            opening_balance=Decimal("0"), is_default=False,
        )
        delete_bank_account(self.db, new_bank.id)
        self.db.refresh(new_bank)
        self.assertFalse(new_bank.is_active)

    def test_edit_name_unique(self):
        edit_bank_account(self.db, self.m["bank_secondary"].id, name="Renamed", account_number_last4=None, ifsc=None, is_active=None)
        with self.assertRaises(ValueError):
            edit_bank_account(self.db, self.m["bank_secondary"].id, name="Default Bank", account_number_last4=None, ifsc=None, is_active=None)


# ---------------------------------------------------------------------------
# Expense Categories service
# ---------------------------------------------------------------------------


class ExpenseCategoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def test_create_expense_or_income(self):
        e = create_category(self.db, name="Stationery", kind=ExpenseCategoryKind.expense)
        self.assertFalse(e.is_system)
        i = create_category(self.db, name="Refund Received", kind=ExpenseCategoryKind.income)
        self.assertEqual(i.kind, ExpenseCategoryKind.income)

    def test_reject_creating_transfer_kind(self):
        with self.assertRaises(ValueError):
            create_category(self.db, name="Bad Transfer", kind=ExpenseCategoryKind.transfer)

    def test_active_name_unique_per_company_not_globally(self):
        company2 = Company(name="Other Co", is_active=True)
        self.db.add(company2)
        self.db.flush()
        # Company 1 already has active "Rent" from seed; company 2 may use the same name.
        rent_other = create_category(
            self.db, company_id=company2.id, name="Rent", kind=ExpenseCategoryKind.expense
        )
        self.assertEqual(rent_other.company_id, company2.id)
        with self.assertRaises(ValueError):
            create_category(self.db, company_id=1, name=" rent ", kind=ExpenseCategoryKind.expense)

    def test_cannot_edit_or_delete_system_row(self):
        with self.assertRaises(ValueError):
            edit_category(self.db, self.m["transfer"].id, name="Hacked", is_active=None)
        with self.assertRaises(ValueError):
            delete_category(self.db, self.m["transfer"].id)

    def test_cannot_delete_category_in_use(self):
        create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["rent"].id,
            amount=Decimal("1000"),
            description=None,
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        with self.assertRaises(ValueError):
            delete_category(self.db, self.m["rent"].id)


# ---------------------------------------------------------------------------
# Cash Book CRUD + balance derivation
# ---------------------------------------------------------------------------


class CashBookServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)
        # seed cash opening balance to 10000
        settings = self.db.get(BookSettings, 1)
        assert settings is not None
        settings.cash_opening_balance = Decimal("10000")
        # bank seed balance
        self.m["bank_default"].opening_balance = Decimal("5000")
        self.m["bank_secondary"].opening_balance = Decimal("3000")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_expense_cash_decreases_cash(self):
        create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["rent"].id,
            amount=Decimal("1000"),
            description="Monthly rent",
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        self.assertEqual(get_cash_balance(self.db), Decimal("9000.00"))

    def test_expense_bank_decreases_that_bank(self):
        create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["rent"].id,
            amount=Decimal("500"),
            description=None,
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.bank,
            source_bank_account_id=self.m["bank_default"].id,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        self.assertEqual(get_cash_balance(self.db), Decimal("10000.00"))
        self.assertEqual(
            get_bank_account_balance(self.db, self.m["bank_default"].id), Decimal("4500.00")
        )
        self.assertEqual(
            get_bank_account_balance(self.db, self.m["bank_secondary"].id), Decimal("3000.00")
        )

    def test_income_increases_destination(self):
        create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.income,
            category_id=self.m["capital"].id,
            amount=Decimal("2500"),
            description=None,
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        self.assertEqual(get_cash_balance(self.db), Decimal("12500.00"))

    def test_transfer_cash_to_bank(self):
        create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.transfer,
            category_id=self.m["transfer"].id,
            amount=Decimal("1000"),
            description=None,
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=CashBookSourceMode.bank,
            dest_bank_account_id=self.m["bank_default"].id,
        )
        self.assertEqual(get_cash_balance(self.db), Decimal("9000.00"))
        self.assertEqual(get_bank_account_balance(self.db, self.m["bank_default"].id), Decimal("6000.00"))

    def test_transfer_between_banks(self):
        create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.transfer,
            category_id=self.m["transfer"].id,
            amount=Decimal("1000"),
            description=None,
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.bank,
            source_bank_account_id=self.m["bank_default"].id,
            dest_payment_mode=CashBookSourceMode.bank,
            dest_bank_account_id=self.m["bank_secondary"].id,
        )
        self.assertEqual(get_bank_account_balance(self.db, self.m["bank_default"].id), Decimal("4000.00"))
        self.assertEqual(get_bank_account_balance(self.db, self.m["bank_secondary"].id), Decimal("4000.00"))

    def test_edit_with_correct_version_succeeds_wrong_409(self):
        entry = create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["rent"].id,
            amount=Decimal("1000"),
            description=None,
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        original_version = entry.version
        entry_id = entry.id
        edited = edit_cash_book_entry(
            self.db,
            entry_id,
            expected_version=original_version,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["rent"].id,
            amount=Decimal("2000"),
            description=None,
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        self.assertEqual(edited.version, original_version + 1)
        self.assertEqual(get_cash_balance(self.db), Decimal("8000.00"))
        with self.assertRaises(ValueError):
            edit_cash_book_entry(
                self.db,
                entry_id,
                expected_version=original_version,  # stale
                entry_type=CashBookEntryType.expense,
                category_id=self.m["rent"].id,
                amount=Decimal("3000"),
                description=None,
                reference_no=None,
                bill_id=None,
                source_payment_mode=CashBookSourceMode.cash,
                source_bank_account_id=None,
                dest_payment_mode=None,
                dest_bank_account_id=None,
            )

    def test_void_reverses_balance(self):
        entry = create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["rent"].id,
            amount=Decimal("1500"),
            description=None,
            reference_no=None,
            bill_id=None,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        self.assertEqual(get_cash_balance(self.db), Decimal("8500.00"))
        voided = void_cash_book_entry(self.db, entry.id, expected_version=entry.version)
        self.assertIsNotNone(voided.voided_at)
        self.assertEqual(get_cash_balance(self.db), Decimal("10000.00"))
        with self.assertRaises(ValueError):
            void_cash_book_entry(self.db, entry.id, expected_version=voided.version)


# ---------------------------------------------------------------------------
# Payments (multi-bank)
# ---------------------------------------------------------------------------


class MultiBankPaymentTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)
        settings = self.db.get(BookSettings, 1)
        assert settings is not None
        settings.cash_opening_balance = Decimal("0")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_bank_payment_to_specific_account_updates_only_that_balance(self):
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("1000"))
        create_payment(
            self.db,
            bill.id,
            Decimal("1000"),
            PaymentMode.bank,
            expected_version=bill.version,
            bank_account_id=self.m["bank_secondary"].id,
        )
        self.assertEqual(get_bank_account_balance(self.db, self.m["bank_secondary"].id), Decimal("1000.00"))
        self.assertEqual(get_bank_account_balance(self.db, self.m["bank_default"].id), Decimal("0.00"))

    def test_cash_sales_payment_increases_cash(self):
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("500"))
        create_payment(self.db, bill.id, Decimal("500"), PaymentMode.cash, expected_version=bill.version)
        self.assertEqual(get_cash_balance(self.db), Decimal("500.00"))

    def test_cash_purchase_payment_decreases_cash(self):
        # seed cash so a payment can occur
        settings = self.db.get(BookSettings, 1)
        assert settings is not None
        settings.cash_opening_balance = Decimal("1000")
        self.db.commit()
        bill = _make_purchase_bill(self.db, self.m, grand_total=Decimal("500"))
        create_payment(self.db, bill.id, Decimal("500"), PaymentMode.cash, expected_version=bill.version)
        self.assertEqual(get_cash_balance(self.db), Decimal("500.00"))

    def test_void_payment_reverses_balance(self):
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("1000"))
        pay = create_payment(
            self.db,
            bill.id,
            Decimal("1000"),
            PaymentMode.bank,
            expected_version=bill.version,
            bank_account_id=self.m["bank_default"].id,
        )
        self.assertEqual(get_bank_account_balance(self.db, self.m["bank_default"].id), Decimal("1000.00"))
        self.db.refresh(bill)
        void_payment(self.db, pay.id, expected_version=bill.version)
        self.assertEqual(get_bank_account_balance(self.db, self.m["bank_default"].id), Decimal("0.00"))

    def test_reject_bank_payment_without_default_when_id_missing(self):
        # remove default
        self.m["bank_default"].is_default = False
        self.db.commit()
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("1000"))
        with self.assertRaises(ValueError):
            create_payment(
                self.db,
                bill.id,
                Decimal("500"),
                PaymentMode.bank,
                expected_version=bill.version,
                bank_account_id=None,
            )

    def test_reject_cash_payment_with_bank_id(self):
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("1000"))
        with self.assertRaises(ValueError):
            create_payment(
                self.db,
                bill.id,
                Decimal("500"),
                PaymentMode.cash,
                expected_version=bill.version,
                bank_account_id=self.m["bank_default"].id,
            )


# ---------------------------------------------------------------------------
# Bill linkage
# ---------------------------------------------------------------------------


class BillLinkageTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)
        settings = self.db.get(BookSettings, 1)
        assert settings is not None
        settings.cash_opening_balance = Decimal("5000")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_link_expense_to_bill_persists(self):
        bill = _make_purchase_bill(self.db, self.m, grand_total=Decimal("2000"))
        entry = create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["freight"].id,
            amount=Decimal("250"),
            description="Lorry freight",
            reference_no="VOUCHER-1",
            bill_id=bill.id,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        self.assertEqual(entry.bill_id, bill.id)
        rows = list(
            self.db.scalars(
                select(CashBookEntry).where(CashBookEntry.bill_id == bill.id)
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, entry.id)


# ---------------------------------------------------------------------------
# Accounts dashboard + customer statement
# ---------------------------------------------------------------------------


class AccountsSummaryTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)
        settings = self.db.get(BookSettings, 1)
        assert settings is not None
        settings.cash_opening_balance = Decimal("1000")
        self.m["bank_default"].opening_balance = Decimal("2000")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_summary_aggregates(self):
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("500"))
        create_payment(self.db, bill.id, Decimal("500"), PaymentMode.cash, expected_version=bill.version)
        summary = get_accounts_summary(self.db)
        self.assertEqual(summary["cash_balance"], Decimal("1500.00"))
        self.assertEqual(summary["total_bank_balance"], Decimal("2000.00"))
        self.assertEqual(summary["total_money"], Decimal("3500.00"))
        self.assertGreaterEqual(len(summary["bank_accounts"]), 1)

    def test_customer_statement_running_balance(self):
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("1000"))
        create_payment(self.db, bill.id, Decimal("400"), PaymentMode.cash, expected_version=bill.version)
        statement = get_customer_statement(
            self.db, self.m["customer"].id, date_from=None, date_to=None, limit=50, offset=0
        )
        kinds = [e["kind"] for e in statement["items"]]
        self.assertIn("bill_created", kinds)
        self.assertIn("payment_received", kinds)
        bill_event = next(e for e in statement["items"] if e["kind"] == "bill_created")
        payment_event = next(e for e in statement["items"] if e["kind"] == "payment_received")
        # sales bill creates a 1000 debit; payment of 400 reduces the debit balance
        self.assertEqual(Decimal(bill_event["debit_amount"]), Decimal("1000"))
        self.assertEqual(Decimal(payment_event["credit_amount"]), Decimal("400"))
        # the final (most-recent) running balance is the latest entry
        last = statement["items"][-1]
        self.assertEqual(Decimal(last["running_balance"]), Decimal("600.00"))


# ---------------------------------------------------------------------------
# Cash book API: idempotency + version + endpoints
# ---------------------------------------------------------------------------


class CashBookApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        self.db = _make_session()
        self.m = _seed_masters(self.db)
        settings = self.db.get(BookSettings, 1)
        assert settings is not None
        settings.cash_opening_balance = Decimal("5000")
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _body(self) -> dict:
        return {
            "entry_type": "expense",
            "category_id": self.m["rent"].id,
            "amount": "1500",
            "description": "Rent",
            "reference_no": None,
            "bill_id": None,
            "source_payment_mode": "cash",
            "source_bank_account_id": None,
            "dest_payment_mode": None,
            "dest_bank_account_id": None,
        }

    def test_post_requires_idempotency_key(self):
        res = self.client.post("/api/cashbook", json=self._body())
        self.assertEqual(res.status_code, 400)

    def test_post_idempotent_replay_returns_same_entry(self):
        key = str(uuid4())
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        r1 = self.client.post("/api/cashbook", json=self._body(), headers=headers)
        r2 = self.client.post("/api/cashbook", json=self._body(), headers=headers)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        count = self.db.scalar(select(func.count(CashBookEntry.id)))
        self.assertEqual(count, 1)

    def test_void_requires_authorization_password(self):
        key = str(uuid4())
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        created = self.client.post("/api/cashbook", json=self._body(), headers=headers).json()
        void_headers = {IDEMPOTENCY_KEY_HEADER: str(uuid4())}
        res = self.client.post(f"/api/cashbook/{created['id']}/void", headers=void_headers)
        self.assertEqual(res.status_code, 403)

    def test_void_requires_expected_version_header(self):
        key = str(uuid4())
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        created = self.client.post("/api/cashbook", json=self._body(), headers=headers).json()
        void_headers = idem_void_headers(str(uuid4()))
        res = self.client.post(f"/api/cashbook/{created['id']}/void", headers=void_headers)
        self.assertEqual(res.status_code, 400)

    def test_void_wrong_version_returns_409(self):
        key = str(uuid4())
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        created = self.client.post("/api/cashbook", json=self._body(), headers=headers).json()
        void_headers = idem_void_headers(str(uuid4())) | {EXPECTED_CASH_BOOK_VERSION_HEADER: "999"}
        res = self.client.post(f"/api/cashbook/{created['id']}/void", headers=void_headers)
        self.assertEqual(res.status_code, 409)

    def test_list_paginated_and_filtered(self):
        key1, key2 = str(uuid4()), str(uuid4())
        b1 = self._body() | {"amount": "100"}
        b2 = self._body() | {"amount": "200"}
        self.client.post("/api/cashbook", json=b1, headers={IDEMPOTENCY_KEY_HEADER: key1})
        self.client.post("/api/cashbook", json=b2, headers={IDEMPOTENCY_KEY_HEADER: key2})
        res = self.client.get("/api/cashbook?limit=10&offset=0")
        self.assertEqual(res.status_code, 200)
        page = res.json()
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["items"]), 2)


# ---------------------------------------------------------------------------
# Bill linked-entries + void-precheck API
# ---------------------------------------------------------------------------


class BillLinkedEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        self.db = _make_session()
        self.m = _seed_masters(self.db)
        settings = self.db.get(BookSettings, 1)
        assert settings is not None
        settings.cash_opening_balance = Decimal("5000")
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_linked_entries_returns_only_bill_entries(self):
        bill = _make_purchase_bill(self.db, self.m, grand_total=Decimal("1000"))
        entry = create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["freight"].id,
            amount=Decimal("300"),
            description="Freight",
            reference_no=None,
            bill_id=bill.id,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        res = self.client.get(f"/api/bills/{bill.id}/linked-entries?limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        page = res.json()
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["id"], entry.id)

    def test_void_precheck_returns_count_and_amount(self):
        bill = _make_purchase_bill(self.db, self.m, grand_total=Decimal("1000"))
        create_cash_book_entry(
            self.db,
            entry_type=CashBookEntryType.expense,
            category_id=self.m["freight"].id,
            amount=Decimal("300"),
            description="Freight",
            reference_no=None,
            bill_id=bill.id,
            source_payment_mode=CashBookSourceMode.cash,
            source_bank_account_id=None,
            dest_payment_mode=None,
            dest_bank_account_id=None,
        )
        res = self.client.get(f"/api/bills/{bill.id}/void-precheck")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["can_void"])
        self.assertTrue(any("cash-book" in r.lower() for r in data["block_reasons"]))
        self.assertEqual(data["linked_active_entries_count"], 1)
        self.assertEqual(Decimal(data["linked_active_entries_amount"]), Decimal("300"))


# ---------------------------------------------------------------------------
# Bank Accounts API + delete protections
# ---------------------------------------------------------------------------


class BankAccountsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        self.db = _make_session()
        self.m = _seed_masters(self.db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_make_default_endpoint_flips(self):
        key = str(uuid4())
        res = self.client.post(
            f"/api/bank-accounts/{self.m['bank_secondary'].id}/make-default",
            headers={IDEMPOTENCY_KEY_HEADER: key},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["is_default"])
        self.db.refresh(self.m["bank_default"])
        self.assertFalse(self.m["bank_default"].is_default)

    def test_delete_in_use_returns_409(self):
        bill = _make_sales_bill(self.db, self.m, grand_total=Decimal("1000"))
        create_payment(
            self.db,
            bill.id,
            Decimal("500"),
            PaymentMode.bank,
            expected_version=bill.version,
            bank_account_id=self.m["bank_secondary"].id,
        )
        res = self.client.delete(f"/api/bank-accounts/{self.m['bank_secondary'].id}")
        self.assertEqual(res.status_code, 409)


if __name__ == "__main__":
    unittest.main()
