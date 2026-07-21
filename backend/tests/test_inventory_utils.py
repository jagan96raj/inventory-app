"""Inventory row recalc — empty stock after full subtract must be valid."""
import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.utils import recalc_inventory_row, validate_bags_loose, validate_inventory_row_state


class InventoryRowStateTests(unittest.TestCase):
    def test_empty_bagged_row_is_valid(self):
        bt = SimpleNamespace(is_loose=False, weight_per_bag_kg=Decimal("50"))
        validate_inventory_row_state(bt, 0, Decimal("0"))

    def test_empty_loose_row_is_valid(self):
        bt = SimpleNamespace(is_loose=True, weight_per_bag_kg=Decimal("0"))
        validate_inventory_row_state(bt, 0, Decimal("0"))

    def test_recalc_after_full_bag_subtract(self):
        bt = SimpleNamespace(is_loose=False, weight_per_bag_kg=Decimal("50"))
        inv = SimpleNamespace(bag_count=10, loose_kg=Decimal("0"), total_quantity_kg=Decimal("500"))
        inv.bag_count -= 10
        recalc_inventory_row(inv, bt)
        self.assertEqual(inv.bag_count, 0)
        self.assertEqual(inv.total_quantity_kg, Decimal("0"))

    def test_transaction_line_still_requires_bags(self):
        bt = SimpleNamespace(is_loose=False, weight_per_bag_kg=Decimal("50"))
        with self.assertRaises(ValueError) as ctx:
            validate_bags_loose(bt, 0, Decimal("0"))
        self.assertIn("at least one bag", str(ctx.exception).lower())

    def test_bill_line_allows_zero_when_flagged(self):
        bagged = SimpleNamespace(is_loose=False, weight_per_bag_kg=Decimal("50"))
        loose = SimpleNamespace(is_loose=True, weight_per_bag_kg=Decimal("0"))
        validate_bags_loose(bagged, 0, Decimal("0"), allow_zero=True)
        validate_bags_loose(loose, 0, Decimal("0"), allow_zero=True)

    def test_zero_ordered_qty_is_delivered(self):
        from app.utils import delivery_status_from_qty

        self.assertEqual(delivery_status_from_qty(Decimal("0"), Decimal("0")), "delivered")


if __name__ == "__main__":
    unittest.main()
