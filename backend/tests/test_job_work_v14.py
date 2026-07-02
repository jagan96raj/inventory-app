"""Spec v14.0 — Job Work + owner-tagged inventory tests."""
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Bill,
    BillLine,
    BillType,
    Brand,
    Customer,
    CustomerPartyType,
    FulfillmentType,
    Inventory,
    InventoryOwnerType,
    JobWorkLine,
    JobWorkOrder,
    Location,
    Product,
    StockSource,
    User,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
from app.services.fulfillment import create_fulfillment, serialize_fulfillment_line
from app.services.job_work import create_job_work_order, receive_job_work, void_job_work_receipt
from app.services.operations import add_inventory
from app.services.processing import create_job, submit_batch
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_kwargs, idem_void_headers
from tests.processing_test_helpers import PROPORTIONAL_ALLOCATION

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed_masters(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    internal = Customer(name="Murugan Traders", party_type=CustomerPartyType.internal)
    external = Customer(name="Stranger Co", party_type=CustomerPartyType.external)
    db.add_all([product, brand, location, bag_type, internal, external])
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "internal": internal,
        "external": external,
    }


class JobWorkV14Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed_masters(self.db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_migration_existing_inventory_is_owned(self):
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["brand"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            2,
            Decimal("0"),
        )
        inv = self.db.scalar(select(Inventory))
        self.assertIsNotNone(inv)
        self.assertEqual(inv.owner_type, InventoryOwnerType.owned)
        self.assertIsNone(inv.customer_id)

    def test_jw_receive_adds_job_work_inventory_no_balance_change(self):
        order = create_job_work_order(
            self.db,
            customer_id=self.m["internal"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 10,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        credit_before = self.m["internal"].credit_balance
        debit_before = self.m["internal"].debit_balance
        line = order.lines[0]
        receive_job_work(
            self.db,
            line_id=line.id,
            location_id=self.m["location"].id,
            bag_count=4,
            loose_kg=Decimal("0"),
        )
        self.db.refresh(self.m["internal"])
        self.assertEqual(self.m["internal"].credit_balance, credit_before)
        self.assertEqual(self.m["internal"].debit_balance, debit_before)

        inv = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.customer_id == self.m["internal"].id,
            )
        )
        self.assertIsNotNone(inv)
        self.assertEqual(inv.bag_count, 4)

    def test_void_jw_receipt_reverses_stock(self):
        order = create_job_work_order(
            self.db,
            customer_id=self.m["internal"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 5,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receipt = receive_job_work(
            self.db,
            line_id=order.lines[0].id,
            location_id=self.m["location"].id,
            bag_count=2,
            loose_kg=Decimal("0"),
        )
        void_job_work_receipt(self.db, receipt.id)
        inv = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.customer_id == self.m["internal"].id,
            )
        )
        self.assertTrue(inv is None or inv.bag_count == 0)

    def test_mixed_80_20_batch_proportional_split(self):
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["brand"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            2,
            Decimal("0"),
        )
        create_job_work_order(
            self.db,
            customer_id=self.m["internal"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 8,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=self.db.scalar(select(JobWorkLine)).id,
            location_id=self.m["location"].id,
            bag_count=8,
            loose_kg=Decimal("0"),
        )
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["brand"].id,
        )
        submit_batch(
            self.db,
            job.id,
            input_lines=[
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 8,
                    "loose_kg": Decimal("0"),
                    "owner_type": "job_work",
                    "customer_id": self.m["internal"].id,
                },
                {
                    "location_id": self.m["location"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "bag_count": 2,
                    "loose_kg": Decimal("0"),
                    "owner_type": "owned",
                },
            ],
            output_lines=[
                {
                    "brand_id": self.m["brand"].id,
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
            miscellaneous_waste_kg=Decimal("1"),
            **PROPORTIONAL_ALLOCATION,
        )
        owned_out = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.owned,
                Inventory.customer_id.is_(None),
                Inventory.product_id == self.m["product"].id,
            )
        )
        jw_out = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.customer_id == self.m["internal"].id,
                Inventory.product_id == self.m["product"].id,
            )
        )
        self.assertIsNotNone(owned_out)
        self.assertIsNotNone(jw_out)
        self.assertEqual(owned_out.total_quantity_kg, Decimal("100.000"))
        self.assertEqual(jw_out.total_quantity_kg, Decimal("400.000"))

    def test_external_mixed_batch_rejected(self):
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["brand"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            5,
            Decimal("0"),
        )
        receive_job_work(
            self.db,
            line_id=create_job_work_order(
                self.db,
                customer_id=self.m["external"].id,
                job_date=date.today(),
                notes=None,
                lines=[
                    {
                        "product_id": self.m["product"].id,
                        "brand_id": self.m["brand"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "ordered_bags": 5,
                        "ordered_loose_kg": Decimal("0"),
                    }
                ],
            ).lines[0].id,
            location_id=self.m["location"].id,
            bag_count=5,
            loose_kg=Decimal("0"),
        )
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["brand"].id,
        )
        with self.assertRaises(ValueError):
            submit_batch(
                self.db,
                job.id,
                input_lines=[
                    {
                        "location_id": self.m["location"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "bag_count": 5,
                        "loose_kg": Decimal("0"),
                        "owner_type": "job_work",
                        "customer_id": self.m["external"].id,
                    },
                    {
                        "location_id": self.m["location"].id,
                        "bag_type_id": self.m["bag_type"].id,
                        "bag_count": 1,
                        "loose_kg": Decimal("0"),
                        "owner_type": "owned",
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

    def test_fulfillment_queue_shows_job_work_stock_on_hand(self):
        order = create_job_work_order(
            self.db,
            customer_id=self.m["internal"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 10,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=order.lines[0].id,
            location_id=self.m["location"].id,
            bag_count=6,
            loose_kg=Decimal("0"),
        )
        jw_bill_out = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.sales,
                customer_id=self.m["internal"].id,
                location_id=self.m["location"].id,
                lines=[
                    BillLineIn(
                        product_id=self.m["product"].id,
                        brand_id=self.m["brand"].id,
                        bag_type_id=self.m["bag_type"].id,
                        ordered_bags=2,
                        ordered_loose_kg=Decimal("0"),
                        rate_per_kg=Decimal("1"),
                        stock_source="job_work",
                    )
                ],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        bill = self.db.scalar(
            select(Bill)
            .where(Bill.id == jw_bill_out.id)
            .options(
                joinedload(Bill.location),
                joinedload(Bill.customer),
                joinedload(Bill.lines).joinedload(BillLine.product),
                joinedload(Bill.lines).joinedload(BillLine.brand),
                joinedload(Bill.lines).joinedload(BillLine.bag_type),
            )
        )
        payload = serialize_fulfillment_line(self.db, bill, bill.lines[0])
        self.assertEqual(payload["stock_bags"], 6)
        self.assertEqual(Decimal(payload["stock_kg"]), Decimal("300"))

    def test_sales_deliver_owned_vs_job_work_subtracts_correct_rows(self):
        add_inventory(
            self.db,
            self.m["product"].id,
            self.m["brand"].id,
            self.m["location"].id,
            self.m["bag_type"].id,
            5,
            Decimal("0"),
        )
        order = create_job_work_order(
            self.db,
            customer_id=self.m["internal"].id,
            job_date=date.today(),
            notes=None,
            lines=[
                {
                    "product_id": self.m["product"].id,
                    "brand_id": self.m["brand"].id,
                    "bag_type_id": self.m["bag_type"].id,
                    "ordered_bags": 5,
                    "ordered_loose_kg": Decimal("0"),
                }
            ],
        )
        receive_job_work(
            self.db,
            line_id=order.lines[0].id,
            location_id=self.m["location"].id,
            bag_count=5,
            loose_kg=Decimal("0"),
        )

        owned_bill = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.sales,
                customer_id=self.m["internal"].id,
                location_id=self.m["location"].id,
                lines=[
                    BillLineIn(
                        product_id=self.m["product"].id,
                        brand_id=self.m["brand"].id,
                        bag_type_id=self.m["bag_type"].id,
                        ordered_bags=1,
                        ordered_loose_kg=Decimal("0"),
                        rate_per_kg=Decimal("10"),
                        stock_source="owned",
                    )
                ],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        jw_bill = create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.sales,
                customer_id=self.m["internal"].id,
                location_id=self.m["location"].id,
                lines=[
                    BillLineIn(
                        product_id=self.m["product"].id,
                        brand_id=self.m["brand"].id,
                        bag_type_id=self.m["bag_type"].id,
                        ordered_bags=1,
                        ordered_loose_kg=Decimal("0"),
                        rate_per_kg=Decimal("10"),
                        stock_source="job_work",
                    )
                ],
            ),
            db=self.db,
            **idem_kwargs(),
        )
        create_fulfillment(
            self.db,
            bill_line_id=owned_bill.lines[0].id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("50"),
            bag_count=1,
            loose_kg=Decimal("0"),
            location_id=self.m["location"].id,
            expected_version=owned_bill.version,
        )
        create_fulfillment(
            self.db,
            bill_line_id=jw_bill.lines[0].id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("50"),
            bag_count=1,
            loose_kg=Decimal("0"),
            location_id=self.m["location"].id,
            expected_version=jw_bill.version,
        )
        owned_inv = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.owned,
                Inventory.customer_id.is_(None),
            )
        )
        jw_inv = self.db.scalar(
            select(Inventory).where(
                Inventory.owner_type == InventoryOwnerType.job_work,
                Inventory.customer_id == self.m["internal"].id,
            )
        )
        self.assertEqual(owned_inv.bag_count, 4)
        self.assertEqual(jw_inv.bag_count, 4)


if __name__ == "__main__":
    unittest.main()
