"""Spec v14.8 — processing batch void."""
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    BookSettings,
    Brand,
    Inventory,
    Location,
    ProcessingBatch,
    ProcessingJobStatus,
    Product,
)
from app.services.idempotency import IDEMPOTENCY_KEY_HEADER
from app.services.operations import OPERATION_ALREADY_VOIDED_MSG, add_inventory, create_bag_change
from app.services.processing import (
    complete_job,
    compute_processing_summary,
    create_job,
    load_processing_job,
    submit_batch,
    void_processing_batch,
)
from app.services.processing.constants import LATER_REPROCESS_VOID_MSG
from tests.idempotency_helpers import TEST_USER, TEST_VOID_AUTH_PASSWORD, ensure_test_user, idem_void_headers


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
    brand = Brand(name="Unclean")
    out_brand = Brand(name="Raj Agro")
    location = Location(name="Mill")
    bag_50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    bag_loose = BagType(name="Loose", weight_per_bag_kg=Decimal("0"), is_loose=True)
    db.add_all([product, brand, out_brand, location, bag_50, bag_loose])
    db.flush()
    db.add(
        BookSettings(
            id=1,
            company_id=1,
            cash_opening_balance=Decimal("0"),
            cash_opening_balance_at=date.today(),
        )
    )
    add_inventory(
        db,
        product.id,
        brand.id,
        location.id,
        bag_50.id,
        20,
        Decimal("0"),
    )
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "out_brand": out_brand,
        "location": location,
        "bag_50": bag_50,
        "bag_loose": bag_loose,
    }


def _zero_batch() -> dict:
    return {
        "input_lines": [],
        "output_lines": [],
        "balance_return_lines": [],
        "dust_kg": Decimal("0"),
        "stone_kg": Decimal("0"),
        "sack_weight_waste_kg": Decimal("0"),
        "powder_kg": Decimal("0"),
        "miscellaneous_waste_kg": Decimal("0"),
    }


def _input_line(m: dict, bags: int = 10) -> dict:
    return {
        "location_id": m["location"].id,
        "bag_type_id": m["bag_50"].id,
        "bag_count": bags,
        "loose_kg": Decimal("0"),
        "owner_type": "owned",
    }


def _output_line(m: dict, bags: int = 8) -> dict:
    return {
        "brand_id": m["out_brand"].id,
        "location_id": m["location"].id,
        "bag_type_id": m["bag_50"].id,
        "bag_count": bags,
        "loose_kg": Decimal("0"),
    }


class ProcessingVoidV148Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

    def tearDown(self):
        self.db.close()

    def _create_job(self):
        return create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["brand"].id,
        )

    def test_void_input_batch_restores_stock(self):
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 10)]
        submit_batch(self.db, job.id, **payload)
        batch = self.db.scalars(select(ProcessingBatch).where(ProcessingBatch.job_id == job.id)).one()
        inv_before_void = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["product"].id,
                Inventory.brand_id == self.m["brand"].id,
            )
        )
        self.assertEqual(inv_before_void.bag_count, 10)

        void_processing_batch(self.db, batch.id)

        inv_after = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["product"].id,
                Inventory.brand_id == self.m["brand"].id,
            )
        )
        self.assertEqual(inv_after.bag_count, 20)
        job = load_processing_job(self.db, job.id)
        self.assertEqual(compute_processing_summary(job)["batch_count"], 0)

    def test_void_output_batch_blocked_when_stock_consumed(self):
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 10)]
        submit_batch(self.db, job.id, **payload)
        out_payload = _zero_batch()
        out_payload["output_lines"] = [_output_line(self.m, 8)]
        submit_batch(self.db, job.id, **out_payload)
        batch = self.db.scalars(
            select(ProcessingBatch).where(ProcessingBatch.job_id == job.id).order_by(ProcessingBatch.id.desc())
        ).first()
        assert batch is not None

        from app.services.operations import subtract_inventory

        subtract_inventory(
            self.db,
            self.m["product"].id,
            self.m["out_brand"].id,
            self.m["location"].id,
            self.m["bag_50"].id,
            8,
            Decimal("0"),
        )
        self.db.commit()

        with self.assertRaises(ValueError) as ctx:
            void_processing_batch(self.db, batch.id)
        self.assertIn("output", str(ctx.exception).lower())
        self.assertIn("Raj Agro", str(ctx.exception))

    def test_void_blocked_when_later_batch_reprocessed_balance(self):
        """Balance-return kg consumed by a later reprocess must not look like missing polish stock."""
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 10)]
        payload["balance_return_lines"] = [
            {
                "location_id": self.m["location"].id,
                "bag_type_id": self.m["bag_loose"].id,
                "bag_count": 0,
                "loose_kg": Decimal("50"),
            }
        ]
        submit_batch(self.db, job.id, **payload)
        batch1 = self.db.scalars(select(ProcessingBatch).where(ProcessingBatch.job_id == job.id)).one()

        reprocess = _zero_batch()
        reprocess["input_lines"] = [
            {
                "location_id": self.m["location"].id,
                "bag_type_id": self.m["bag_loose"].id,
                "bag_count": 0,
                "loose_kg": Decimal("50"),
                "owner_type": "owned",
                "input_source": "balance_reprocess",
            }
        ]
        submit_batch(self.db, job.id, **reprocess)

        with self.assertRaises(ValueError) as ctx:
            void_processing_batch(self.db, batch1.id)
        self.assertEqual(str(ctx.exception), LATER_REPROCESS_VOID_MSG)

    def test_void_grader_rejection_loose_plus_balance_return_loose(self):
        """Batch 15: grader rejection 155 + Unclean balance return 111; both outputs come off stock."""
        m = self.m
        grader = Brand(name="Grader rejection")
        self.db.add(grader)
        self.db.flush()
        add_inventory(
            self.db,
            m["product"].id,
            m["brand"].id,
            m["location"].id,
            m["bag_loose"].id,
            0,
            Decimal("300"),
        )
        self.db.commit()
        job = self._create_job()
        fresh = _zero_batch()
        fresh["input_lines"] = [
            {
                "location_id": m["location"].id,
                "bag_type_id": m["bag_loose"].id,
                "bag_count": 0,
                "loose_kg": Decimal("300"),
                "owner_type": "owned",
            }
        ]
        submit_batch(self.db, job.id, **fresh)

        later = _zero_batch()
        later["output_lines"] = [
            {
                "brand_id": grader.id,
                "location_id": m["location"].id,
                "bag_type_id": m["bag_loose"].id,
                "bag_count": 0,
                "loose_kg": Decimal("155"),
            }
        ]
        later["balance_return_lines"] = [
            {
                "location_id": m["location"].id,
                "bag_type_id": m["bag_loose"].id,
                "bag_count": 0,
                "loose_kg": Decimal("111"),
            }
        ]
        submit_batch(self.db, job.id, **later)
        batch = self.db.scalars(
            select(ProcessingBatch)
            .where(ProcessingBatch.job_id == job.id)
            .order_by(ProcessingBatch.id.desc())
        ).first()
        assert batch is not None
        complete_job(self.db, job.id, **_zero_batch())

        grader_inv = self.db.scalar(
            select(Inventory).where(
                Inventory.brand_id == grader.id,
                Inventory.bag_type_id == m["bag_loose"].id,
            )
        )
        unclean_inv = self.db.scalar(
            select(Inventory).where(
                Inventory.brand_id == m["brand"].id,
                Inventory.bag_type_id == m["bag_loose"].id,
            )
        )
        assert grader_inv is not None
        assert unclean_inv is not None
        self.assertEqual(grader_inv.loose_kg, Decimal("155"))
        self.assertEqual(unclean_inv.loose_kg, Decimal("111"))

        void_processing_batch(self.db, batch.id)

        grader_after = self.db.scalar(
            select(Inventory).where(
                Inventory.brand_id == grader.id,
                Inventory.bag_type_id == m["bag_loose"].id,
            )
        )
        unclean_after = self.db.scalar(
            select(Inventory).where(
                Inventory.brand_id == m["brand"].id,
                Inventory.bag_type_id == m["bag_loose"].id,
            )
        )
        self.assertTrue(grader_after is None or grader_after.loose_kg == Decimal("0"))
        self.assertTrue(unclean_after is None or unclean_after.loose_kg == Decimal("0"))
        job = load_processing_job(self.db, job.id)
        self.assertEqual(job.status, ProcessingJobStatus.open)

    def test_void_grader_loose_when_pile_moved_to_other_location(self):
        """Grader 155 still on hand at another godown must reverse (processing-only fallback)."""
        m = self.m
        grader = Brand(name="Grader rejection")
        other = Location(name="Godown")
        self.db.add_all([grader, other])
        self.db.flush()
        add_inventory(
            self.db,
            m["product"].id,
            m["brand"].id,
            m["location"].id,
            m["bag_loose"].id,
            0,
            Decimal("300"),
        )
        self.db.commit()
        job = self._create_job()
        fresh = _zero_batch()
        fresh["input_lines"] = [
            {
                "location_id": m["location"].id,
                "bag_type_id": m["bag_loose"].id,
                "bag_count": 0,
                "loose_kg": Decimal("300"),
                "owner_type": "owned",
            }
        ]
        submit_batch(self.db, job.id, **fresh)
        later = _zero_batch()
        later["output_lines"] = [
            {
                "brand_id": grader.id,
                "location_id": m["location"].id,
                "bag_type_id": m["bag_loose"].id,
                "bag_count": 0,
                "loose_kg": Decimal("155"),
            }
        ]
        submit_batch(self.db, job.id, **later)
        batch = self.db.scalars(
            select(ProcessingBatch)
            .where(ProcessingBatch.job_id == job.id)
            .order_by(ProcessingBatch.id.desc())
        ).first()
        assert batch is not None
        grader_inv = self.db.scalar(
            select(Inventory).where(
                Inventory.brand_id == grader.id,
                Inventory.location_id == m["location"].id,
            )
        )
        assert grader_inv is not None
        grader_inv.location_id = other.id
        self.db.commit()
        complete_job(self.db, job.id, **_zero_batch())

        void_processing_batch(self.db, batch.id)

        grader_after = self.db.scalar(
            select(Inventory).where(Inventory.brand_id == grader.id)
        )
        self.assertTrue(grader_after is None or grader_after.loose_kg == Decimal("0"))

    def test_void_output_after_rebag_to_loose_on_completed_job(self):
        """Output kg still on hand as a different bag type must reverse (not false insufficient)."""
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 10)]
        submit_batch(self.db, job.id, **payload)
        out_payload = _zero_batch()
        out_payload["output_lines"] = [_output_line(self.m, 8)]
        submit_batch(self.db, job.id, **out_payload)
        batch = self.db.scalars(
            select(ProcessingBatch).where(ProcessingBatch.job_id == job.id).order_by(ProcessingBatch.id.desc())
        ).first()
        assert batch is not None

        create_bag_change(
            self.db,
            location_id=self.m["location"].id,
            product_id=self.m["product"].id,
            brand_id=self.m["out_brand"].id,
            from_bag_type_id=self.m["bag_50"].id,
            from_bag_count=8,
            from_loose_kg=Decimal("0"),
            quantity_loss_kg=Decimal("0"),
            to_lines=[
                {
                    "to_bag_type_id": self.m["bag_loose"].id,
                    "bag_count": 0,
                    "loose_kg": Decimal("400"),
                }
            ],
            notes=None,
        )
        complete_job(self.db, job.id, **_zero_batch())

        void_processing_batch(self.db, batch.id)

        out_bags = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["product"].id,
                Inventory.brand_id == self.m["out_brand"].id,
                Inventory.bag_type_id == self.m["bag_50"].id,
            )
        )
        out_loose = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["product"].id,
                Inventory.brand_id == self.m["out_brand"].id,
                Inventory.bag_type_id == self.m["bag_loose"].id,
            )
        )
        self.assertTrue(out_bags is None or out_bags.bag_count == 0)
        self.assertTrue(out_loose is None or out_loose.loose_kg == Decimal("0"))

        inp = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["product"].id,
                Inventory.brand_id == self.m["brand"].id,
                Inventory.bag_type_id == self.m["bag_50"].id,
            )
        )
        assert inp is not None
        self.assertEqual(inp.bag_count, 10)

        job = load_processing_job(self.db, job.id)
        self.assertEqual(job.status, ProcessingJobStatus.open)

    def test_void_on_completed_job_reopens(self):
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 10)]
        submit_batch(self.db, job.id, **payload)
        out_payload = _zero_batch()
        out_payload["output_lines"] = [_output_line(self.m, 8)]
        out_payload["miscellaneous_waste_kg"] = Decimal("50")
        submit_batch(self.db, job.id, **out_payload)
        complete_job(self.db, job.id, **_zero_batch())
        job = load_processing_job(self.db, job.id)
        self.assertEqual(job.status, ProcessingJobStatus.completed)

        batch = self.db.scalars(select(ProcessingBatch).where(ProcessingBatch.job_id == job.id)).first()
        assert batch is not None
        void_processing_batch(self.db, batch.id)
        job = load_processing_job(self.db, job.id)
        self.assertEqual(job.status, ProcessingJobStatus.open)
        self.assertIsNone(job.completed_at)

    def test_complete_empty_open_job(self):
        """Open job with no active batches may be completed to free the open slot."""
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 4)]
        submit_batch(self.db, job.id, **payload)
        batch = self.db.scalars(select(ProcessingBatch).where(ProcessingBatch.job_id == job.id)).one()
        void_processing_batch(self.db, batch.id)

        job = complete_job(self.db, job.id, **_zero_batch())
        self.assertEqual(job.status, ProcessingJobStatus.completed)
        self.assertIsNotNone(job.completed_at)
        summary = compute_processing_summary(job)
        self.assertEqual(summary["batch_count"], 0)
        self.assertEqual(summary["total_fresh_input_kg"], Decimal("0"))

    def test_void_completed_job_auto_closes_empty_other_open_and_reopens(self):
        """Empty open sibling is auto-closed so completed-job void can reopen."""
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 10)]
        submit_batch(self.db, job.id, **payload)
        balance_payload = _zero_batch()
        balance_payload["balance_return_lines"] = [
            {
                "location_id": self.m["location"].id,
                "bag_type_id": self.m["bag_loose"].id,
                "bag_count": 0,
                "loose_kg": Decimal("134.900"),
            }
        ]
        submit_batch(self.db, job.id, **balance_payload)
        complete_job(self.db, job.id, **_zero_batch())

        other = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["brand"].id,
        )
        self.assertEqual(other.status, ProcessingJobStatus.open)

        batch = self.db.scalars(
            select(ProcessingBatch)
            .where(ProcessingBatch.job_id == job.id)
            .order_by(ProcessingBatch.id.desc())
        ).first()
        assert batch is not None
        void_processing_batch(self.db, batch.id)

        job = load_processing_job(self.db, job.id)
        self.assertEqual(job.status, ProcessingJobStatus.open)
        self.assertIsNone(job.completed_at)
        other = load_processing_job(self.db, other.id)
        self.assertEqual(other.status, ProcessingJobStatus.completed)
        self.db.refresh(batch)
        self.assertIsNotNone(batch.voided_at)

        inv = self.db.scalar(
            select(Inventory).where(
                Inventory.product_id == self.m["product"].id,
                Inventory.brand_id == self.m["brand"].id,
                Inventory.bag_type_id == self.m["bag_loose"].id,
            )
        )
        if inv is not None:
            self.assertEqual(inv.quantity_kg, Decimal("0.000"))

    def test_void_completed_job_rejects_when_other_open_has_batches(self):
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 10)]
        submit_batch(self.db, job.id, **payload)
        complete_job(self.db, job.id, **_zero_batch())

        other = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["brand"].id,
        )
        other_payload = _zero_batch()
        other_payload["input_lines"] = [_input_line(self.m, 2)]
        submit_batch(self.db, other.id, **other_payload)

        batch = self.db.scalars(
            select(ProcessingBatch)
            .where(ProcessingBatch.job_id == job.id)
            .order_by(ProcessingBatch.id.desc())
        ).first()
        assert batch is not None
        with self.assertRaises(ValueError) as ctx:
            void_processing_batch(self.db, batch.id)
        self.assertIn("another open processing job", str(ctx.exception))

        job = load_processing_job(self.db, job.id)
        self.assertEqual(job.status, ProcessingJobStatus.completed)
        self.db.refresh(batch)
        self.assertIsNone(batch.voided_at)

    def test_double_void_rejected(self):
        job = self._create_job()
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 5)]
        submit_batch(self.db, job.id, **payload)
        batch = self.db.scalars(select(ProcessingBatch).where(ProcessingBatch.job_id == job.id)).one()
        void_processing_batch(self.db, batch.id)
        with self.assertRaises(ValueError) as ctx:
            void_processing_batch(self.db, batch.id)
        self.assertEqual(str(ctx.exception), OPERATION_ALREADY_VOIDED_MSG)


class ProcessingVoidApiV148Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_api_void_batch(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["brand"].id,
        )
        payload = _zero_batch()
        payload["input_lines"] = [_input_line(self.m, 4)]
        submit_batch(self.db, job.id, **payload)
        batch = self.db.scalars(select(ProcessingBatch).where(ProcessingBatch.job_id == job.id)).one()

        r = self.client.post(
            f"/api/operations/processing/batches/{batch.id}/void",
            headers=idem_void_headers(str(uuid4()), TEST_VOID_AUTH_PASSWORD),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "open")
        self.assertEqual(body["summary"]["batch_count"], 0)


if __name__ == "__main__":
    unittest.main()
