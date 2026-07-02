"""Processing job list — status filter for open vs completed history."""
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import Brand, ProcessingJobStatus, Product
from app.services.processing import create_job
from tests.idempotency_helpers import TEST_USER, ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class ProcessingListStatusTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        product = Product(product_name="Wheat")
        brand = Brand(name="Raw")
        self.db.add_all([product, brand])
        self.db.flush()
        self.product_id = product.id
        self.brand_id = brand.id

        product_b = Product(product_name="Rice")
        brand_b = Brand(name="Mill")
        self.db.add_all([product_b, brand_b])
        self.db.flush()

        open_job = create_job(
            self.db, input_product_id=self.product_id, input_brand_id=self.brand_id
        )
        completed_job = create_job(
            self.db, input_product_id=product_b.id, input_brand_id=brand_b.id
        )
        completed_job.status = ProcessingJobStatus.completed
        completed_job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.open_id = open_job.id
        self.completed_id = completed_job.id

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_list_completed_only(self):
        res = self.client.get("/api/operations/processing?status=completed&limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["id"], self.completed_id)
        self.assertEqual(body["items"][0]["status"], "completed")

    def test_list_open_only(self):
        res = self.client.get("/api/operations/processing?status=open&limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["id"], self.open_id)
        self.assertEqual(body["items"][0]["status"], "open")

    def test_invalid_status_rejected(self):
        res = self.client.get("/api/operations/processing?status=closed")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
