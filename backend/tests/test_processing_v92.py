"""Spec v9.2 processing balance and net summary tests."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.entities import ProcessingInputSource, ProcessingJobStatus
from app.services.processing import compute_processing_summary, submit_batch
from tests.processing_test_helpers import (
    bag_type_loose,
    bag_type_50kg,
    balance_return_batch,
    fresh_and_return_batch,
    fresh_input_batch,
    mock_db_bag_types,
    mock_db_stored_input_lines,
)


def _bag_type_loose():
    return SimpleNamespace(id=99, is_loose=True, weight_per_bag_kg=Decimal("0"))


def _bag_type_50kg():
    return SimpleNamespace(id=1, is_loose=False, weight_per_bag_kg=Decimal("50"))


class ProcessingV92Tests(unittest.TestCase):
    def _open_job(self, batches=None):
        return SimpleNamespace(
            id=1,
            input_product_id=10,
            input_brand_id=20,
            status=ProcessingJobStatus.open,
            completed_at=None,
            batches=batches or [],
            input_product=SimpleNamespace(product_name="Moong"),
            input_brand=SimpleNamespace(name="Unclean"),
        )

    def test_two_batch_unclean_scenario_summary(self):
        bt50 = _bag_type_50kg()
        bt_loose = _bag_type_loose()
        job = SimpleNamespace(
            batches=[
                SimpleNamespace(
                    input_lines=[
                        SimpleNamespace(
                            quantity_kg=Decimal("2000"),
                            bag_count=40,
                            input_source=ProcessingInputSource.fresh,
                            bag_type=bt50,
                        )
                    ],
                    output_lines=[
                        SimpleNamespace(
                            quantity_kg=Decimal("500"),
                            brand_id=30,
                            brand=SimpleNamespace(name="Clean A"),
                            bag_count=10,
                        )
                    ],
                    balance_return_lines=[
                        SimpleNamespace(quantity_kg=Decimal("15")),
                    ],
                    dust_kg=Decimal("0"),
                    stone_kg=Decimal("0"),
                    sack_weight_waste_kg=Decimal("5"),
                    miscellaneous_waste_kg=Decimal("10"),
                ),
                SimpleNamespace(
                    input_lines=[
                        SimpleNamespace(
                            quantity_kg=Decimal("2000"),
                            bag_count=40,
                            input_source=ProcessingInputSource.fresh,
                            bag_type=bt50,
                        ),
                        SimpleNamespace(
                            quantity_kg=Decimal("15"),
                            bag_count=0,
                            input_source=ProcessingInputSource.balance_reprocess,
                            bag_type=bt_loose,
                        ),
                    ],
                    output_lines=[
                        SimpleNamespace(
                            quantity_kg=Decimal("400"),
                            brand_id=31,
                            brand=SimpleNamespace(name="Clean B"),
                            bag_count=8,
                        )
                    ],
                    balance_return_lines=[
                        SimpleNamespace(quantity_kg=Decimal("15")),
                    ],
                    dust_kg=Decimal("0"),
                    stone_kg=Decimal("0"),
                    sack_weight_waste_kg=Decimal("5"),
                    miscellaneous_waste_kg=Decimal("10"),
                ),
            ]
        )
        summary = compute_processing_summary(job)
        self.assertEqual(summary["total_fresh_input_kg"], Decimal("4000"))
        self.assertEqual(summary["fresh_input_bags"], 80)
        self.assertEqual(summary["total_balance_reprocess_kg"], Decimal("15"))
        self.assertEqual(summary["total_balance_return_kg"], Decimal("30"))
        self.assertEqual(summary["net_balance_kg"], Decimal("15"))
        self.assertEqual(summary["job_available_reprocess_kg"], Decimal("15"))
        self.assertEqual(summary["total_waste_kg"], Decimal("10"))
        self.assertEqual(summary["total_misc_kg"], Decimal("3075"))
        self.assertEqual(summary["total_loss_kg"], Decimal("3085"))
        self.assertEqual(summary["batch_count"], 2)
        self.assertEqual(len(summary["output_by_brand"]), 2)
        brands = {row["brand_name"]: row["quantity_kg"] for row in summary["output_by_brand"]}
        self.assertEqual(brands["Clean A"], Decimal("500"))
        self.assertEqual(brands["Clean B"], Decimal("400"))

    def test_mixed_batch_fresh_and_reprocess_summary(self):
        bt50 = _bag_type_50kg()
        bt_loose = _bag_type_loose()
        job = SimpleNamespace(
            batches=[
                SimpleNamespace(
                    input_lines=[
                        SimpleNamespace(
                            quantity_kg=Decimal("2000"),
                            bag_count=40,
                            input_source=ProcessingInputSource.fresh,
                            bag_type=bt50,
                        ),
                        SimpleNamespace(
                            quantity_kg=Decimal("15"),
                            bag_count=0,
                            input_source=ProcessingInputSource.balance_reprocess,
                            bag_type=bt_loose,
                        ),
                    ],
                    output_lines=[],
                    balance_return_lines=[],
                    dust_kg=Decimal("0"),
                    stone_kg=Decimal("0"),
                    sack_weight_waste_kg=Decimal("0"),
                    miscellaneous_waste_kg=Decimal("0"),
                ),
            ]
        )
        summary = compute_processing_summary(job)
        self.assertEqual(summary["total_fresh_input_kg"], Decimal("2000"))
        self.assertEqual(summary["fresh_input_bags"], 40)
        self.assertEqual(summary["total_balance_reprocess_kg"], Decimal("15"))
        all_input_kg = sum(
            ln.quantity_kg for batch in job.batches for ln in batch.input_lines
        )
        self.assertEqual(all_input_kg, Decimal("2015"))
        self.assertNotEqual(summary["total_fresh_input_kg"], all_input_kg)

    def test_mixed_batch_subtracts_inventory_for_both_sources(self):
        db = MagicMock()
        job = self._open_job([fresh_and_return_batch(Decimal("2000"), Decimal("15"))])
        mock_db_bag_types(db, {1: bag_type_50kg(1), 99: bag_type_loose(99)})
        mock_db_stored_input_lines(db, job=job)
        subtract_calls: list[tuple] = []
        qty_by_loose = {Decimal("0"): Decimal("2000"), Decimal("15"): Decimal("15")}
        inv = SimpleNamespace(bag_count=40, loose_kg=Decimal("15"), total_quantity_kg=Decimal("2015"))

        def _sub(db_, pid, bid, lid, btid, bags, loose, owner_type=None, customer_id=None, company_id=1):
            subtract_calls.append((bags, loose, lid))
            return qty_by_loose.get(loose, Decimal("0"))

        with patch("app.services.processing.get_inventory_row", return_value=inv):
            with patch("app.services.processing.subtract_inventory", side_effect=_sub):
                with patch("app.services.processing.add_inventory", return_value=Decimal("0")):
                    with patch("app.services.processing.load_processing_job", return_value=job):
                        submit_batch(
                        db,
                        1,
                        input_lines=[
                            {
                                "location_id": 1,
                                "bag_type_id": 1,
                                "bag_count": 40,
                                "loose_kg": Decimal("0"),
                                "input_source": "fresh",
                            },
                            {
                                "location_id": 1,
                                "bag_type_id": 99,
                                "bag_count": 0,
                                "loose_kg": Decimal("15"),
                                "input_source": "balance_reprocess",
                            },
                        ],
                        output_lines=[],
                        balance_return_lines=[],
                        dust_kg=Decimal("0"),
                        stone_kg=Decimal("0"),
                        sack_weight_waste_kg=Decimal("0"),
                        miscellaneous_waste_kg=Decimal("0"),
                    )

        self.assertEqual(len(subtract_calls), 2)
        self.assertEqual(subtract_calls[0][0], 40)
        self.assertEqual(subtract_calls[1][1], Decimal("15"))

    def test_balance_reprocess_without_prior_return_blocked(self):
        db = MagicMock()
        job = self._open_job()
        mock_db_bag_types(db, {99: bag_type_loose(99)})
        subtract_calls: list[tuple] = []

        def _sub(db_, pid, bid, lid, btid, bags, loose, owner_type=None, customer_id=None, company_id=1):
            subtract_calls.append((pid, bid, lid, btid, bags, loose))
            return Decimal("15")

        with patch("app.services.processing.subtract_inventory", side_effect=_sub):
            with patch("app.services.processing.add_inventory", return_value=Decimal("0")):
                with patch("app.services.processing.load_processing_job", return_value=job):
                    with self.assertRaises(ValueError) as ctx:
                        submit_batch(
                            db,
                            1,
                            input_lines=[
                                {
                                    "location_id": 1,
                                    "bag_type_id": 99,
                                    "bag_count": 0,
                                    "loose_kg": Decimal("15"),
                                    "input_source": "balance_reprocess",
                                }
                            ],
                            output_lines=[],
                            balance_return_lines=[],
                            dust_kg=Decimal("0"),
                            stone_kg=Decimal("0"),
                            sack_weight_waste_kg=Decimal("0"),
                            miscellaneous_waste_kg=Decimal("0"),
                        )
        self.assertIn("from stock only", str(ctx.exception).lower())
        self.assertEqual(len(subtract_calls), 0)

    def test_balance_return_adds_inventory(self):
        db = MagicMock()
        job = self._open_job(batches=[fresh_input_batch(Decimal("100"))])
        mock_db_bag_types(db, {99: bag_type_loose(99)})
        mock_db_stored_input_lines(db, job=job)
        add_calls: list[tuple] = []

        def _add(db_, pid, bid, lid, btid, bags, loose, owner_type=None, customer_id=None, company_id=1):
            add_calls.append((pid, bid, lid, btid, bags, loose))
            return Decimal("15")

        with patch("app.services.processing.subtract_inventory"):
            with patch("app.services.processing.add_inventory", side_effect=_add):
                with patch("app.services.processing.load_processing_job", return_value=job):
                    submit_batch(
                        db,
                        1,
                        input_lines=[],
                        output_lines=[],
                        balance_return_lines=[
                            {
                                "location_id": 2,
                                "bag_type_id": 99,
                                "bag_count": 0,
                                "loose_kg": Decimal("15"),
                            }
                        ],
                        dust_kg=Decimal("0"),
                        stone_kg=Decimal("0"),
                        sack_weight_waste_kg=Decimal("0"),
                        miscellaneous_waste_kg=Decimal("0"),
                    )

        self.assertEqual(len(add_calls), 1)
        self.assertEqual(add_calls[0][:2], (10, 20))


if __name__ == "__main__":
    unittest.main()
