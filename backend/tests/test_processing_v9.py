"""Spec v9 processing unit tests."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.entities import ProcessingJobStatus
from app.services.processing import (
    batch_has_content,
    complete_job,
    create_job,
    submit_batch,
)
from tests.processing_test_helpers import (
    bag_type_15kg,
    bag_type_50kg,
    fresh_input_batch,
    mock_db_bag_types,
    mock_db_stored_input_lines,
)


class BatchContentTests(unittest.TestCase):
    def test_empty_batch_rejected(self):
        self.assertFalse(
            batch_has_content(
                input_lines=[],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                powder_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )
        )

    def test_waste_only_counts(self):
        self.assertTrue(
            batch_has_content(
                input_lines=[],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("1"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                powder_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )
        )


class ProcessingV9ServiceTests(unittest.TestCase):
    def _open_job(self, job_id: int = 1, batches=None):
        return SimpleNamespace(
            id=job_id,
            input_product_id=10,
            input_brand_id=20,
            status=ProcessingJobStatus.open,
            completed_at=None,
            batches=batches or [],
            input_product=SimpleNamespace(product_name="Wheat"),
            input_brand=SimpleNamespace(name="Raw"),
        )

    def test_input_only_batch_subtracts(self):
        db = MagicMock()
        job = self._open_job()
        mock_db_bag_types(db, {2: bag_type_50kg(2)})
        subtract_calls: list[tuple] = []
        add_calls: list[tuple] = []

        def _sub(db_, pid, bid, lid, btid, bags, loose, owner_type=None, customer_id=None, company_id=1):
            subtract_calls.append((pid, bid, lid, btid, bags, loose))
            return Decimal("50")

        with patch("app.services.processing.subtract_inventory", side_effect=_sub):
            with patch("app.services.processing.add_inventory", side_effect=lambda *a, **k: add_calls.append(a)):
                with patch("app.services.processing.load_processing_job", return_value=job):
                    submit_batch(
                        db,
                        1,
                        input_lines=[
                            {
                                "location_id": 1,
                                "bag_type_id": 2,
                                "bag_count": 1,
                                "loose_kg": Decimal("0"),
                            }
                        ],
                        output_lines=[],
                        balance_return_lines=[],
                        dust_kg=Decimal("0"),
                        stone_kg=Decimal("0"),
                        sack_weight_waste_kg=Decimal("0"),
                        miscellaneous_waste_kg=Decimal("0"),
                    )

        self.assertEqual(len(subtract_calls), 1)
        self.assertEqual(subtract_calls[0], (10, 20, 1, 2, 1, Decimal("0")))
        self.assertEqual(add_calls, [])
        db.commit.assert_called_once()

    def test_output_only_batch_adds(self):
        db = MagicMock()
        job = self._open_job(batches=[fresh_input_batch(Decimal("100"))])
        mock_db_bag_types(db, {3: bag_type_15kg(3)})
        mock_db_stored_input_lines(db, job=job)
        add_calls: list[tuple] = []

        def _add(db_, pid, bid, lid, btid, bags, loose, owner_type=None, customer_id=None, company_id=1):
            add_calls.append((pid, bid, lid, btid, bags, loose))
            return Decimal("30")

        with patch("app.services.processing.subtract_inventory"):
            with patch("app.services.processing.add_inventory", side_effect=_add):
                with patch("app.services.processing.load_processing_job", return_value=job):
                    submit_batch(
                        db,
                        1,
                        input_lines=[],
                        output_lines=[
                            {
                                "brand_id": 30,
                                "location_id": 1,
                                "bag_type_id": 3,
                                "bag_count": 2,
                                "loose_kg": Decimal("0"),
                            }
                        ],
                        balance_return_lines=[],
                        dust_kg=Decimal("0"),
                        stone_kg=Decimal("0"),
                        sack_weight_waste_kg=Decimal("0"),
                        miscellaneous_waste_kg=Decimal("0"),
                    )

        self.assertEqual(len(add_calls), 1)
        self.assertEqual(add_calls[0], (10, 30, 1, 3, 2, Decimal("0")))

    def test_complete_locks_job(self):
        db = MagicMock()
        job = self._open_job()
        db.get.return_value = job
        db.scalar.return_value = 99

        with patch("app.services.processing.load_processing_job", return_value=job):
            complete_job(
                db,
                1,
                input_lines=[],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                powder_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )

        self.assertEqual(job.status, ProcessingJobStatus.completed)
        self.assertIsNotNone(job.completed_at)

    def test_incremental_batches_do_not_replay(self):
        db = MagicMock()
        job = self._open_job()
        mock_db_bag_types(db, {2: bag_type_50kg(2)})
        subtract_calls = 0

        def _sub(*_args, **_kwargs):
            nonlocal subtract_calls
            subtract_calls += 1
            return Decimal("10")

        with patch("app.services.processing.subtract_inventory", side_effect=_sub):
            with patch("app.services.processing.add_inventory"):
                with patch("app.services.processing.load_processing_job", return_value=job):
                    submit_batch(
                        db,
                        1,
                        input_lines=[
                            {
                                "location_id": 1,
                                "bag_type_id": 2,
                                "bag_count": 1,
                                "loose_kg": Decimal("0"),
                            }
                        ],
                        output_lines=[],
                        balance_return_lines=[],
                        dust_kg=Decimal("0"),
                        stone_kg=Decimal("0"),
                        sack_weight_waste_kg=Decimal("0"),
                        miscellaneous_waste_kg=Decimal("0"),
                    )
                    submit_batch(
                        db,
                        1,
                        input_lines=[
                            {
                                "location_id": 1,
                                "bag_type_id": 2,
                                "bag_count": 2,
                                "loose_kg": Decimal("0"),
                            }
                        ],
                        output_lines=[],
                        balance_return_lines=[],
                        dust_kg=Decimal("0"),
                        stone_kg=Decimal("0"),
                        sack_weight_waste_kg=Decimal("0"),
                        miscellaneous_waste_kg=Decimal("0"),
                    )

        self.assertEqual(subtract_calls, 2)

    def test_waste_stored_no_inventory_effect(self):
        db = MagicMock()
        job = self._open_job()
        db.get.return_value = job
        batch_holder: list = []

        def capture_batch(db_, job_, **kwargs):
            batch = SimpleNamespace(
                id=1,
                job_id=job_.id,
                operation_at=kwargs.get("operation_at"),
                dust_kg=kwargs["dust_kg"],
                stone_kg=kwargs["stone_kg"],
                sack_weight_waste_kg=kwargs["sack_weight_waste_kg"],
                miscellaneous_waste_kg=kwargs["miscellaneous_waste_kg"],
                input_lines=[],
                output_lines=[],
            )
            batch_holder.append(batch)
            return batch

        with patch("app.services.processing.batch._apply_batch", side_effect=capture_batch):
            with patch("app.services.processing.load_processing_job", return_value=job):
                submit_batch(
                    db,
                    1,
                    input_lines=[],
                    output_lines=[],
                    balance_return_lines=[],
                    dust_kg=Decimal("2.5"),
                    stone_kg=Decimal("1"),
                    sack_weight_waste_kg=Decimal("0"),
                    miscellaneous_waste_kg=Decimal("0.5"),
                )

        self.assertEqual(len(batch_holder), 1)
        self.assertEqual(batch_holder[0].dust_kg, Decimal("2.5"))
        self.assertEqual(batch_holder[0].stone_kg, Decimal("1"))

    def test_complete_empty_without_batches_succeeds(self):
        """v17.3.1: empty open job (no active batches) may be completed to free the slot."""
        db = MagicMock()
        job = self._open_job()
        db.scalar.return_value = None

        with patch("app.services.processing.load_processing_job", return_value=job):
            complete_job(
                db,
                1,
                input_lines=[],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )

        self.assertEqual(job.status, ProcessingJobStatus.completed)
        self.assertIsNotNone(job.completed_at)
        db.commit.assert_called()

    def test_completed_job_rejects_batch(self):
        db = MagicMock()
        job = self._open_job()
        job.status = ProcessingJobStatus.completed

        with patch("app.services.processing.load_processing_job", return_value=job):
            with self.assertRaises(ValueError) as ctx:
                submit_batch(
                    db,
                    1,
                    input_lines=[
                        {
                            "location_id": 1,
                            "bag_type_id": 2,
                            "bag_count": 1,
                            "loose_kg": Decimal("0"),
                        }
                    ],
                    output_lines=[],
                    balance_return_lines=[],
                    dust_kg=Decimal("0"),
                    stone_kg=Decimal("0"),
                    sack_weight_waste_kg=Decimal("0"),
                    miscellaneous_waste_kg=Decimal("0"),
                )
        self.assertIn("not open", str(ctx.exception).lower())

    def test_create_job_blocks_duplicate_open(self):
        db = MagicMock()
        db.scalar.return_value = SimpleNamespace(id=5)

        with self.assertRaises(ValueError) as ctx:
            create_job(db, input_product_id=1, input_brand_id=2)
        self.assertIn("already exists", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
