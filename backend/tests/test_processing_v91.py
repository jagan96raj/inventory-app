"""Spec v9.1 / v9.2 processing summary unit tests."""
import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.models.entities import ProcessingInputSource
from app.services.processing import compute_processing_summary


def _input_line(qty: str, *, source=ProcessingInputSource.fresh, bags: int = 0, is_loose: bool = False):
    return SimpleNamespace(
        quantity_kg=Decimal(qty),
        bag_count=bags,
        input_source=source,
        bag_type=SimpleNamespace(is_loose=is_loose),
    )


def _output_line(qty: str, brand_id: int = 1, brand_name: str = "Clean", bags: int = 0):
    return SimpleNamespace(
        quantity_kg=Decimal(qty),
        brand_id=brand_id,
        brand=SimpleNamespace(name=brand_name),
        bag_count=bags,
    )


def _balance_line(qty: str):
    return SimpleNamespace(quantity_kg=Decimal(qty))


def _batch(
    *,
    input_lines=None,
    output_lines=None,
    balance_return_lines=None,
    dust: str = "0",
    stone: str = "0",
    sack: str = "0",
    misc: str = "0",
):
    return SimpleNamespace(
        input_lines=input_lines or [],
        output_lines=output_lines or [],
        balance_return_lines=balance_return_lines or [],
        dust_kg=Decimal(dust),
        stone_kg=Decimal(stone),
        sack_weight_waste_kg=Decimal(sack),
        miscellaneous_waste_kg=Decimal(misc),
    )


class ProcessingSummaryTests(unittest.TestCase):
    def test_fresh_input_and_loss_totals(self):
        job = SimpleNamespace(
            batches=[
                _batch(
                    input_lines=[_input_line("100", bags=2)],
                    output_lines=[_output_line("40", brand_id=2, brand_name="Grade A")],
                    dust="5",
                ),
                _batch(
                    input_lines=[_input_line("50", bags=1)],
                    output_lines=[_output_line("30", brand_id=2, brand_name="Grade A")],
                    stone="2",
                ),
            ]
        )
        summary = compute_processing_summary(job)
        self.assertEqual(summary["total_fresh_input_kg"], Decimal("150"))
        self.assertEqual(summary["fresh_input_bags"], 3)
        self.assertEqual(summary["total_waste_kg"], Decimal("7"))
        self.assertEqual(summary["total_misc_kg"], Decimal("73"))
        self.assertEqual(summary["total_loss_kg"], Decimal("80"))
        self.assertEqual(summary["batch_count"], 2)
        self.assertEqual(len(summary["output_by_brand"]), 1)
        self.assertEqual(summary["output_by_brand"][0]["quantity_kg"], Decimal("70"))

    def test_net_balance_kg_formula(self):
        job = SimpleNamespace(
            batches=[
                _batch(
                    balance_return_lines=[_balance_line("15")],
                ),
                _batch(
                    input_lines=[
                        _input_line("15", source=ProcessingInputSource.balance_reprocess),
                    ],
                    balance_return_lines=[_balance_line("15")],
                ),
            ]
        )
        summary = compute_processing_summary(job)
        self.assertEqual(summary["total_balance_return_kg"], Decimal("30"))
        self.assertEqual(summary["total_balance_reprocess_kg"], Decimal("15"))
        self.assertEqual(summary["net_balance_kg"], Decimal("15"))
        self.assertEqual(summary["total_fresh_input_kg"], Decimal("0"))

    def test_waste_and_auto_misc_split(self):
        job = SimpleNamespace(
            batches=[
                _batch(
                    input_lines=[_input_line("100")],
                    output_lines=[_output_line("60")],
                    dust="3",
                    stone="2",
                    sack="5",
                ),
            ]
        )
        summary = compute_processing_summary(job)
        self.assertEqual(summary["total_waste_kg"], Decimal("10"))
        self.assertEqual(summary["total_misc_kg"], Decimal("30"))
        self.assertEqual(summary["total_loss_kg"], Decimal("40"))

    def test_empty_job_summary(self):
        job = SimpleNamespace(batches=[])
        summary = compute_processing_summary(job)
        self.assertEqual(summary["total_fresh_input_kg"], Decimal("0"))
        self.assertEqual(summary["fresh_input_bags"], 0)
        self.assertEqual(summary["net_balance_kg"], Decimal("0"))
        self.assertEqual(summary["total_waste_kg"], Decimal("0"))
        self.assertEqual(summary["total_misc_kg"], Decimal("0"))
        self.assertEqual(summary["total_loss_kg"], Decimal("0"))
        self.assertEqual(summary["output_by_brand"], [])
        self.assertEqual(summary["batch_count"], 0)


if __name__ == "__main__":
    unittest.main()
