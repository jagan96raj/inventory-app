"""Spec v14.7 — consolidated processing powder."""
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import (
    BagType,
    BookSettings,
    Brand,
    Customer,
    CustomerPartyType,
    Inventory,
    InventoryOwnerType,
    Location,
    Product,
)
from app.services.accounts import update_book_settings
from app.services.job_work import create_job_work_order, receive_job_work
from app.services.operations import add_inventory
from app.services.processing import (
    POWDER_DEST_NOT_CONFIGURED_MSG,
    POWDER_OUTPUT_LINE_MSG,
    compute_processing_summary,
    create_job,
    load_processing_job,
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


def _seed_powder_settings(db: Session) -> dict:
    ensure_test_user(db)
    powder_product = Product(product_name="Powder")
    powder_brand = Brand(name="Powder")
    bajra = Product(product_name="Bajra")
    jowar = Product(product_name="Jowar")
    unclean = Brand(name="Unclean")
    raj_agro = Brand(name="Raj Agro")
    location = Location(name="Mill")
    loose = BagType(name="Loose", weight_per_bag_kg=Decimal("0"), is_loose=True)
    bag_50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    customer = Customer(name="JW Customer", party_type=CustomerPartyType.internal)
    db.add_all(
        [powder_product, powder_brand, bajra, jowar, unclean, raj_agro, location, loose, bag_50, customer]
    )
    db.flush()
    db.add(
        BookSettings(
            id=1,
            company_id=1,
            cash_opening_balance=Decimal("0"),
            cash_opening_balance_at=date.today(),
            powder_product_id=powder_product.id,
            powder_brand_id=powder_brand.id,
            powder_location_id=location.id,
            powder_bag_type_id=loose.id,
        )
    )
    db.commit()
    return {
        "powder_product": powder_product,
        "powder_brand": powder_brand,
        "bajra": bajra,
        "jowar": jowar,
        "unclean": unclean,
        "raj_agro": raj_agro,
        "location": location,
        "loose": loose,
        "bag_50": bag_50,
        "customer": customer,
    }


class ProcessingV147ConsolidatedPowderTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_powder_settings(self.db)

    def _add_stock(self, product: Product, brand: Brand, kg: Decimal) -> None:
        add_inventory(
            self.db,
            product.id,
            brand.id,
            self.m["location"].id,
            self.m["bag_50"].id,
            int(kg / Decimal("50")),
            Decimal("0"),
            owner_type=InventoryOwnerType.owned,
        )

    def _fresh_input(self, product: Product, brand: Brand, bags: int, **extra) -> dict:
        return {
            "location_id": self.m["location"].id,
            "bag_type_id": self.m["bag_50"].id,
            "bag_count": bags,
            "loose_kg": Decimal("0"),
            "owner_type": "owned",
            **extra,
        }

    def _submit_powder_only(self, product: Product, brand: Brand, powder_kg: Decimal) -> None:
        self._add_stock(product, brand, Decimal("1000"))
        from app.models.entities import ProcessingJob, ProcessingJobStatus

        existing = self.db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.input_product_id == product.id,
                ProcessingJob.input_brand_id == brand.id,
                ProcessingJob.status == ProcessingJobStatus.open,
            )
        )
        if existing:
            existing.status = ProcessingJobStatus.completed
            self.db.commit()
        job = create_job(self.db, input_product_id=product.id, input_brand_id=brand.id)
        submit_batch(
            self.db,
            job.id,
            input_lines=[self._fresh_input(product, brand, 20)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            powder_kg=powder_kg,
            miscellaneous_waste_kg=Decimal("0"),
        )

    def test_two_jobs_consolidate_to_single_inventory_row(self):
        self._submit_powder_only(self.m["bajra"], self.m["unclean"], Decimal("15"))
        self._submit_powder_only(self.m["jowar"], self.m["unclean"], Decimal("15"))

        row = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["powder_product"].id,
                Inventory.brand_id == self.m["powder_brand"].id,
                Inventory.location_id == self.m["location"].id,
                Inventory.owner_type == InventoryOwnerType.owned,
            )
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.total_quantity_kg, Decimal("30"))

    def test_powder_in_waste_not_output_by_brand(self):
        self._add_stock(self.m["bajra"], self.m["unclean"], Decimal("1000"))
        job = create_job(
            self.db, input_product_id=self.m["bajra"].id, input_brand_id=self.m["unclean"].id
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[self._fresh_input(self.m["bajra"], self.m["unclean"], 20)],
            output_lines=[
                {
                    "brand_id": self.m["raj_agro"].id,
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_50"].id,
                    "bag_count": 18,
                    "loose_kg": Decimal("0"),
                }
            ],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            powder_kg=Decimal("15"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        job = load_processing_job(self.db, job.id)
        summary = compute_processing_summary(job)
        self.assertEqual(summary["total_waste_kg"], Decimal("15"))
        brand_names = [row["brand_name"] for row in summary["output_by_brand"]]
        self.assertIn("Raj Agro", brand_names)
        self.assertNotIn("Powder", brand_names)

    def test_misc_lower_when_powder_recorded(self):
        self._add_stock(self.m["bajra"], self.m["unclean"], Decimal("1000"))
        job = create_job(
            self.db, input_product_id=self.m["bajra"].id, input_brand_id=self.m["unclean"].id
        )
        input_line = [self._fresh_input(self.m["bajra"], self.m["unclean"], 20)]
        output_line = [
            {
                "brand_id": self.m["raj_agro"].id,
                "location_id": self.m["location"].id,
                "bag_type_id": self.m["bag_50"].id,
                "bag_count": 18,
                "loose_kg": Decimal("0"),
            }
        ]
        submit_batch(
            self.db,
            job.id,
            input_lines=input_line,
            output_lines=output_line,
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            powder_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        misc_without = compute_processing_summary(load_processing_job(self.db, job.id))["total_misc_kg"]

        from app.models.entities import ProcessingJobStatus

        job.status = ProcessingJobStatus.completed
        self.db.commit()

        job2 = create_job(
            self.db, input_product_id=self.m["bajra"].id, input_brand_id=self.m["unclean"].id
        )
        self._add_stock(self.m["bajra"], self.m["unclean"], Decimal("1000"))
        submit_batch(
            self.db,
            job2.id,
            input_lines=input_line,
            output_lines=output_line,
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            powder_kg=Decimal("15"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        misc_with = compute_processing_summary(load_processing_job(self.db, job2.id))["total_misc_kg"]
        self.assertLess(misc_with, misc_without)

    def test_powder_output_brand_line_rejected(self):
        self._add_stock(self.m["bajra"], self.m["unclean"], Decimal("1000"))
        job = create_job(
            self.db, input_product_id=self.m["bajra"].id, input_brand_id=self.m["unclean"].id
        )
        with self.assertRaises(ValueError) as ctx:
            submit_batch(
                self.db,
                job.id,
                input_lines=[self._fresh_input(self.m["bajra"], self.m["unclean"], 20)],
                output_lines=[
                    {
                        "brand_id": self.m["powder_brand"].id,
                        "location_id": self.m["location"].id,
                        "bag_type_id": self.m["loose"].id,
                        "bag_count": 0,
                        "loose_kg": Decimal("15"),
                    }
                ],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                powder_kg=Decimal("0"),
                miscellaneous_waste_kg=Decimal("0"),
            )
        self.assertIn(POWDER_OUTPUT_LINE_MSG, str(ctx.exception))

    def test_powder_without_book_settings_rejected(self):
        update_book_settings(
            self.db,
            1,
            {
                "powder_product_id": None,
                "powder_brand_id": None,
                "powder_location_id": None,
                "powder_bag_type_id": None,
            },
        )
        self._add_stock(self.m["bajra"], self.m["unclean"], Decimal("1000"))
        job = create_job(
            self.db, input_product_id=self.m["bajra"].id, input_brand_id=self.m["unclean"].id
        )
        with self.assertRaises(ValueError) as ctx:
            submit_batch(
                self.db,
                job.id,
                input_lines=[self._fresh_input(self.m["bajra"], self.m["unclean"], 20)],
                output_lines=[],
                balance_return_lines=[],
                dust_kg=Decimal("0"),
                stone_kg=Decimal("0"),
                sack_weight_waste_kg=Decimal("0"),
                powder_kg=Decimal("5"),
                miscellaneous_waste_kg=Decimal("0"),
            )
        self.assertIn(POWDER_DEST_NOT_CONFIGURED_MSG, str(ctx.exception))

    def test_dust_does_not_create_inventory(self):
        self._add_stock(self.m["bajra"], self.m["unclean"], Decimal("1000"))
        job = create_job(
            self.db, input_product_id=self.m["bajra"].id, input_brand_id=self.m["unclean"].id
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[self._fresh_input(self.m["bajra"], self.m["unclean"], 20)],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("3"),
            stone_kg=Decimal("2"),
            sack_weight_waste_kg=Decimal("1"),
            powder_kg=Decimal("0"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        powder_rows = self.db.scalars(
            select(Inventory).where(Inventory.product_id == self.m["powder_product"].id)
        ).all()
        self.assertEqual(len(powder_rows), 0)

    def test_mixed_owner_job_powder_splits_by_owner_proportion(self):
        order = create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["bajra"].id,
                    "brand_id": self.m["unclean"].id,
                    "bag_type_id": self.m["bag_50"].id,
                    "ordered_bags": 100,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=order.lines[0].id,
            location_id=self.m["location"].id,
            bag_count=10,
            loose_kg=Decimal("0"),
        )
        self._add_stock(self.m["bajra"], self.m["unclean"], Decimal("500"))
        job = create_job(
            self.db, input_product_id=self.m["bajra"].id, input_brand_id=self.m["unclean"].id
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                self._fresh_input(self.m["bajra"], self.m["unclean"], 5),
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_50"].id,
                    "bag_count": 5,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["customer"].id,
                },
            ],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            powder_kg=Decimal("0"),
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
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            powder_kg=Decimal("10"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        owned_row = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["powder_product"].id,
                Inventory.brand_id == self.m["powder_brand"].id,
                Inventory.owner_type == InventoryOwnerType.owned,
            )
        )
        self.assertIsNotNone(owned_row)
        self.assertEqual(owned_row.total_quantity_kg, Decimal("5"))
        jw_row = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["powder_product"].id,
                Inventory.brand_id == self.m["powder_brand"].id,
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.customer_id == self.m["customer"].id,
            )
        )
        self.assertIsNotNone(jw_row)
        self.assertEqual(jw_row.total_quantity_kg, Decimal("5"))

    def test_separate_jobs_powder_splits_by_input_owner(self):
        """Owned Bajra job and JW Jowar job post to separate powder inventory rows."""
        order = create_job_work_order(
            self.db,
            customer_id=self.m["customer"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["jowar"].id,
                    "brand_id": self.m["unclean"].id,
                    "bag_type_id": self.m["bag_50"].id,
                    "ordered_bags": 100,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=order.lines[0].id,
            location_id=self.m["location"].id,
            bag_count=20,
            loose_kg=Decimal("0"),
        )
        self._add_stock(self.m["jowar"], self.m["unclean"], Decimal("1000"))
        jw_job = create_job(
            self.db, input_product_id=self.m["jowar"].id, input_brand_id=self.m["unclean"].id
        )
        submit_batch(
            self.db,
            jw_job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_50"].id,
                    "bag_count": 10,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["customer"].id,
                }
            ],
            output_lines=[],
            balance_return_lines=[],
            dust_kg=Decimal("0"),
            stone_kg=Decimal("0"),
            sack_weight_waste_kg=Decimal("0"),
            powder_kg=Decimal("12"),
            miscellaneous_waste_kg=Decimal("0"),
        )
        self._submit_powder_only(self.m["bajra"], self.m["unclean"], Decimal("15"))

        owned_row = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["powder_product"].id,
                Inventory.owner_type == InventoryOwnerType.owned,
            )
        )
        jw_row = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["powder_product"].id,
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.customer_id == self.m["customer"].id,
            )
        )
        self.assertIsNotNone(owned_row)
        self.assertEqual(owned_row.total_quantity_kg, Decimal("15"))
        self.assertIsNotNone(jw_row)
        self.assertEqual(jw_row.total_quantity_kg, Decimal("12"))


if __name__ == "__main__":
    unittest.main()
