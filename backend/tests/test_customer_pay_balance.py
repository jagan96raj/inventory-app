"""Spec v17.3.27 — customer Pay debit / Pay credit FIFO cash/bank."""
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.entities import (
    BankAccountKind,
    BillStatus,
    BillType,
    Payment,
    PaymentMode,
    PaymentStatus,
)
from app.services.payments import (
    CUSTOMER_PAY_NO_BALANCE_MSG,
    CUSTOMER_PAY_NO_OPEN_BILLS_MSG,
    CUSTOMER_PAY_OVER_CAP_MSG,
    allocate_setoff_fifo,
    pay_customer_balance,
    preview_customer_pay_balance,
)


def _customer(cid=1, name="Acme", credit="0", debit="0", company_id=1):
    return SimpleNamespace(
        id=cid,
        name=name,
        credit_balance=Decimal(credit),
        debit_balance=Decimal(debit),
        company_id=company_id,
    )


def _bill(bill_id, bill_type, customer, grand_total, bill_date_day=1, payments=None, bill_number=None):
    return SimpleNamespace(
        id=bill_id,
        bill_type=bill_type,
        status=BillStatus.finalized,
        grand_total=Decimal(grand_total),
        customer_id=customer.id,
        customer=customer,
        payments=payments or [],
        amount_paid=Decimal("0"),
        payment_status=PaymentStatus.unpaid,
        bill_number=bill_number or f"B{bill_id}",
        bill_date=date(2026, 1, bill_date_day),
        version=1,
        company_id=customer.company_id,
    )


def _cash_account(aid=10, company_id=1):
    return SimpleNamespace(
        id=aid,
        kind=BankAccountKind.cash,
        is_active=True,
        company_id=company_id,
        name="Cash",
    )


class FifoAllocationUnitTests(unittest.TestCase):
    def test_partial_pays_oldest_first(self):
        c = _customer(debit="10000")
        b1 = _bill(1, BillType.sales, c, "4000", bill_date_day=1)
        b2 = _bill(2, BillType.sales, c, "3000", bill_date_day=2)
        b3 = _bill(3, BillType.sales, c, "3000", bill_date_day=3)
        alloc = allocate_setoff_fifo(
            [(b1, Decimal("4000")), (b2, Decimal("3000")), (b3, Decimal("3000"))],
            Decimal("5000"),
        )
        self.assertEqual(alloc, [(1, Decimal("4000")), (2, Decimal("1000"))])


class PreviewCustomerPayBalanceTests(unittest.TestCase):
    @patch("app.services.payments.load_customer_bills_with_due")
    def test_preview_caps_and_fifo(self, mock_load):
        c = _customer(debit="10000")
        b1 = _bill(1, BillType.sales, c, "4000", bill_date_day=1)
        b2 = _bill(2, BillType.sales, c, "3000", bill_date_day=2)
        mock_load.return_value = [(b1, Decimal("4000")), (b2, Decimal("3000"))]
        db = MagicMock()
        db.scalar.return_value = c

        preview = preview_customer_pay_balance(db, 1, "debit", Decimal("5000"))
        self.assertEqual(preview["max_amount"], Decimal("7000"))
        self.assertEqual(preview["amount"], Decimal("5000"))
        self.assertEqual(
            [(a["bill_id"], a["amount"]) for a in preview["allocations"]],
            [(1, Decimal("4000")), (2, Decimal("1000"))],
        )


class PayCustomerBalanceTests(unittest.TestCase):
    def _mock_db(self, customer, open_bills, account):
        db = MagicMock()
        payment_id = [0]

        def scalar(stmt=None, **_kwargs):
            # Customer load vs account load — distinguish by call order via side_effect list
            return None

        # First scalar: customer; later scalars may be account or refresh paths
        scalar_returns = [customer, account]
        db.scalar.side_effect = lambda *a, **k: (
            scalar_returns.pop(0) if scalar_returns else customer
        )

        def add_obj(obj):
            if isinstance(obj, Payment):
                payment_id[0] += 1
                obj.id = payment_id[0]

        db.add.side_effect = add_obj
        return db, open_bills

    @patch("app.services.payments.lock_bills_for_update")
    @patch("app.services.payments.load_customer_bills_with_due")
    @patch("app.services.payments._resolve_money_account_id", return_value=10)
    def test_pay_debit_partial_fifo(self, _resolve, mock_load, _lock):
        customer = _customer(debit="10000")
        b1 = _bill(1, BillType.sales, customer, "4000", bill_date_day=1)
        b2 = _bill(2, BillType.sales, customer, "3000", bill_date_day=2)
        b3 = _bill(3, BillType.sales, customer, "3000", bill_date_day=3)
        open_bills = [
            (b1, Decimal("4000")),
            (b2, Decimal("3000")),
            (b3, Decimal("3000")),
        ]
        mock_load.return_value = open_bills
        account = _cash_account()
        db, _ = self._mock_db(customer, open_bills, account)

        result = pay_customer_balance(
            db, 1, "debit", Decimal("5000"), account_id=10, company_id=1
        )

        self.assertEqual(result["payments_created"], 2)
        self.assertEqual(result["direction"], "debit")
        self.assertEqual(
            [(a["bill_id"], a["amount"]) for a in result["allocations"]],
            [(1, Decimal("4000")), (2, Decimal("1000"))],
        )
        self.assertEqual(customer.debit_balance, Decimal("5000"))
        self.assertEqual(b1.payment_status, PaymentStatus.paid)
        self.assertEqual(b1.amount_paid, Decimal("4000"))
        self.assertEqual(b2.payment_status, PaymentStatus.partial)
        self.assertEqual(b2.amount_paid, Decimal("1000"))
        self.assertEqual(b3.payment_status, PaymentStatus.unpaid)
        db.commit.assert_called_once()

    @patch("app.services.payments.lock_bills_for_update")
    @patch("app.services.payments.load_customer_bills_with_due")
    @patch("app.services.payments._resolve_money_account_id", return_value=10)
    def test_pay_credit_reduces_credit(self, _resolve, mock_load, _lock):
        customer = _customer(credit="8000", debit="0")
        b1 = _bill(11, BillType.purchase, customer, "5000", bill_date_day=1)
        b2 = _bill(12, BillType.purchase, customer, "5000", bill_date_day=2)
        open_bills = [(b1, Decimal("5000")), (b2, Decimal("5000"))]
        mock_load.return_value = open_bills
        account = _cash_account()
        db, _ = self._mock_db(customer, open_bills, account)

        result = pay_customer_balance(
            db, 1, "credit", Decimal("5000"), account_id=10, company_id=1
        )

        self.assertEqual(result["payments_created"], 1)
        self.assertEqual(result["allocations"][0]["bill_id"], 11)
        self.assertEqual(customer.credit_balance, Decimal("3000"))
        self.assertEqual(b1.payment_status, PaymentStatus.paid)

    @patch("app.services.payments.lock_bills_for_update")
    @patch("app.services.payments.load_customer_bills_with_due")
    def test_rejects_over_cap(self, mock_load, _lock):
        customer = _customer(debit="2000")
        b1 = _bill(1, BillType.sales, customer, "5000")
        mock_load.return_value = [(b1, Decimal("5000"))]
        account = _cash_account()
        db, _ = self._mock_db(customer, [(b1, Decimal("5000"))], account)

        with self.assertRaises(ValueError) as ctx:
            pay_customer_balance(db, 1, "debit", Decimal("3000"), account_id=10, company_id=1)
        self.assertIn(CUSTOMER_PAY_OVER_CAP_MSG, str(ctx.exception))

    @patch("app.services.payments.load_customer_bills_with_due")
    def test_rejects_no_balance(self, mock_load):
        customer = _customer(debit="0")
        mock_load.return_value = []
        account = _cash_account()
        db, _ = self._mock_db(customer, [], account)

        with self.assertRaises(ValueError) as ctx:
            pay_customer_balance(db, 1, "debit", Decimal("100"), account_id=10, company_id=1)
        self.assertIn(CUSTOMER_PAY_NO_BALANCE_MSG, str(ctx.exception))

    @patch("app.services.payments.lock_bills_for_update")
    @patch("app.services.payments.load_customer_bills_with_due")
    def test_rejects_no_open_bills(self, mock_load, _lock):
        customer = _customer(debit="5000")
        mock_load.return_value = []
        account = _cash_account()
        db, _ = self._mock_db(customer, [], account)

        with self.assertRaises(ValueError) as ctx:
            pay_customer_balance(db, 1, "debit", Decimal("100"), account_id=10, company_id=1)
        self.assertIn(CUSTOMER_PAY_NO_OPEN_BILLS_MSG, str(ctx.exception))

    @patch("app.services.payments.lock_bills_for_update")
    @patch("app.services.payments.load_customer_bills_with_due")
    @patch("app.services.payments._resolve_money_account_id", return_value=10)
    def test_cap_by_open_dues_when_balance_higher(self, _resolve, mock_load, _lock):
        customer = _customer(debit="20000")
        b1 = _bill(1, BillType.sales, customer, "3000")
        mock_load.return_value = [(b1, Decimal("3000"))]
        account = _cash_account()
        db, _ = self._mock_db(customer, [(b1, Decimal("3000"))], account)

        with self.assertRaises(ValueError) as ctx:
            pay_customer_balance(db, 1, "debit", Decimal("4000"), account_id=10, company_id=1)
        self.assertIn(CUSTOMER_PAY_OVER_CAP_MSG, str(ctx.exception))
        self.assertIn("3000", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
