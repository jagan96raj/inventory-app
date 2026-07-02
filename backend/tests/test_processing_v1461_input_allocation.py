"""Spec v14.6.1 — mixed processing output allocation on input batch (not output)."""
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
    ProcessingWasteAllocation,
    Product,
    Location,
)
from app.services.job_work import create_job_work_order, receive_job_work
from app.services.operations import add_inventory
from app.services.processing import (
    MIXED_EXTERNAL_OWNER_MSG,
    MIXED_JOB_NO_MORE_INPUT_MSG,
    OUTPUT_ALLOCATION_LOCKED_MSG,
    OUTPUT_ALLOCATION_MODE_REQUIRED_MSG,
    SINGLE_OWNER_NOT_IN_JOB_INPUT_MSG,
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


def _jw_input(m: dict, bags: int, customer_id: int | None = None) -> dict:
    return {
        "location_id": m["location"].id,
        "bag_type_id": m["bag_type"].id,
        "bag_count": bags,
        "loose_kg": Decimal("0"),
        "owner_type": "job_work",
        "customer_id": customer_id or m["raghavendra"].id,
    }


def _raj_agro_output(m: dict, bags: int) -> dict:
    return {
        "brand_id": m["raj_agro"].id,
        "location_id": m["location"].id,
        "bag_type_id": m["bag_type"].id,
        "bag_count": bags,
        "loose_kg": Decimal("0"),
    }


def _zero_batch() -> dict:
    return {
        "balance_return_lines": [],
        "dust_kg": Decimal("0"),
        "stone_kg": Decimal("0"),
        "sack_weight_waste_kg": Decimal("0"),
        "powder_kg": Decimal("0"),
        "miscellaneous_waste_kg": Decimal("0"),
    }


class ProcessingV1461InputAllocationTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["unclean"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            200,
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
                    "ordered_bags": 50,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=self.db.scalar(select(JobWorkLine)).id,
            location_id=self.m["location"].id,
            bag_count=50,
            loose_kg=Decimal("0"),
        )

    def test_path_a_proportional_input_locked_then_output_splits(self):
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
            **PROPORTIONAL,
            **_zero_batch(),
        )
        with self.assertRaisesRegex(ValueError, MIXED_JOB_NO_MORE_INPUT_MSG):
            submit_batch(
                self.db,
                job.id,
                input_lines=[_owned_input(self.m, 5)],
                output_lines=[],
                **_zero_batch(),
            )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 103)],
            **_zero_batch(),
        )
        output_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        owned_bags = sum(
            ln.bag_count for ln in output_lines if ln.owner_type == InventoryOwnerType.owned
        )
        jw_bags = sum(
            ln.bag_count
            for ln in output_lines
            if ln.owner_type == InventoryOwnerType.job_work
        )
        self.assertEqual(owned_bags + jw_bags, 103)
        self.assertEqual(owned_bags, 81)
        self.assertEqual(jw_bags, 22)

    def test_path_a_single_owner_owned_allows_more_owned_input(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 80), _jw_input(self.m, 20)],
            output_lines=[],
            output_allocation_mode="single_owner",
            single_allocation_owner_type="owned",
            **_zero_batch(),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 50)],
            output_lines=[],
            **_zero_batch(),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 100)],
            **_zero_batch(),
        )
        output_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        self.assertTrue(all(ln.owner_type == InventoryOwnerType.owned for ln in output_lines))

    def test_single_owner_rejects_other_owner_input(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 80), _jw_input(self.m, 20)],
            output_lines=[],
            output_allocation_mode="single_owner",
            single_allocation_owner_type="owned",
            **_zero_batch(),
        )
        with self.assertRaisesRegex(ValueError, "Only Owned may receive more input"):
            submit_batch(
                self.db,
                job.id,
                input_lines=[_jw_input(self.m, 10)],
                output_lines=[],
                **_zero_batch(),
            )

    def test_path_b_single_owner_jw_allows_more_jw_rejects_owned(self):
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
            **_zero_batch(),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_jw_input(self.m, 23)],
            output_lines=[],
            output_allocation_mode="single_owner",
            single_allocation_owner_type="job_work",
            single_allocation_customer_id=self.m["raghavendra"].id,
            **_zero_batch(),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_jw_input(self.m, 5)],
            output_lines=[],
            **_zero_batch(),
        )
        with self.assertRaisesRegex(ValueError, "Only Job work"):
            submit_batch(
                self.db,
                job.id,
                input_lines=[_owned_input(self.m, 3)],
                output_lines=[],
                **_zero_batch(),
            )

    def test_output_only_no_allocation_fields_when_mode_set(self):
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
            **PROPORTIONAL,
            **_zero_batch(),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 50)],
            **_zero_batch(),
        )
        output_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        self.assertGreater(len(output_lines), 0)

    def test_cannot_change_mode_after_mixed_input_saved(self):
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
            **PROPORTIONAL,
            **_zero_batch(),
        )
        with self.assertRaisesRegex(ValueError, OUTPUT_ALLOCATION_LOCKED_MSG):
            submit_batch(
                self.db,
                job.id,
                input_lines=[],
                output_lines=[_raj_agro_output(self.m, 10)],
                output_allocation_mode="single_owner",
                **_zero_batch(),
            )

    def test_waste_follows_proportional_vs_single(self):
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
            output_allocation_mode="single_owner",
            single_allocation_owner_type="owned",
            **_zero_batch(),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[],
            dust_kg=Decimal("10"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            balance_return_lines=[],
        )
        waste_rows = self.db.scalars(select(ProcessingWasteAllocation)).all()
        self.assertEqual(len(waste_rows), 1)
        self.assertEqual(waste_rows[0].owner_type, InventoryOwnerType.owned)

    def test_single_owner_job_unchanged(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[_owned_input(self.m, 10)],
            output_lines=[],
            **_zero_batch(),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 8)],
            **_zero_batch(),
        )
        output_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        self.assertTrue(all(ln.owner_type == InventoryOwnerType.owned for ln in output_lines))

    def test_input_then_output_separate_batches(self):
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
            **PROPORTIONAL,
            **_zero_batch(),
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[],
            output_lines=[_raj_agro_output(self.m, 103)],
            **_zero_batch(),
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
                Inventory.customer_id == self.m["raghavendra"].id,
                Inventory.brand_id == self.m["raj_agro"].id,
            )
        )
        self.assertIsNotNone(owned_out)
        self.assertIsNotNone(jw_out)
        self.assertEqual(owned_out.bag_count + jw_out.bag_count, 103)

    def test_mixed_input_requires_allocation_mode(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        with self.assertRaisesRegex(ValueError, OUTPUT_ALLOCATION_MODE_REQUIRED_MSG):
            submit_batch(
                self.db,
                job.id,
                input_lines=[_owned_input(self.m, 85), _jw_input(self.m, 23)],
                output_lines=[],
                **_zero_batch(),
            )

    def test_external_mixed_batch_rejected(self):
        with self.assertRaisesRegex(ValueError, MIXED_EXTERNAL_OWNER_MSG):
            validate_processing_owner_mix(
                self.db,
                [
                    _owned_input(self.m, 10),
                    {
                        "location_id": self.m["location"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "bag_count": 5,
                        "loose_kg": Decimal("0"),
                        "owner_type": "job_work",
                        "customer_id": self.m["external"].id,
                    },
                ],
                is_first_input_batch=True,
            )

    def test_single_owner_not_in_job_input_rejected(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        other = Customer(name="Other JW", party_type=CustomerPartyType.internal)
        self.db.add(other)
        self.db.commit()
        with self.assertRaisesRegex(ValueError, SINGLE_OWNER_NOT_IN_JOB_INPUT_MSG):
            submit_batch(
                self.db,
                job.id,
                input_lines=[_owned_input(self.m, 85), _jw_input(self.m, 23)],
                output_lines=[],
                output_allocation_mode="single_owner",
                single_allocation_owner_type="job_work",
                single_allocation_customer_id=other.id,
                **_zero_batch(),
            )


if __name__ == "__main__":
    unittest.main()
