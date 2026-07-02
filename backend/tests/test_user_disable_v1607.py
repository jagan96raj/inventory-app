"""Spec v16.0.7 — disable user (soft ban)."""
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import COOKIE_NAME, create_access_token, get_current_user, hash_password
from app.database import Base, get_db
from app.main import app
from app.models.entities import AuditEvent, User, UserRole
from app.services.audit_log import AuditAction

STRONG_PASSWORD = "Test@123"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class TestUserDisableV1607(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        owner_hash = hash_password("owner-pass")
        writer_hash = hash_password("writer-pass")
        self.owner = User(
            id=1,
            email="owner@test.com",
            name="Owner",
            password_hash=owner_hash,
            role=UserRole.owner,
            is_active=True,
        )
        self.writer = User(
            id=2,
            email="writer@test.com",
            name="Writer",
            password_hash=writer_hash,
            role=UserRole.writer,
            is_active=True,
        )
        self.db.add_all([self.owner, self.writer])
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _login_as_owner(self):
        token = create_access_token(self.owner.id)
        self.client.cookies.set(COOKIE_NAME, token)

    def test_disabled_writer_cannot_login(self):
        self._login_as_owner()
        res = self.client.patch("/api/users/2", json={"is_active": False})
        self.assertEqual(res.status_code, 200)
        self.client.cookies.clear()

        login = self.client.post(
            "/api/auth/login",
            json={"email": "writer@test.com", "password": "writer-pass"},
        )
        self.assertEqual(login.status_code, 403)
        self.assertIn("disabled", login.json()["detail"].lower())

    def test_disabled_session_rejected(self):
        writer_token = create_access_token(self.writer.id)
        self.client.cookies.set(COOKIE_NAME, writer_token)
        res = self.client.get("/api/inventory")
        self.assertEqual(res.status_code, 200)

        self.writer.is_active = False
        self.db.commit()

        res2 = self.client.get("/api/inventory")
        self.assertEqual(res2.status_code, 401)
        self.assertIn("disabled", res2.json()["detail"].lower())

    def test_re_enable_restores_login(self):
        self._login_as_owner()
        self.client.patch("/api/users/2", json={"is_active": False})
        self.client.cookies.clear()

        self._login_as_owner()
        self.client.patch("/api/users/2", json={"is_active": True})
        self.client.cookies.clear()

        login = self.client.post(
            "/api/auth/login",
            json={"email": "writer@test.com", "password": "writer-pass"},
        )
        self.assertEqual(login.status_code, 200)

    def test_cannot_disable_self(self):
        self._login_as_owner()
        res = self.client.patch("/api/users/1", json={"is_active": False})
        self.assertEqual(res.status_code, 400)
        self.assertIn("own", res.json()["detail"].lower())

    def test_cannot_disable_last_owner(self):
        other_owner = User(
            id=99,
            email="other@test.com",
            name="Other",
            password_hash="x",
            role=UserRole.owner,
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: other_owner
        res = self.client.patch("/api/users/1", json={"is_active": False})
        self.assertEqual(res.status_code, 400)
        self.assertIn("last owner", res.json()["detail"].lower())

    def test_disable_and_enable_audit_rows(self):
        self._login_as_owner()
        self.client.patch("/api/users/2", json={"is_active": False})
        disabled = self.db.scalar(
            select(AuditEvent).where(AuditEvent.action == AuditAction.USER_DISABLED)
        )
        self.assertIsNotNone(disabled)
        self.assertEqual(disabled.entity_id, 2)

        self.client.patch("/api/users/2", json={"is_active": True})
        enabled = self.db.scalar(
            select(AuditEvent).where(AuditEvent.action == AuditAction.USER_ENABLED)
        )
        self.assertIsNotNone(enabled)
        self.assertEqual(enabled.entity_id, 2)


if __name__ == "__main__":
    unittest.main()
