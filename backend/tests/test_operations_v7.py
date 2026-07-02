"""Spec v7 operations unit tests."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.operations import create_bag_change


class BagChangeBalanceTests(unittest.TestCase):
    def _bag_type(self, bt_id: int, weight: str = "50"):
        return SimpleNamespace(id=bt_id, is_loose=False, weight_per_bag_kg=Decimal(weight))

    def test_blocks_unbalanced_from_to_loss(self):
        db = MagicMock()
        db.get.side_effect = lambda _cls, bid: self._bag_type(bid)
        with patch("app.services.operations.subtract_inventory"):
            with self.assertRaises(ValueError) as ctx:
                create_bag_change(
                    db,
                    location_id=1,
                    product_id=1,
                    brand_id=1,
                    from_bag_type_id=1,
                    from_bag_count=50,
                    from_loose_kg=Decimal("0"),
                    quantity_loss_kg=Decimal("0"),
                    to_lines=[
                        {"to_bag_type_id": 2, "bag_count": 31, "loose_kg": Decimal("0")},
                    ],
                    notes=None,
                )
        self.assertIn("from_kg must equal", str(ctx.exception))

    def test_validates_bag_types_exist(self):
        db = MagicMock()
        db.get.return_value = None
        with self.assertRaises(ValueError) as ctx:
            create_bag_change(
                db,
                location_id=1,
                product_id=1,
                brand_id=1,
                from_bag_type_id=99,
                from_bag_count=1,
                from_loose_kg=Decimal("0"),
                quantity_loss_kg=Decimal("0"),
                to_lines=[{"to_bag_type_id": 2, "bag_count": 1, "loose_kg": Decimal("0")}],
                notes=None,
            )
        self.assertIn("Invalid bag type", str(ctx.exception))


class ProductTransferValidationTests(unittest.TestCase):
    def test_same_location_rejected(self):
        from app.services.operations import create_product_transfer

        db = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            create_product_transfer(
                db,
                product_id=1,
                brand_id=1,
                bag_type_id=1,
                from_location_id=1,
                to_location_id=1,
                bag_count=1,
                loose_kg=Decimal("0"),
                notes=None,
            )
        self.assertIn("must differ", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
