"""Spec v14.4 — mixed processing integer bag split vs kg split."""
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
    ProcessingBatch,
    ProcessingOutputLine,
    ProcessingWasteAllocation,
    Product,
    Location,
)
from app.services.job_work import create_job_work_order, receive_job_work
from app.services.operations import add_inventory
from app.services.owner_allocation import proportional_split_bags, proportional_split_kg
from app.services.processing import create_job, submit_batch
from tests.idempotency_helpers import ensure_test_user
from tests.processing_test_helpers import PROPORTIONAL_ALLOCATION


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed_bajra_mixed(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Bajra")
    unclean = Brand(name="Unclean")
    raj_agro = Brand(name="Raj Agro")
    location = Location(name="Unit")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    loose_type = BagType(name="Loose", weight_per_bag_kg=Decimal("1"), is_loose=True)
    internal = Customer(name="Raghavendra", party_type=CustomerPartyType.internal)
    db.add_all([product, unclean, raj_agro, location, bag_type, loose_type, internal])
    db.commit()
    return {
        "product": product,
        "unclean": unclean,
        "raj_agro": raj_agro,
        "location": location,
        "bag_type": bag_type,
        "loose_type": loose_type,
        "internal": internal,
    }


class ProportionalSplitBagsTests(unittest.TestCase):
    def test_113_bags_90_28_input_weights(self):
        weights = {
            ("owned", None): Decimal("4500"),
            ("job_work", 1): Decimal("1400"),
        }
        split = proportional_split_bags(113, weights)
        self.assertEqual(split[("owned", None)], 86)
        self.assertEqual(split[("job_work", 1)], 27)
        self.assertEqual(sum(split.values()), 113)

    def test_90_kg_loose_split(self):
        weights = {
            ("owned", None): Decimal("4500"),
            ("job_work", 1): Decimal("1400"),
        }
        split = proportional_split_kg(Decimal("90"), weights)
        self.assertEqual(split[("owned", None)], Decimal("68.644"))
        self.assertEqual(split[("job_work", 1)], Decimal("21.356"))
        self.assertEqual(sum(split.values()), Decimal("90"))


class ProcessingV144MixedBagSplitTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_bajra_mixed(self.db)

    def _stock_owned(self, bags: int) -> None:
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["unclean"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            bags,
            Decimal("0"),
        )

    def _stock_jw(self, bags: int) -> None:
        order = create_job_work_order(
            self.db,
            customer_id=self.m["internal"].id,
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
        receive_job_work(
            self.db,
            line_id=self.db.scalar(select(JobWorkLine)).id,
            location_id=self.m["location"].id,
            bag_count=bags,
            loose_kg=Decimal("0"),
        )

    def _mixed_job(self):
        self._stock_owned(90)
        self._stock_jw(28)
        return create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["unclean"].id,
        )

    def test_mixed_113_bag_output_integer_split(self):
        job = self._mixed_job()
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 90,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 28,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["internal"].id,
                },
            ],
            output_lines=[
                {
                    "brand_id": self.m["raj_agro"].id,
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 113,
                    "loose_kg": Decimal("0"),
                }
            ],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL_ALLOCATION,
        )
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
                Inventory.customer_id == self.m["internal"].id,
                Inventory.brand_id == self.m["raj_agro"].id,
            )
        )
        self.assertIsNotNone(owned_out)
        self.assertIsNotNone(jw_out)
        self.assertEqual(owned_out.bag_count, 86)
        self.assertEqual(jw_out.bag_count, 27)
        self.assertEqual(owned_out.loose_kg, Decimal("0"))
        self.assertEqual(jw_out.loose_kg, Decimal("0"))
        self.assertEqual(owned_out.total_quantity_kg, Decimal("4300.000"))
        self.assertEqual(jw_out.total_quantity_kg, Decimal("1350.000"))

    def test_mixed_loose_balance_kg_split(self):
        job = self._mixed_job()
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 90,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 28,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["internal"].id,
                },
            ],
            output_lines=[],
            balance_return_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["loose_type"].id,
                    "bag_count": 0,
                    "loose_kg": Decimal("90"),
                }
            ],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL_ALLOCATION,
        )
        owned_bal = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.owned,
                Inventory.customer_id.is_(None),
                Inventory.bag_type_id == self.m["loose_type"].id,
            )
        )
        jw_bal = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.customer_id == self.m["internal"].id,
                Inventory.bag_type_id == self.m["loose_type"].id,
            )
        )
        self.assertIsNotNone(owned_bal)
        self.assertIsNotNone(jw_bal)
        self.assertEqual(owned_bal.loose_kg, Decimal("68.644"))
        self.assertEqual(jw_bal.loose_kg, Decimal("21.356"))
        self.assertEqual(
            owned_bal.loose_kg + jw_bal.loose_kg,
            Decimal("90"),
        )

    def test_owned_only_unchanged(self):
        self._stock_owned(10)
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
                    "bag_count": 10,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                }
            ],
            output_lines=[
                {
                    "brand_id": self.m["raj_agro"].id,
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 10,
                    "loose_kg": Decimal("0"),
                }
            ],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL_ALLOCATION,
        )
        owned = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.owned,
                Inventory.brand_id == self.m["raj_agro"].id,
            )
        )
        jw = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.job_work,
            )
        )
        self.assertIsNotNone(owned)
        self.assertEqual(owned.bag_count, 10)
        self.assertIsNone(jw)

    def test_mixed_waste_kg_split(self):
        job = self._mixed_job()
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 90,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 28,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["internal"].id,
                },
            ],
            output_lines=[
                {
                    "brand_id": self.m["raj_agro"].id,
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 9,
                    "loose_kg": Decimal("0"),
                }
            ],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("30"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("20"),
            **PROPORTIONAL_ALLOCATION,
        )
        batch = self.db.scalar(select(ProcessingBatch))
        waste_rows = self.db.scalars(
            select(ProcessingWasteAllocation).where(
                ProcessingWasteAllocation.batch_id == batch.id
            )
        ).all()
        self.assertEqual(len(waste_rows), 2)
        stone_total = sum(r.stone_kg for r in waste_rows)
        misc_total = sum(r.miscellaneous_waste_kg for r in waste_rows)
        self.assertEqual(stone_total, Decimal("30"))
        self.assertEqual(misc_total, Decimal("20"))

    def test_mixed_split_output_only_batch(self):
        """UI workflow: input batch then separate output batch (empty input_lines)."""
        job = self._mixed_job()
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 90,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 28,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["internal"].id,
                },
            ],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL_ALLOCATION,
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
                    "bag_count": 113,
                    "loose_kg": Decimal("0"),
                }
            ],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL_ALLOCATION,
        )
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
                Inventory.customer_id == self.m["internal"].id,
                Inventory.brand_id == self.m["raj_agro"].id,
            )
        )
        self.assertIsNotNone(owned_out)
        self.assertIsNotNone(jw_out)
        self.assertEqual(owned_out.bag_count, 86)
        self.assertEqual(jw_out.bag_count, 27)

        out_lines = self.db.scalars(select(ProcessingOutputLine)).all()
        self.assertEqual(len(out_lines), 2)
        owned_lines = [ln for ln in out_lines if ln.owner_type == InventoryOwnerType.owned]
        jw_lines = [ln for ln in out_lines if ln.owner_type == InventoryOwnerType.job_work]
        self.assertEqual(sum(ln.bag_count for ln in owned_lines), 86)
        self.assertEqual(sum(ln.bag_count for ln in jw_lines), 27)

    def test_mixed_waste_split_output_only_batch(self):
        job = self._mixed_job()
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 90,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 28,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["internal"].id,
                },
            ],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
            **PROPORTIONAL_ALLOCATION,
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
            **PROPORTIONAL_ALLOCATION,
        )
        batch = self.db.scalar(
            select(ProcessingBatch).order_by(ProcessingBatch.id.desc())
        )
        waste_rows = self.db.scalars(
            select(ProcessingWasteAllocation).where(
                ProcessingWasteAllocation.batch_id == batch.id
            )
        ).all()
        self.assertEqual(len(waste_rows), 2)
        stone_total = sum(r.stone_kg for r in waste_rows)
        misc_total = sum(r.miscellaneous_waste_kg for r in waste_rows)
        self.assertEqual(stone_total, Decimal("44"))
        self.assertEqual(misc_total, Decimal("26"))


if __name__ == "__main__":
    unittest.main()
