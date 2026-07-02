"""Spec v15.0 — role-based access control tests."""
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import User, UserRole
from tests.idempotency_helpers import TEST_VOID_AUTH_PASSWORD, ensure_test_user, idem_void_headers

OWNER = User(id=1, email="owner@test.com", name="Owner", role=UserRole.owner)
WRITER = User(id=2, email="writer@test.com", name="Writer", role=UserRole.writer)
STOCK = User(id=3, email="stock@test.com", name="Stock", role=UserRole.stock_manager)
FACTORY = User(id=4, email="factory@test.com", name="Factory", role=UserRole.factory_manager)
UNASSIGNED = User(id=5, email="none@test.com", name="None", role=None)


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class RbacV150Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        for u in (OWNER, WRITER, STOCK, FACTORY, UNASSIGNED):
            if u.id != UNASSIGNED.id:
                self.db.add(
                    User(
                        id=u.id,
                        email=u.email,
                        name=u.name,
                        password_hash="x",
                        role=u.role,
                    )
                )
            else:
                self.db.add(
                    User(
                        id=u.id,
                        email=u.email,
                        name=u.name,
                        password_hash="x",
                        role=None,
                    )
                )
        self.db.commit()

        def override_db():
            yield self.db

        self._current = OWNER
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self._current
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def _as(self, user: User):
        self._current = user

    def test_unassigned_blocked_from_inventory(self):
        self._as(UNASSIGNED)
        r = self.client.get("/api/inventory")
        self.assertEqual(r.status_code, 403)

    def test_writer_can_view_inventory_not_create(self):
        self._as(WRITER)
        self.assertEqual(self.client.get("/api/inventory").status_code, 200)
        self.assertEqual(self.client.post("/api/inventory", json={}).status_code, 403)

    def test_stock_manager_can_bag_change_not_bills(self):
        self._as(STOCK)
        self.assertEqual(self.client.get("/api/operations/bag-change").status_code, 200)
        self.assertEqual(self.client.get("/api/bills").status_code, 403)

    def test_factory_manager_can_processing_not_payments(self):
        self._as(FACTORY)
        self.assertEqual(self.client.get("/api/operations/processing").status_code, 200)
        self.assertEqual(self.client.get("/api/payments").status_code, 403)
        self.assertEqual(self.client.get("/api/book-settings").status_code, 200)

    def test_writer_can_fulfillment_not_job_work_orders(self):
        self._as(WRITER)
        self.assertEqual(self.client.get("/api/fulfillment/bills").status_code, 200)
        self.assertEqual(self.client.get("/api/job-work").status_code, 403)
        self.assertEqual(self.client.get("/api/job-work/fulfillment/orders").status_code, 200)

    def test_only_owner_manages_users(self):
        self._as(WRITER)
        self.assertEqual(self.client.get("/api/users").status_code, 403)
        self._as(OWNER)
        self.assertEqual(self.client.get("/api/users").status_code, 200)

    def test_void_owner_only(self):
        self._as(OWNER)
        r_owner = self.client.post(
            "/api/payments/1/void",
            headers=idem_void_headers(str(uuid4())),
        )
        self.assertIn(r_owner.status_code, (400, 404))
        self.assertNotEqual(r_owner.status_code, 403)
        self._as(WRITER)
        r_writer = self.client.post(
            "/api/payments/1/void",
            headers=idem_void_headers(str(uuid4())),
        )
        self.assertEqual(r_writer.status_code, 403)

    def test_owner_email_migration_seed(self):
        ensure_test_user(self.db)
        owner = self.db.scalar(select(User).where(User.email == "owner@test.com"))
        self.assertEqual(owner.role, UserRole.owner)


if __name__ == "__main__":
    unittest.main()
