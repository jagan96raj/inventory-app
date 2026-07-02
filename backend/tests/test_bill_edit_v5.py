"""Spec v5 bill edit unit tests."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.entities import BillType, DeliveryStatus, PaymentStatus
from app.services.bills import (
    apply_balance_on_edit_replace,
    recalc_delivery_status_after_edit,
    update_line_delivery_status,
    validate_edit_bill,
)
from app.services.payments import update_bill_payment_status
from app.utils import delivery_status_from_qty


class BalanceReplaceTests(unittest.TestCase):
    def test_purchase_50k_to_40k(self):
        customer = SimpleNamespace(credit_balance=Decimal("50000"), debit_balance=Decimal("0"))
        db = MagicMock()
        bill = SimpleNamespace(bill_type=BillType.purchase, grand_total=Decimal("40000"))
        apply_balance_on_edit_replace(db, customer, bill, Decimal("50000"))
        self.assertEqual(customer.credit_balance, Decimal("40000"))

    def test_sales_50k_to_60k(self):
        customer = SimpleNamespace(credit_balance=Decimal("0"), debit_balance=Decimal("50000"))
        db = MagicMock()
        bill = SimpleNamespace(bill_type=BillType.sales, grand_total=Decimal("60000"))
        apply_balance_on_edit_replace(db, customer, bill, Decimal("50000"))
        self.assertEqual(customer.debit_balance, Decimal("60000"))


class ValidateEditTests(unittest.TestCase):
    def _line(self, lid, ordered_kg, net_delivered=0, net_received=0):
        return SimpleNamespace(
            id=lid,
            ordered_quantity_kg=Decimal(str(ordered_kg)),
            net_delivered_kg=Decimal(str(net_delivered)),
            net_received_kg=Decimal(str(net_received)),
            net_returned_kg=Decimal("0"),
            bag_type=SimpleNamespace(is_loose=False, weight_per_bag_kg=Decimal("50")),
        )

    def test_blocks_below_delivered(self):
        bill = SimpleNamespace(bill_type=BillType.sales, grand_total=Decimal("40000"), payments=[])
        line = self._line(1, ordered_kg=400, net_delivered=500)
        with self.assertRaises(ValueError) as ctx:
            validate_edit_bill(bill, [line])
        self.assertIn("return first", str(ctx.exception))

    def test_blocks_final_below_paid(self):
        bill = SimpleNamespace(
            bill_type=BillType.purchase,
            grand_total=Decimal("25000"),
            payments=[SimpleNamespace(amount=Decimal("30000"))],
        )
        line = self._line(1, ordered_kg=500)
        with self.assertRaises(ValueError) as ctx:
            validate_edit_bill(bill, [line])
        self.assertIn("less than amount already paid", str(ctx.exception))


class DeliveryStatusTests(unittest.TestCase):
    def test_delivered_when_qty_matches_net(self):
        line = SimpleNamespace(
            ordered_quantity_kg=Decimal("500"),
            net_delivered_kg=Decimal("500"),
            net_received_kg=Decimal("0"),
            net_returned_kg=Decimal("0"),
            line_delivery_status=None,
        )
        update_line_delivery_status(line, BillType.sales)
        self.assertEqual(line.line_delivery_status, DeliveryStatus.delivered)
        self.assertEqual(delivery_status_from_qty(Decimal("500"), Decimal("500")), "delivered")


class PaymentStatusAfterEditTests(unittest.TestCase):
    def test_paid_when_equal(self):
        bill = SimpleNamespace(
            grand_total=Decimal("50000"),
            amount_paid=Decimal("0"),
            payment_status=None,
            payments=[SimpleNamespace(amount=Decimal("50000"))],
        )
        update_bill_payment_status(bill)
        self.assertEqual(bill.payment_status, PaymentStatus.paid)

    def test_partial_after_edit(self):
        bill = SimpleNamespace(
            grand_total=Decimal("45000"),
            amount_paid=Decimal("0"),
            payment_status=None,
            payments=[SimpleNamespace(amount=Decimal("30000"))],
        )
        update_bill_payment_status(bill)
        self.assertEqual(bill.payment_status, PaymentStatus.partial)


class DeliveryRollupTests(unittest.TestCase):
    def test_mixed_partial_bill(self):
        db = MagicMock()
        lines = [
            SimpleNamespace(line_delivery_status=DeliveryStatus.delivered),
            SimpleNamespace(line_delivery_status=DeliveryStatus.not_delivered),
        ]
        db.scalars.return_value.all.return_value = lines
        bill = SimpleNamespace(id=1, order_delivery_status=None)

        from app.services.bills import update_bill_delivery_status

        update_bill_delivery_status(db, bill)
        self.assertEqual(bill.order_delivery_status, DeliveryStatus.partial)


if __name__ == "__main__":
    unittest.main()
