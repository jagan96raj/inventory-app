"""Spec v9.4 — balance reprocess guards."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.entities import ProcessingInputSource, ProcessingJobStatus
from app.services.processing import (
    BALANCE_REPROCESS_NO_RETURN_MSG,
    compute_job_available_reprocess_kg,
    compute_processing_summary,
    submit_batch,
    validate_balance_reprocess,
)
from tests.processing_test_helpers import (
    bag_type_loose,
    balance_return_batch,
    fresh_and_return_batch,
    mock_db_bag_types,
    mock_db_stored_input_lines,
)


def _open_job(batches=None):
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


class ProcessingV94ValidationTests(unittest.TestCase):
    def test_e_available_never_negative(self):
        job = SimpleNamespace(
            batches=[
                SimpleNamespace(
                    input_lines=[
                        SimpleNamespace(
                            quantity_kg=Decimal("20"),
                            input_source=ProcessingInputSource.balance_reprocess,
                        )
                    ],
                    balance_return_lines=[SimpleNamespace(quantity_kg=Decimal("15"))],
                )
            ]
        )
        self.assertEqual(compute_job_available_reprocess_kg(job), Decimal("0"))

    def test_f_summary_includes_job_available(self):
        job = SimpleNamespace(
            batches=[
                SimpleNamespace(
                    input_lines=[],
                    output_lines=[],
                    balance_return_lines=[SimpleNamespace(quantity_kg=Decimal("15"))],
                    dust_kg=Decimal("0"),
                    stone_kg=Decimal("0"),
                    sack_weight_waste_kg=Decimal("0"),
                    miscellaneous_waste_kg=Decimal("0"),
                ),
                SimpleNamespace(
                    input_lines=[
                        SimpleNamespace(
                            quantity_kg=Decimal("10"),
                            bag_count=0,
                            input_source=ProcessingInputSource.balance_reprocess,
                            bag_type=SimpleNamespace(is_loose=True),
                        )
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
        self.assertEqual(summary["job_available_reprocess_kg"], Decimal("5"))
        self.assertEqual(summary["net_balance_kg"], Decimal("5"))

    def test_a_reprocess_without_return_rejected(self):
        db = MagicMock()
        job = _open_job()
        mock_db_bag_types(db, {99: bag_type_loose(99)})
        with self.assertRaises(ValueError) as ctx:
            validate_balance_reprocess(
                job,
                [
                    {
                        "location_id": 1,
                        "bag_type_id": 99,
                        "bag_count": 0,
                        "loose_kg": Decimal("15"),
                        "input_source": "balance_reprocess",
                    }
                ],
                db,
            )
        self.assertEqual(str(ctx.exception), BALANCE_REPROCESS_NO_RETURN_MSG)

    def test_c_reprocess_exceeds_available_rejected(self):
        db = MagicMock()
        job = _open_job([balance_return_batch(Decimal("15"))])
        mock_db_bag_types(db, {99: bag_type_loose(99)})
        with self.assertRaises(ValueError) as ctx:
            validate_balance_reprocess(
                job,
                [
                    {
                        "location_id": 1,
                        "bag_type_id": 99,
                        "bag_count": 0,
                        "loose_kg": Decimal("20"),
                        "input_source": "balance_reprocess",
                    }
                ],
                db,
            )
        self.assertIn("exceeds unclean balance available", str(ctx.exception).lower())


class ProcessingV94SubmitTests(unittest.TestCase):
    def test_a_submit_reprocess_without_return_no_inventory_change(self):
        db = MagicMock()
        job = _open_job()
        mock_db_bag_types(db, {99: bag_type_loose(99)})
        subtract = MagicMock(return_value=Decimal("15"))
        with patch("app.services.processing.subtract_inventory", subtract):
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
        self.assertEqual(str(ctx.exception), BALANCE_REPROCESS_NO_RETURN_MSG)
        subtract.assert_not_called()
        db.commit.assert_not_called()

    def test_b_return_then_reprocess_ok(self):
        db = MagicMock()
        job = _open_job([fresh_and_return_batch(Decimal("2000"), Decimal("15"))])
        mock_db_bag_types(db, {99: bag_type_loose(99)})
        mock_db_stored_input_lines(db, job=job)

        inv = SimpleNamespace(bag_count=0, loose_kg=Decimal("15"), total_quantity_kg=Decimal("15"))

        with patch("app.services.processing.get_inventory_row", return_value=inv):
            with patch("app.services.processing.subtract_inventory", return_value=Decimal("15")):
                with patch("app.services.processing.add_inventory", return_value=Decimal("0")):
                    with patch("app.services.processing.load_processing_job", return_value=job):
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
        db.commit.assert_called_once()

    def test_d_partial_reprocess_ok_summary_available_five(self):
        db = MagicMock()
        job = _open_job([fresh_and_return_batch(Decimal("2000"), Decimal("15"))])
        mock_db_bag_types(db, {99: bag_type_loose(99)})
        mock_db_stored_input_lines(db, job=job)
        inv = SimpleNamespace(bag_count=0, loose_kg=Decimal("15"), total_quantity_kg=Decimal("15"))

        def _reload(_db, _jid):
            batch = SimpleNamespace(
                input_lines=[
                    SimpleNamespace(
                        quantity_kg=Decimal("10"),
                        bag_count=0,
                        input_source=ProcessingInputSource.balance_reprocess,
                        bag_type=SimpleNamespace(is_loose=True),
                    )
                ],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )
            return _open_job(
                [
                    fresh_and_return_batch(Decimal("2000"), Decimal("15")),
                    batch,
                ]
            )

        with patch("app.services.processing.get_inventory_row", return_value=inv):
            with patch("app.services.processing.subtract_inventory", return_value=Decimal("10")):
                with patch("app.services.processing.add_inventory", return_value=Decimal("0")):
                    with patch("app.services.processing.load_processing_job", side_effect=[job, job]):
                        submit_batch(
                            db,
                            1,
                            input_lines=[
                                {
                                    "location_id": 1,
                                    "bag_type_id": 99,
                                    "bag_count": 0,
                                    "loose_kg": Decimal("10"),
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

        updated = _reload(db, 1)
        summary = compute_processing_summary(updated)
        self.assertEqual(summary["total_balance_reprocess_kg"], Decimal("10"))
        self.assertEqual(summary["job_available_reprocess_kg"], Decimal("5"))


if __name__ == "__main__":
    unittest.main()
