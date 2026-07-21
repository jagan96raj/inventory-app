"""Spec v9.3 processing mass-balance guard tests.

Manual test checklist:
1. New job → output only → blocked
2. Input 2000 kg → output 1950 + balance 15 + waste 15 → OK
3. Second batch fresh 2000 + reprocess 15 → summary fresh still 4000;
   allowance basis = fresh + reprocess → output within allowance → OK
4. Try outflow > (fresh + reprocess) + 100 → blocked on submit
"""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.entities import ProcessingInputSource, ProcessingJobStatus
from app.services.processing import (
    PROCESSING_OUTPUT_TOLERANCE_KG,
    compute_job_fresh_input_kg,
    compute_job_mass_balance_input_kg,
    compute_job_outflow_kg,
    submit_batch,
    validate_processing_mass_balance,
)
from tests.processing_test_helpers import bag_type_loose, mock_db_bag_types


def _fresh_line(qty: Decimal) -> SimpleNamespace:
    return SimpleNamespace(
        quantity_kg=qty,
        input_source=ProcessingInputSource.fresh,
    )


def _output_line(qty: Decimal) -> SimpleNamespace:
    return SimpleNamespace(quantity_kg=qty)


def _balance_line(qty: Decimal) -> SimpleNamespace:
    return SimpleNamespace(quantity_kg=qty)


def _batch(
    *,
    fresh_input: Decimal = Decimal("0"),
    output: Decimal = Decimal("0"),
    balance_return: Decimal = Decimal("0"),
    dust: Decimal = Decimal("0"),
    stone: Decimal = Decimal("0"),
    sack: Decimal = Decimal("0"),
    misc: Decimal = Decimal("0"),
    reprocess: Decimal = Decimal("0"),
) -> SimpleNamespace:
    input_lines = []
    if fresh_input > 0:
        input_lines.append(_fresh_line(fresh_input))
    if reprocess > 0:
        input_lines.append(
            SimpleNamespace(
                quantity_kg=reprocess,
                input_source=ProcessingInputSource.balance_reprocess,
            )
        )
    output_lines = [_output_line(output)] if output > 0 else []
    balance_return_lines = [_balance_line(balance_return)] if balance_return > 0 else []
    return SimpleNamespace(
        input_lines=input_lines,
        output_lines=output_lines,
        balance_return_lines=balance_return_lines,
        dust_kg=dust,
        stone_kg=stone,
        sack_weight_waste_kg=sack,
        miscellaneous_waste_kg=misc,
        powder_kg=Decimal("0"),
    )


class ProcessingV93ValidationTests(unittest.TestCase):
    def _job(self, batches: list) -> SimpleNamespace:
        return SimpleNamespace(batches=batches)

    def _validate(self, job, **kwargs) -> None:
        validate_processing_mass_balance(
            job,
            pending_input_lines=kwargs.get("pending_input_lines", []),
            pending_output_lines=kwargs.get("pending_output_lines", []),
            pending_balance_return_lines=kwargs.get("pending_balance_return_lines", []),
            pending_waste_fields=kwargs.get(
                "pending_waste_fields",
                {
                    "dust_kg": Decimal("0"),
                    "stone_kg": Decimal("0"),
                    "sack_weight_waste_kg": Decimal("0"),
                    "miscellaneous_waste_kg": Decimal("0"),
                },
            ),
            db=MagicMock(),
        )

    def test_fresh_4000_outflow_3960_passes(self):
        job = self._job([_batch(fresh_input=Decimal("4000"), output=Decimal("3960"))])
        self._validate(job)

    def test_fresh_zero_output_50_fails(self):
        job = self._job([])
        with self.assertRaises(ValueError) as ctx:
            self._validate(
                job,
                pending_output_lines=[
                    {
                        "bag_type_id": 1,
                        "bag_count": 0,
                        "loose_kg": Decimal("50"),
                        "quantity_kg": Decimal("50"),
                    }
                ],
            )
        self.assertIn("fresh input", str(ctx.exception).lower())

    def test_fresh_2000_outflow_2110_fails_tolerance(self):
        job = self._job([_batch(fresh_input=Decimal("2000"), output=Decimal("2110"))])
        with self.assertRaises(ValueError) as ctx:
            self._validate(job)
        self.assertIn("allowance", str(ctx.exception).lower())

    def test_fresh_2000_outflow_2090_passes(self):
        job = self._job([_batch(fresh_input=Decimal("2000"), output=Decimal("2090"))])
        self._validate(job)

    def test_two_batch_unclean_reprocess_in_allowance_basis(self):
        job = self._job(
            [
                _batch(
                    fresh_input=Decimal("2000"),
                    output=Decimal("500"),
                    balance_return=Decimal("15"),
                    sack=Decimal("5"),
                    misc=Decimal("10"),
                ),
                _batch(
                    fresh_input=Decimal("2000"),
                    reprocess=Decimal("15"),
                    output=Decimal("400"),
                    balance_return=Decimal("15"),
                    sack=Decimal("5"),
                    misc=Decimal("10"),
                ),
            ]
        )
        fresh = compute_job_fresh_input_kg(job)
        input_kg = compute_job_mass_balance_input_kg(job)
        self.assertEqual(fresh, Decimal("4000"))
        self.assertEqual(input_kg, Decimal("4015"))
        outflow = compute_job_outflow_kg(job)
        self.assertLessEqual(outflow, input_kg + PROCESSING_OUTPUT_TOLERANCE_KG)
        self._validate(job)

    def test_reprocess_raises_ceiling_when_returns_in_outflow(self):
        """Return counts as outflow; without counting reprocess as in, this would fail."""
        job = self._job(
            [
                _batch(
                    fresh_input=Decimal("1000"),
                    output=Decimal("900"),
                    balance_return=Decimal("80"),
                    dust=Decimal("20"),
                ),
                _batch(
                    reprocess=Decimal("80"),
                    output=Decimal("175"),  # uses returned material; total outflow 1175
                ),
            ]
        )
        # fresh=1000, input=1080, outflow=900+80+20+175=1175
        # old rule: 1175 > 1000+100 → fail
        # new rule: 1175 <= 1080+100 → pass
        self.assertEqual(compute_job_fresh_input_kg(job), Decimal("1000"))
        self.assertEqual(compute_job_mass_balance_input_kg(job), Decimal("1080"))
        self.assertEqual(compute_job_outflow_kg(job), Decimal("1175"))
        self._validate(job)

    def test_allowance_equals_misc_plus_tolerance(self):
        job = self._job(
            [
                _batch(
                    fresh_input=Decimal("12500"),
                    output=Decimal("12000"),
                    balance_return=Decimal("50"),
                    stone=Decimal("20"),
                ),
                _batch(
                    fresh_input=Decimal("12500"),
                    reprocess=Decimal("50"),
                    output=Decimal("12400"),
                    dust=Decimal("30"),
                ),
            ]
        )
        fresh = compute_job_fresh_input_kg(job)
        reprocess = Decimal("50")
        input_kg = compute_job_mass_balance_input_kg(job)
        outflow = compute_job_outflow_kg(job)
        explicit_waste = Decimal("50")
        output = Decimal("24400")
        bal_ret = Decimal("50")
        residual_misc = fresh + reprocess - output - bal_ret - explicit_waste
        allowance = input_kg + PROCESSING_OUTPUT_TOLERANCE_KG - outflow
        self.assertEqual(allowance, residual_misc + PROCESSING_OUTPUT_TOLERANCE_KG)
        self._validate(job)


class ProcessingV93SubmitTests(unittest.TestCase):
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

    def test_output_without_fresh_input_blocked(self):
        db = MagicMock()
        job = self._open_job()
        mock_db_bag_types(db, {3: bag_type_loose(3)})

        with patch("app.services.processing.load_processing_job", return_value=job):
            with self.assertRaises(ValueError) as ctx:
                submit_batch(
                    db,
                    1,
                    input_lines=[],
                    output_lines=[
                        {
                            "brand_id": 30,
                            "location_id": 1,
                            "bag_type_id": 3,
                            "bag_count": 0,
                            "loose_kg": Decimal("50"),
                        }
                    ],
                    balance_return_lines=[],
                    dust_kg=Decimal("0"),
                    stone_kg=Decimal("0"),
                    sack_weight_waste_kg=Decimal("0"),
                    miscellaneous_waste_kg=Decimal("0"),
                )
        self.assertIn("fresh input", str(ctx.exception).lower())

    def test_input_only_submit_not_blocked(self):
        db = MagicMock()
        job = self._open_job()
        mock_db_bag_types(db, {2: bag_type_loose(2)})

        with patch("app.services.processing.subtract_inventory", return_value=Decimal("2000")):
            with patch("app.services.processing.add_inventory", return_value=Decimal("0")):
                with patch("app.services.processing.load_processing_job", return_value=job):
                    submit_batch(
                        db,
                        1,
                        input_lines=[
                            {
                                "location_id": 1,
                                "bag_type_id": 2,
                                "bag_count": 0,
                                "loose_kg": Decimal("2000"),
                                "input_source": "fresh",
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


if __name__ == "__main__":
    unittest.main()
