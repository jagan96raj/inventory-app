"""Spec v14.6 — superseded by v14.6.1 (allocation on input batch). Regression coverage."""
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
    InventoryOwnerType,
    JobWorkLine,
    ProcessingOutputLine,
    Product,
    Location,
)
from app.services.job_work import create_job_work_order, receive_job_work
from app.services.operations import add_inventory
from app.services.processing import (
    OUTPUT_ALLOCATION_LOCKED_MSG,
    create_job,
    submit_batch,
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
    db.add_all([product, unclean, raj_agro, location, bag_type, raghavendra])
    db.commit()
    return {
        "product": product,
        "unclean": unclean,
        "raj_agro": raj_agro,
        "location": location,
        "bag_type": bag_type,
        "raghavendra": raghavendra,
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


def _zero_batch() -> dict:
    return {
        "balance_return_lines": [],
        "dust_kg": Decimal("0"),
        "stone_kg": Decimal("0"),
        "sack_weight_waste_kg": Decimal("0"),
        "powder_kg": Decimal("0"),
        "miscellaneous_waste_kg": Decimal("0"),
    }


class ProcessingV146RegressionTests(unittest.TestCase):
    """v14.6 output-batch allocation superseded; ensure stored mode drives output splits."""

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

    def _mixed_input_job_proportional(self):
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
        return job

    def test_proportional_splits_103_bags(self):
        job = self._mixed_input_job_proportional()
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

    def test_single_owner_default_highest_owned(self):
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
        self.assertTrue(all(ln.owner_type == InventoryOwnerType.owned for ln in output_lines))

    def test_allocation_locked_on_output_body_change(self):
        job = self._mixed_input_job_proportional()
        with self.assertRaisesRegex(ValueError, OUTPUT_ALLOCATION_LOCKED_MSG):
            submit_batch(
                self.db,
                job.id,
                input_lines=[],
                output_lines=[_raj_agro_output(self.m, 10)],
                output_allocation_mode="single_owner",
                **_zero_batch(),
            )


if __name__ == "__main__":
    unittest.main()
