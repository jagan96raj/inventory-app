"""Spec v16.0.6 — login history."""
import unittest
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user, hash_password
from app.database import Base, get_db
from app.main import app
from app.models.entities import LoginEvent, User, UserRole
from app.services.login_history import LoginFailureReason

STRONG_PASSWORD = "Test@123"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


OWNER = User(id=1, email="owner@test.com", name="Owner", role=UserRole.owner)
WRITER = User(id=2, email="writer@test.com", name="Writer", role=UserRole.writer)


class TestLoginHistoryV1606(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        password_hash = hash_password("password123")
        self.db.add_all(
            [
                User(
                    id=OWNER.id,
                    email=OWNER.email,
                    name=OWNER.name,
                    password_hash=password_hash,
                    role=OWNER.role,
                ),
                User(
                    id=WRITER.id,
                    email=WRITER.email,
                    name=WRITER.name,
                    password_hash=password_hash,
                    role=WRITER.role,
                ),
            ]
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
        self.db.close()

    def _as(self, user: User):
        self._current = user

    def test_successful_login_creates_row(self):
        res = self.client.post(
            "/api/auth/login",
            json={"email": OWNER.email, "password": "password123"},
        )
        self.assertEqual(res.status_code, 200)
        row = self.db.scalar(select(LoginEvent).where(LoginEvent.email == OWNER.email))
        self.assertIsNotNone(row)
        self.assertTrue(row.success)
        self.assertIsNone(row.failure_reason)
        self.assertEqual(row.user_id, OWNER.id)

    def test_wrong_password_creates_failure_row(self):
        res = self.client.post(
            "/api/auth/login",
            json={"email": OWNER.email, "password": "wrong-password"},
        )
        self.assertEqual(res.status_code, 401)
        row = self.db.scalar(
            select(LoginEvent).where(
                LoginEvent.email == OWNER.email,
                LoginEvent.success.is_(False),
            )
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.failure_reason, LoginFailureReason.INVALID_CREDENTIALS)

    def test_list_login_events_owner_ok(self):
        self.client.post(
            "/api/auth/login",
            json={"email": OWNER.email, "password": "password123"},
        )
        self._as(OWNER)
        res = self.client.get("/api/login-history/events?limit=50&offset=0")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertTrue(any(i["email"] == OWNER.email and i["success"] for i in body["items"]))

    def test_list_login_events_writer_forbidden(self):
        self._as(WRITER)
        res = self.client.get("/api/login-history/events")
        self.assertEqual(res.status_code, 403)

    def test_filters_by_date(self):
        old = LoginEvent(
            email="old@test.com",
            user_id=OWNER.id,
            success=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        new = LoginEvent(
            email="new@test.com",
            user_id=OWNER.id,
            success=True,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add_all([old, new])
        self.db.commit()
        self._as(OWNER)

        today = date.today().isoformat()
        res = self.client.get(f"/api/login-history/events?date_from={today}&date_to={today}")
        self.assertEqual(res.status_code, 200)
        emails = {i["email"] for i in res.json()["items"]}
        self.assertIn("new@test.com", emails)
        self.assertNotIn("old@test.com", emails)


if __name__ == "__main__":
    unittest.main()
