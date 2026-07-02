"""Spec v14.4.2 — enum-safe job_work owner detection + multi-owner split."""
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.utils.time import utc_now

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
    ProcessingBatch,
    ProcessingInputLine,
    ProcessingJob,
    ProcessingOutputLine,
    ProcessingWasteAllocation,
    Product,
    Location,
)
from app.services.job_work import create_job_work_order, receive_job_work
from app.services.operations import add_inventory
from app.services.processing import (
    MIXED_EXTERNAL_OWNER_MSG,
    _owner_key_from_stored_input,
    _owner_weights_for_job_allocation,
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


def _seed_three_owner(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Bajra")
    unclean = Brand(name="Unclean")
    raj_agro = Brand(name="Raj Agro")
    location = Location(name="Unit")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    raghavendra = Customer(name="Sri Raghavendra", party_type=CustomerPartyType.internal)
    murugan = Customer(name="Sri Murugan", party_type=CustomerPartyType.internal)
    external = Customer(name="External Co", party_type=CustomerPartyType.external)
    db.add_all([product, unclean, raj_agro, location, bag_type, raghavendra, murugan, external])
    db.commit()
    return {
        "product": product,
        "unclean": unclean,
        "raj_agro": raj_agro,
        "location": location,
        "bag_type": bag_type,
        "raghavendra": raghavendra,
        "murugan": murugan,
        "external": external,
    }


class OwnerKeyEnumCoercionTests(unittest.TestCase):
    def test_owner_key_accepts_string_job_work(self):
        line = SimpleNamespace(owner_type="job_work", customer_id=42)
        self.assertEqual(_owner_key_from_stored_input(line), ("job_work", 42))

    def test_owner_key_accepts_enum_job_work(self):
        line = SimpleNamespace(
            owner_type=InventoryOwnerType.job_work,
            customer_id=42,
        )
        self.assertEqual(_owner_key_from_stored_input(line), ("job_work", 42))

    def test_owner_key_job_work_missing_customer_raises(self):
        line = SimpleNamespace(owner_type="job_work", customer_id=None)
        with self.assertRaises(ValueError):
            _owner_key_from_stored_input(line)


class OwnerWeightsAllocationTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_three_owner(self.db)

    def _job_with_stored_inputs(self) -> ProcessingJob:
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        batch = ProcessingBatch(job_id=job.id, operation_at=utc_now())
        self.db.add(batch)
        self.db.flush()
        owned_line = ProcessingInputLine(
            batch_id=batch.id,
            location_id=self.m["location"].id,
            bag_type_id=self.m["bag_type"].id,
            bag_count=85,
            loose_kg=Decimal("0"),
            quantity_kg=Decimal("4250"),
            line_index=0,
            owner_type=InventoryOwnerType.owned,
            customer_id=None,
        )
        jw_line = ProcessingInputLine(
            batch_id=batch.id,
            location_id=self.m["location"].id,
            bag_type_id=self.m["bag_type"].id,
            bag_count=23,
            loose_kg=Decimal("0"),
            quantity_kg=Decimal("1150"),
            line_index=1,
            owner_type="job_work",
            customer_id=self.m["raghavendra"].id,
        )
        self.db.add_all([owned_line, jw_line])
        self.db.commit()
        return self.db.get(ProcessingJob, job.id)

    def test_owner_weights_two_owners_with_string_job_work(self):
        job = self._job_with_stored_inputs()
        weights = _owner_weights_for_job_allocation(self.db, job, [])
        self.assertEqual(len(weights), 2)
        self.assertGreater(weights[("owned", None)], Decimal("0"))
        self.assertGreater(weights[("job_work", self.m["raghavendra"].id)], Decimal("0"))


class ProcessingV1442TwoOwnerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_three_owner(self.db)
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
            bag_count=28,
            loose_kg=Decimal("0"),
        )

    def test_two_owner_output_only_batch_splits(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 85,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 28,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["raghavendra"].id,
                },
            ],
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
            output_lines=[
                {
                    "brand_id": self.m["raj_agro"].id,
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 103,
                    "loose_kg": Decimal("0"),
                }
            ],
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

        owned_out = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.owned,
                Inventory.customer_id.is_(None),
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
        self.assertGreater(owned_out.bag_count, 0)
        self.assertGreater(jw_out.bag_count, 0)


class ProcessingV1442ThreeOwnerTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_three_owner(self.db)
        add_inventory(self.db, self.m["product"].id, self.m["unclean"].id, self.m["location"].id, self.m["bag_type"].id, 85, Decimal("0"))

        def jw_stock(customer: Customer, bags: int) -> None:
            order = create_job_work_order(
                self.db,
                customer_id=customer.id,
                job_date=date.today(),
                notes=None,
                lines=[
                    {
                        "product_id": self.m["product"].id,
                        "brand_id": self.m["unclean"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "ordered_bags": bags,
                        "ordered_loose_kg": Decimal("0"),
                    }
                ],
            )
            line_id = self.db.scalars(
                select(JobWorkLine).where(JobWorkLine.order_id == order.id)
            ).one().id
            receive_job_work(
                self.db,
                line_id=line_id,
                location_id=self.m["location"].id,
                bag_count=bags,
                loose_kg=Decimal("0"),
            )

        jw_stock(self.m["raghavendra"], 40)
        jw_stock(self.m["murugan"], 23)

    def test_three_owner_bag_split(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 85,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 40,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["raghavendra"].id,
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 23,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["murugan"].id,
                },
            ],
            output_lines=[
                {
                    "brand_id": self.m["raj_agro"].id,
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 103,
                    "loose_kg": Decimal("0"),
                }
            ],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL,
        )
        output_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        owner_groups = {(ln.owner_type, ln.customer_id) for ln in output_lines}
        self.assertEqual(len(owner_groups), 3)
        self.assertEqual(sum(ln.bag_count for ln in output_lines), 103)
        for ln in output_lines:
            self.assertGreater(ln.bag_count, 0)

    def test_three_owner_waste_split_after_input_only(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 85,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 40,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["raghavendra"].id,
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 23,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["murugan"].id,
                },
            ],
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
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("44"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("26"),
        )
        waste_rows = self.db.scalars(select(ProcessingWasteAllocation)).all()
        self.assertEqual(len(waste_rows), 3)
        self.assertEqual(sum(r.stone_kg for r in waste_rows), Decimal("44"))
        self.assertEqual(sum(r.miscellaneous_waste_kg for r in waste_rows), Decimal("26"))


class ProcessingV1442RegressionTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_three_owner(self.db)

    def test_external_mixed_batch_rejected(self):
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
