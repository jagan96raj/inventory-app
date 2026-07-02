"""Spec v5.2 cross-bill set-off payment tests."""
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.entities import BillStatus, BillType, Payment, PaymentMode, PaymentStatus
from app.services.payments import (
    allocate_setoff_fifo,
    apply_payment_balance,
    create_payment,
    opposite_bills_due_total,
    preview_setoff_allocation,
)


def _customer(credit="0", debit="0"):
    return SimpleNamespace(id=1, credit_balance=Decimal(credit), debit_balance=Decimal(debit))


def _bill(
    bill_id: int,
    bill_type: BillType,
    customer,
    grand_total: str,
    payments=None,
    bill_number: str | None = None,
):
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
        bill_date=date(2026, 1, bill_id),
        version=1,
    )


class AllocateSetoffFifoTests(unittest.TestCase):
    def test_single_bill_full(self):
        b1 = _bill(2, BillType.sales, _customer(), "10000")
        allocations = allocate_setoff_fifo([(b1, Decimal("10000"))], Decimal("10000"))
        self.assertEqual(allocations, [(2, Decimal("10000"))])

    def test_fifo_split_two_bills(self):
        b1 = _bill(2, BillType.sales, _customer(), "4000", bill_number="S1")
        b2 = _bill(3, BillType.sales, _customer(), "6000", bill_number="S2")
        allocations = allocate_setoff_fifo(
            [(b1, Decimal("4000")), (b2, Decimal("6000"))],
            Decimal("10000"),
        )
        self.assertEqual(allocations, [(2, Decimal("4000")), (3, Decimal("6000"))])

    def test_partial_allocation(self):
        b1 = _bill(2, BillType.sales, _customer(), "6000")
        allocations = allocate_setoff_fifo([(b1, Decimal("6000"))], Decimal("6000"))
        self.assertEqual(allocations, [(2, Decimal("6000"))])


class OppositeBillsDueTotalTests(unittest.TestCase):
    def test_sums_remaining_on_opposite_bills(self):
        customer = _customer()
        sales1 = _bill(2, BillType.sales, customer, "4000")
        sales2 = _bill(3, BillType.sales, customer, "6000")
        sales1.payments = [SimpleNamespace(amount=Decimal("1000"))]
        db = MagicMock()
        db.scalars.return_value.unique.return_value.all.return_value = [sales1, sales2]
        total = opposite_bills_due_total(db, 1, BillType.purchase)
        self.assertEqual(total, Decimal("9000"))


class ApplyPaymentBalanceSetoffTests(unittest.TestCase):
    def test_setoff_does_not_change_balances(self):
        customer = _customer(credit="5000", debit="5000")
        bill = SimpleNamespace(bill_type=BillType.sales, customer_id=1, customer=customer)
        payment = SimpleNamespace(amount=Decimal("2000"), payment_mode=PaymentMode.setoff)
        db = MagicMock()
        apply_payment_balance(db, bill, payment)
        self.assertEqual(customer.credit_balance, Decimal("5000"))
        self.assertEqual(customer.debit_balance, Decimal("5000"))


class CreatePaymentSetoffTests(unittest.TestCase):
    def _mock_db(self, primary, opposite_bills):
        db = MagicMock()
        db.scalar.return_value = primary
        db.scalars.return_value.unique.return_value.all.return_value = [b for b, _ in opposite_bills]
        payment_id = [0]

        def add_obj(obj):
            if isinstance(obj, Payment):
                payment_id[0] += 1
                obj.id = payment_id[0]

        db.add.side_effect = add_obj
        return db

    def _pay(self, db, primary, *args, **kwargs):
        with patch("app.services.payments.lock_bill_for_update", return_value=primary):
            with patch("app.services.payments.lock_bills_for_update", return_value={}):
                return create_payment(db, primary.id, *args, **kwargs)

    @patch("app.services.payments.load_opposite_bills_with_due")
    @patch("app.services.payments.opposite_bills_due_total")
    def test_purchase_debit_pays_both_bills(self, mock_opp_total, mock_opp_bills):
        customer = _customer(credit="10000", debit="10000")
        purchase = _bill(1, BillType.purchase, customer, "10000")
        sales = _bill(2, BillType.sales, customer, "10000")
        mock_opp_total.return_value = Decimal("10000")
        mock_opp_bills.return_value = [(sales, Decimal("10000"))]
        db = self._mock_db(purchase, [(sales, Decimal("10000"))])

        self._pay(db, purchase, Decimal("10000"), PaymentMode.debit, expected_version=1)

        self.assertEqual(customer.credit_balance, Decimal("0"))
        self.assertEqual(customer.debit_balance, Decimal("0"))
        self.assertEqual(len(purchase.payments), 1)
        self.assertEqual(purchase.payments[0].payment_mode, PaymentMode.debit)
        self.assertEqual(len(sales.payments), 1)
        self.assertEqual(sales.payments[0].payment_mode, PaymentMode.setoff)
        self.assertEqual(sales.payments[0].linked_payment_id, purchase.payments[0].id)
        self.assertEqual(purchase.payment_status, PaymentStatus.paid)
        self.assertEqual(sales.payment_status, PaymentStatus.paid)

    @patch("app.services.payments.load_opposite_bills_with_due")
    @patch("app.services.payments.opposite_bills_due_total")
    def test_fifo_split_across_two_sales_bills(self, mock_opp_total, mock_opp_bills):
        customer = _customer(credit="10000", debit="10000")
        purchase = _bill(1, BillType.purchase, customer, "10000")
        sales1 = _bill(2, BillType.sales, customer, "4000", bill_number="S1")
        sales2 = _bill(3, BillType.sales, customer, "6000", bill_number="S2")
        mock_opp_total.return_value = Decimal("10000")
        mock_opp_bills.return_value = [
            (sales1, Decimal("4000")),
            (sales2, Decimal("6000")),
        ]
        db = self._mock_db(purchase, mock_opp_bills.return_value)

        self._pay(db, purchase, Decimal("10000"), PaymentMode.debit, expected_version=1)

        self.assertEqual(len(sales1.payments), 1)
        self.assertEqual(sales1.payments[0].amount, Decimal("4000"))
        self.assertEqual(len(sales2.payments), 1)
        self.assertEqual(sales2.payments[0].amount, Decimal("6000"))

    @patch("app.services.payments.load_opposite_bills_with_due")
    @patch("app.services.payments.opposite_bills_due_total")
    def test_partial_when_opposite_due_less_than_primary(self, mock_opp_total, mock_opp_bills):
        customer = _customer(credit="10000", debit="10000")
        purchase = _bill(1, BillType.purchase, customer, "10000")
        sales = _bill(2, BillType.sales, customer, "6000")
        mock_opp_total.return_value = Decimal("6000")
        mock_opp_bills.return_value = [(sales, Decimal("6000"))]
        db = self._mock_db(purchase, [(sales, Decimal("6000"))])

        self._pay(db, purchase, Decimal("6000"), PaymentMode.debit, expected_version=1)

        self.assertEqual(purchase.payment_status, PaymentStatus.partial)
        self.assertEqual(sales.payment_status, PaymentStatus.paid)
        self.assertEqual(customer.credit_balance, Decimal("4000"))
        self.assertEqual(customer.debit_balance, Decimal("4000"))

    def test_blocks_debit_when_no_opposite_bills(self):
        customer = _customer(credit="10000", debit="10000")
        purchase = _bill(1, BillType.purchase, customer, "10000")
        db = MagicMock()
        db.scalar.return_value = purchase
        db.scalars.return_value.unique.return_value.all.return_value = []

        with self.assertRaises(ValueError) as ctx:
            self._pay(db, purchase, Decimal("10000"), PaymentMode.debit, expected_version=1)
        self.assertIn("opposite bills", str(ctx.exception).lower())

    def test_cash_creates_no_linked_payments(self):
        customer = _customer(credit="5000", debit="0")
        purchase = _bill(1, BillType.purchase, customer, "5000")
        db = MagicMock()
        db.scalar.return_value = purchase
        payment_id = [0]

        def add_obj(obj):
            if isinstance(obj, Payment):
                payment_id[0] += 1
                obj.id = payment_id[0]

        db.add.side_effect = add_obj

        self._pay(db, purchase, Decimal("2000"), PaymentMode.cash, expected_version=1)

        self.assertEqual(len(purchase.payments), 1)
        self.assertEqual(purchase.payments[0].payment_mode, PaymentMode.cash)
        self.assertIsNone(getattr(purchase.payments[0], "linked_payment_id", None))

    def test_rejects_standalone_setoff(self):
        db = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            create_payment(db, 1, Decimal("1000"), PaymentMode.setoff, expected_version=1)
        self.assertIn("cannot be created directly", str(ctx.exception).lower())

    @patch("app.services.payments.load_opposite_bills_with_due")
    @patch("app.services.payments.opposite_bills_due_total")
    def test_setoff_does_not_double_reduce_balances(self, mock_opp_total, mock_opp_bills):
        customer = _customer(credit="10000", debit="10000")
        purchase = _bill(1, BillType.purchase, customer, "10000")
        sales = _bill(2, BillType.sales, customer, "10000")
        mock_opp_total.return_value = Decimal("10000")
        mock_opp_bills.return_value = [(sales, Decimal("10000"))]
        db = self._mock_db(purchase, [(sales, Decimal("10000"))])

        self._pay(db, purchase, Decimal("10000"), PaymentMode.debit, expected_version=1)

        # Both balances reduced once by primary debit payment only
        self.assertEqual(customer.credit_balance, Decimal("0"))
        self.assertEqual(customer.debit_balance, Decimal("0"))


class PreviewSetoffTests(unittest.TestCase):
    @patch("app.services.payments.load_opposite_bills_with_due")
    @patch("app.services.payments.opposite_bills_due_total")
    def test_preview_caps_at_max_amount(self, mock_opp_total, mock_opp_bills):
        customer = _customer(credit="10000", debit="10000")
        purchase = _bill(1, BillType.purchase, customer, "10000")
        sales = _bill(2, BillType.sales, customer, "6000")
        mock_opp_total.return_value = Decimal("6000")
        mock_opp_bills.return_value = [(sales, Decimal("6000"))]
        db = MagicMock()
        db.scalar.return_value = purchase

        result = preview_setoff_allocation(db, 1, Decimal("10000"), PaymentMode.debit)

        self.assertEqual(result["max_amount"], Decimal("6000"))
        self.assertEqual(result["amount"], Decimal("6000"))
        self.assertEqual(len(result["allocations"]), 1)
        self.assertEqual(result["allocations"][0]["amount"], Decimal("6000"))


if __name__ == "__main__":
    unittest.main()
