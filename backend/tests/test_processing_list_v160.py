"""Spec v16.0 — processing job list performance (lightweight list payload)."""
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    BookSettings,
    Brand,
    Location,
    ProcessingBatch,
    ProcessingJobStatus,
    Product,
)
from app.routers import operations as operations_router
from app.services.operations import add_inventory
from app.services.processing import (
    complete_job,
    create_job,
    submit_batch,
)
from tests.idempotency_helpers import TEST_USER, ensure_test_user


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
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    out_brand = Brand(name="Clean")
    location = Location(name="Mill")
    bag_50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    db.add_all([product, brand, out_brand, location, bag_50])
    db.flush()
    db.add(
        BookSettings(
            id=1,
            cash_opening_balance=Decimal("0"),
            cash_opening_balance_at=datetime.now(timezone.utc).date(),
        )
    )
    add_inventory(db, product.id, brand.id, location.id, bag_50.id, 20, Decimal("0"))
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "out_brand": out_brand,
        "location": location,
        "bag_50": bag_50,
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


class ProcessingListV160Tests(unittest.TestCase):
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

    def _create_completed_job_with_batches(self) -> int:
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["brand"].id,
        )
        input_payload = _zero_batch()
        input_payload["input_lines"] = [
            {
                "location_id": self.m["location"].id,
                "bag_type_id": self.m["bag_50"].id,
                "bag_count": 10,
                "loose_kg": Decimal("0"),
                "owner_type": "owned",
            }
        ]
        submit_batch(self.db, job.id, **input_payload)

        output_payload = _zero_batch()
        output_payload["output_lines"] = [
            {
                "brand_id": self.m["out_brand"].id,
                "location_id": self.m["location"].id,
                "bag_type_id": self.m["bag_50"].id,
                "bag_count": 8,
                "loose_kg": Decimal("0"),
            }
        ]
        submit_batch(self.db, job.id, **output_payload)
        complete_job(self.db, job.id, **_zero_batch())
        return job.id

    def test_list_returns_empty_batches(self):
        job_id = self._create_completed_job_with_batches()
        res = self.client.get("/api/operations/processing?status=completed&limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        item = next(row for row in res.json()["items"] if row["id"] == job_id)
        self.assertEqual(item["batches"], [])
        self.assertNotIn("owner_mode", item)
        self.assertNotIn("input_rules_hint", item)

    def test_list_summary_batch_count_and_output_kg(self):
        job_id = self._create_completed_job_with_batches()
        res = self.client.get("/api/operations/processing?status=completed&limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        item = next(row for row in res.json()["items"] if row["id"] == job_id)
        self.assertEqual(item["summary"]["batch_count"], 2)
        self.assertEqual(Decimal(item["summary"]["total_output_kg"]), Decimal("400"))

    def test_detail_still_returns_full_batches(self):
        job_id = self._create_completed_job_with_batches()
        res = self.client.get(f"/api/operations/processing/{job_id}")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreater(len(body["batches"]), 0)
        self.assertTrue(any(batch["input_lines"] or batch["output_lines"] for batch in body["batches"]))
        self.assertIn("owner_mode", body)
        self.assertIn("output_by_brand", body["summary"])

    def test_list_query_does_not_join_batch_line_tables(self):
        self._create_completed_job_with_batches()
        engine = self.db.get_bind()
        statements: list[str] = []

        def _capture(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            res = self.client.get("/api/operations/processing?status=completed&limit=50&offset=0")
            self.assertEqual(res.status_code, 200)
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        joined = "\n".join(statements).lower()
        for table in (
            "processing_input_lines",
            "processing_balance_return_lines",
            "bag_types",
        ):
            self.assertNotIn(table, joined)
        if "processing_output_lines" in joined:
            self.assertIn("sum(", joined)
            self.assertNotIn("processing_output_lines.brand_id", joined)

    def test_list_loader_options_exclude_batches(self):
        import inspect as py_inspect

        source = py_inspect.getsource(operations_router.get_processing_jobs)
        self.assertNotIn("joinedload(ProcessingJob.batches)", source)

    def test_voided_batch_excluded_from_list_summary(self):
        job = create_job(
            self.db,
            input_product_id=self.m["product"].id,
            input_brand_id=self.m["brand"].id,
        )
        input_payload = _zero_batch()
        input_payload["input_lines"] = [
            {
                "location_id": self.m["location"].id,
                "bag_type_id": self.m["bag_50"].id,
                "bag_count": 4,
                "loose_kg": Decimal("0"),
                "owner_type": "owned",
            }
        ]
        submit_batch(self.db, job.id, **input_payload)
        batch = self.db.scalars(
            select(ProcessingBatch).where(ProcessingBatch.job_id == job.id)
        ).one()
        batch.voided_at = datetime.now(timezone.utc)
        job.status = ProcessingJobStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()

        res = self.client.get("/api/operations/processing?status=completed&limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        item = next(row for row in res.json()["items"] if row["id"] == job.id)
        self.assertEqual(item["summary"]["batch_count"], 0)
        self.assertEqual(Decimal(item["summary"]["total_output_kg"]), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
