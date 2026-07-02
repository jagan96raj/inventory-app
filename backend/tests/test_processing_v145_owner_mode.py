"""Spec v14.5 — processing job owner-mode rules (mixed input lock + single-owner exception)."""
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import (
    BagType,
    Brand,
    Customer,
    CustomerPartyType,
    Inventory,
    InventoryOwnerType,
    JobWorkLine,
    ProcessingOutputLine,
    Product,
    Location,
)
from app.services.job_work import create_job_work_order, receive_job_work
from app.services.operations import add_inventory
from app.services.processing import (
    DIFFERENT_OWNER_AFTER_OUTPUT_MSG,
    MIXED_EXTERNAL_OWNER_MSG,
    MIXED_JOB_NO_MORE_INPUT_MSG,
    MIXED_OWNERS_FIRST_BATCH_ONLY_MSG,
    create_job,
    submit_batch,
    validate_processing_owner_mix,
)
from tests.idempotency_helpers import ensure_test_user

PROPORTIONAL = {"output_allocation_mode": "proportional"}


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Bajra")
    unclean = Brand(name="Unclean")
    raj_agro = Brand(name="Raj Agro")
    location = Location(name="Unit")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    raghavendra = Customer(name="Sri Raghavendra", party_type=CustomerPartyType.internal)
    external = Customer(name="External Co", party_type=CustomerPartyType.external)
    db.add_all([product, unclean, raj_agro, location, bag_type, raghavendra, external])
    db.commit()
    return {
        "product": product,
        "unclean": unclean,
        "raj_agro": raj_agro,
        "location": location,
        "bag_type": bag_type,
        "raghavendra": raghavendra,
        "external": external,
    }


def _owned_input(m: dict, bags: int) -> dict:
    return {
        "location_id": m["location"].id,
        "bag_type_id": m["bag_type"].id,
        "bag_count": bags,
        "loose_kg": Decimal("0"),
        "owner_type": "owned",
    }


def _jw_input(m: dict, bags: int) -> dict:
    return {
        "location_id": m["location"].id,
        "bag_type_id": m["bag_type"].id,
        "bag_count": bags,
        "loose_kg": Decimal("0"),
        "owner_type": "job_work",
        "customer_id": m["raghavendra"].id,
    }


def _raj_agro_output(m: dict, bags: int) -> dict:
    return {
        "brand_id": m["raj_agro"].id,
        "location_id": m["location"].id,
        "bag_type_id": m["bag_type"].id,
        "bag_count": bags,
        "loose_kg": Decimal("0"),
    }


class ProcessingV145MixedBatchOneTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["unclean"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            85,
            Decimal("0"),
        )
        order = create_job_work_order(
            self.db,
            customer_id=self.m["raghavendra"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["unclean"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 28,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=self.db.scalar(select(JobWorkLine)).id,
            location_id=self.m["location"].id,
            bag_count=23,
            loose_kg=Decimal("0"),
        )

    def test_mixed_batch1_output_then_input_rejected(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 85), _jw_input(self.m, 23)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 103)],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        output_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        owner_types = {ln.owner_type for ln in output_lines}
        self.assertIn(InventoryOwnerType.owned, owner_types)
        self.assertIn(InventoryOwnerType.job_work, owner_types)

        with self.assertRaises(ValueError) as ctx:
            submit_batch(
                self.db,
                job.id,
                input_lines=[_owned_input(self.m, 10)],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )
        self.assertEqual(str(ctx.exception), MIXED_JOB_NO_MORE_INPUT_MSG)


class ProcessingV145SingleOwnerTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["unclean"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            100,
            Decimal("0"),
        )

    def test_same_owner_multiple_input_batches_all_owned_output(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 50)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 30)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 80)],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        owned_out = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.owned,
                Inventory.brand_id == self.m["raj_agro"].id,
            )
        )
        jw_out = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.brand_id == self.m["raj_agro"].id,
            )
        )
        self.assertIsNotNone(owned_out)
        self.assertEqual(owned_out.bag_count, 80)
        self.assertIsNone(jw_out)


class ProcessingV145SingleOwnerExceptionTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["unclean"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            85,
            Decimal("0"),
        )
        order = create_job_work_order(
            self.db,
            customer_id=self.m["raghavendra"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["unclean"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 28,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=self.db.scalar(select(JobWorkLine)).id,
            location_id=self.m["location"].id,
            bag_count=23,
            loose_kg=Decimal("0"),
        )

    def test_exception_path_then_input_locked_output_splits(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 85)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_jw_input(self.m, 23)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL,
        )
        with self.assertRaises(ValueError) as ctx:
            submit_batch(
                self.db,
                job.id,
                input_lines=[_owned_input(self.m, 5)],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )
        self.assertEqual(str(ctx.exception), MIXED_JOB_NO_MORE_INPUT_MSG)

        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 103)],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        output_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        owner_types = {ln.owner_type for ln in output_lines}
        self.assertIn(InventoryOwnerType.owned, owner_types)
        self.assertIn(InventoryOwnerType.job_work, owner_types)
        self.assertEqual(sum(ln.bag_count for ln in output_lines), 103)


class ProcessingV145OutputBeforeDifferentOwnerTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["unclean"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            85,
            Decimal("0"),
        )
        order = create_job_work_order(
            self.db,
            customer_id=self.m["raghavendra"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["unclean"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 28,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=self.db.scalar(select(JobWorkLine)).id,
            location_id=self.m["location"].id,
            bag_count=23,
            loose_kg=Decimal("0"),
        )

    def test_output_first_blocks_different_owner_input(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 85)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 50)],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        with self.assertRaises(ValueError) as ctx:
            submit_batch(
                self.db,
                job.id,
                input_lines=[_jw_input(self.m, 10)],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )
        self.assertEqual(str(ctx.exception), DIFFERENT_OWNER_AFTER_OUTPUT_MSG)


class ProcessingV145MixedSecondBatchRejectedTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["unclean"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            85,
            Decimal("0"),
        )
        order = create_job_work_order(
            self.db,
            customer_id=self.m["raghavendra"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["unclean"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 28,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=self.db.scalar(select(JobWorkLine)).id,
            location_id=self.m["location"].id,
            bag_count=23,
            loose_kg=Decimal("0"),
        )

    def test_second_batch_mixed_owners_in_one_batch_rejected(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 85)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        with self.assertRaises(ValueError) as ctx:
            submit_batch(
                self.db,
                job.id,
                input_lines=[_owned_input(self.m, 5), _jw_input(self.m, 5)],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )
        self.assertEqual(str(ctx.exception), MIXED_OWNERS_FIRST_BATCH_ONLY_MSG)


class ProcessingV145RegressionTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

    def test_external_mixed_still_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_processing_owner_mix(
                self.db,
                [
                    {"owner_type": "owned"},
                    {
                        "owner_type": "job_work",
                        "customer_id": self.m["external"].id,
                    },
                ],
            )
        self.assertEqual(str(ctx.exception), MIXED_EXTERNAL_OWNER_MSG)

    def test_separate_input_output_batch_workflow(self):
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["unclean"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            85,
            Decimal("0"),
        )
        order = create_job_work_order(
            self.db,
            customer_id=self.m["raghavendra"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["unclean"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 28,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=self.db.scalar(select(JobWorkLine)).id,
            location_id=self.m["location"].id,
            bag_count=23,
            loose_kg=Decimal("0"),
        )
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 85), _jw_input(self.m, 23)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 103)],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        output_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        self.assertEqual(len(output_lines), 2)
        self.assertEqual(sum(ln.bag_count for ln in output_lines), 103)


if __name__ == "__main__":
    unittest.main()
