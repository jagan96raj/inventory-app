"""Spec v5.1 payment module unit tests."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.entities import BillStatus, BillType, PaymentMode
from app.services.payments import apply_payment_balance, create_payment


class ApplyPaymentBalanceTests(unittest.TestCase):
    def _customer(self, credit="0", debit="0"):
        return SimpleNamespace(credit_balance=Decimal(credit), debit_balance=Decimal(debit))

    def _payment(self, amount, mode):
        return SimpleNamespace(amount=Decimal(str(amount)), payment_mode=mode)

    def test_purchase_cash_reduces_credit_only(self):
        customer = self._customer(credit="5000", debit="3000")
        bill = SimpleNamespace(bill_type=BillType.purchase, customer_id=1, customer=customer)
        db = MagicMock()
        apply_payment_balance(db, bill, self._payment(2000, PaymentMode.cash))
        self.assertEqual(customer.credit_balance, Decimal("3000"))
        self.assertEqual(customer.debit_balance, Decimal("3000"))

    def test_purchase_debit_reduces_both(self):
        customer = self._customer(credit="5000", debit="3000")
        bill = SimpleNamespace(bill_type=BillType.purchase, customer_id=1, customer=customer)
        db = MagicMock()
        apply_payment_balance(db, bill, self._payment(2000, PaymentMode.debit))
        self.assertEqual(customer.credit_balance, Decimal("3000"))
        self.assertEqual(customer.debit_balance, Decimal("1000"))

    def test_sales_cash_reduces_debit_only(self):
        customer = self._customer(credit="2000", debit="5000")
        bill = SimpleNamespace(bill_type=BillType.sales, customer_id=1, customer=customer)
        db = MagicMock()
        apply_payment_balance(db, bill, self._payment(2000, PaymentMode.bank))
        self.assertEqual(customer.debit_balance, Decimal("3000"))
        self.assertEqual(customer.credit_balance, Decimal("2000"))

    def test_sales_credit_reduces_both(self):
        customer = self._customer(credit="2000", debit="5000")
        bill = SimpleNamespace(bill_type=BillType.sales, customer_id=1, customer=customer)
        db = MagicMock()
        apply_payment_balance(db, bill, self._payment(2000, PaymentMode.credit))
        self.assertEqual(customer.debit_balance, Decimal("3000"))
        self.assertEqual(customer.credit_balance, Decimal("0"))


class AutoFillLogicTests(unittest.TestCase):
    """Mirror PaymentPage auto-fill: min(balance, due)."""

    def min_fill(self, balance, due):
        return min(Decimal(str(balance)), Decimal(str(due)))

    def test_purchase_debit_3000_due_5000(self):
        self.assertEqual(self.min_fill(3000, 5000), Decimal("3000"))

    def test_purchase_debit_8000_due_5000(self):
        self.assertEqual(self.min_fill(8000, 5000), Decimal("5000"))

    def test_sales_credit_2000_due_5000(self):
        self.assertEqual(self.min_fill(2000, 5000), Decimal("2000"))

    def test_sales_credit_10000_due_5000(self):
        self.assertEqual(self.min_fill(10000, 5000), Decimal("5000"))


class CreatePaymentValidationTests(unittest.TestCase):
    def test_rejects_amount_over_due(self):
        db = MagicMock()
        bill = SimpleNamespace(
            id=1,
            status=BillStatus.finalized,
            bill_type=BillType.purchase,
            grand_total=Decimal("5000"),
            version=1,
            customer=SimpleNamespace(
                credit_balance=Decimal("5000"),
                debit_balance=Decimal("0"),
            ),
            payments=[],
        )
        db.scalar.return_value = bill
        with patch("app.services.payments.lock_bill_for_update", return_value=bill):
            with self.assertRaises(ValueError) as ctx:
                create_payment(db, 1, Decimal("6000"), PaymentMode.cash, expected_version=1)
        self.assertIn("exceeds amount due", str(ctx.exception))

    def test_purchase_rejects_credit_mode(self):
        db = MagicMock()
        bill = SimpleNamespace(
            id=1,
            status=BillStatus.finalized,
            bill_type=BillType.purchase,
            grand_total=Decimal("5000"),
            version=1,
            customer=SimpleNamespace(
                credit_balance=Decimal("5000"),
                debit_balance=Decimal("1000"),
            ),
            payments=[],
        )
        db.scalar.return_value = bill
        with patch("app.services.payments.lock_bill_for_update", return_value=bill):
            with self.assertRaises(ValueError) as ctx:
                create_payment(db, 1, Decimal("1000"), PaymentMode.credit, expected_version=1)
        self.assertIn("not valid on purchase", str(ctx.exception))

    @patch("app.services.payments.opposite_bills_due_total", return_value=Decimal("5000"))
    def test_debit_mode_requires_sufficient_balance(self, _mock_opp):
        db = MagicMock()
        bill = SimpleNamespace(
            id=1,
            status=BillStatus.finalized,
            bill_type=BillType.purchase,
            grand_total=Decimal("5000"),
            version=1,
            customer_id=1,
            customer=SimpleNamespace(
                credit_balance=Decimal("5000"),
                debit_balance=Decimal("2000"),
            ),
            payments=[],
        )
        db.scalar.return_value = bill
        with patch("app.services.payments.lock_bill_for_update", return_value=bill):
            with self.assertRaises(ValueError) as ctx:
                create_payment(db, 1, Decimal("3000"), PaymentMode.debit, expected_version=1)
        msg = str(ctx.exception).lower()
        self.assertTrue("debit balance" in msg or "set-off amount" in msg)


if __name__ == "__main__":
    unittest.main()
