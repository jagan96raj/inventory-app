"""Spec v17.3.21 — dashboard Money now snapshot (not month P&L)."""
import unittest
from decimal import Decimal

from app.services.accounts import money_now_from_totals


class MoneyNowV17321Tests(unittest.TestCase):
    def test_four_derived_amounts(self):
        m = Decimal("10000.00")
        c = Decimal("2000.00")
        d = Decimal("3500.00")
        snap = money_now_from_totals(
            total_money=m,
            total_customer_credit=c,
            total_customer_debit=d,
        )
        self.assertEqual(snap["amount_in_hand"], Decimal("10000.00"))
        self.assertEqual(snap["after_credit"], Decimal("8000.00"))
        self.assertEqual(snap["after_debit"], Decimal("13500.00"))
        self.assertEqual(snap["after_settlement"], Decimal("11500.00"))

    def test_amount_in_hand_is_m_not_m_minus_debit(self):
        m = Decimal("5000.00")
        d = Decimal("1200.00")
        snap = money_now_from_totals(
            total_money=m,
            total_customer_credit=Decimal("0"),
            total_customer_debit=d,
        )
        self.assertEqual(snap["amount_in_hand"], m)
        self.assertNotEqual(snap["amount_in_hand"], (m - d).quantize(Decimal("0.01")))
        self.assertEqual(snap["after_debit"], Decimal("6200.00"))

    def test_after_settlement_is_not_profit_formula(self):
        """M − C + D is a cash-if-settled snapshot, not sales − purchase − expenses."""
        snap = money_now_from_totals(
            total_money=Decimal("8000.00"),
            total_customer_credit=Decimal("500.00"),
            total_customer_debit=Decimal("1500.00"),
        )
        self.assertEqual(snap["after_settlement"], Decimal("9000.00"))
        self.assertNotEqual(snap["after_settlement"], snap["amount_in_hand"])
