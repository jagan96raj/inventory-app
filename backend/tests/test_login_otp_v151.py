"""Spec v15.1 — owner-issued login OTP and user profile edits."""
import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import COOKIE_NAME, get_current_user, hash_password
from app.database import Base, get_db
from app.main import app
from app.models.entities import User, UserRole
from app.services.login_otp import _hash_otp, verify_login_otp
from app.services.users import delete_user

OWNER = User(id=1, email="owner@test.com", name="Owner", role=UserRole.owner)
STAFF = User(id=2, email="staff@test.com", name="Staff", role=UserRole.writer)


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class LoginOtpServiceTests(unittest.TestCase):
    def test_verify_login_otp_accepts_valid_code(self):
        user = User(id=1, email="u@example.com")
        user.login_otp_hash = _hash_otp("123456")
        user.login_otp_expires_at = datetime.now(UTC) + timedelta(minutes=5)
        self.assertTrue(verify_login_otp(user, "123456"))
        self.assertFalse(verify_login_otp(user, "654321"))

    def test_verify_login_otp_rejects_expired_code(self):
        user = User(id=1, email="u@example.com")
        user.login_otp_hash = _hash_otp("123456")
        user.login_otp_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        self.assertFalse(verify_login_otp(user, "123456"))


class DeleteUserServiceTests(unittest.TestCase):
    def test_blocks_deleting_sole_owner(self):
        db = _make_session()
        owner = User(
            id=1,
            email="sole@test.com",
            password_hash="x",
            role=UserRole.owner,
        )
        db.add(owner)
        db.commit()

        with self.assertRaises(ValueError) as ctx:
            delete_user(db, 1, actor_id=99)
        self.assertIn("last owner", str(ctx.exception).lower())


class LoginOtpApiTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        staff = User(
            id=STAFF.id,
            email=STAFF.email,
            name=STAFF.name,
            password_hash=hash_password("old-password"),
            role=STAFF.role,
        )
        owner = User(
            id=OWNER.id,
            email=OWNER.email,
            name=OWNER.name,
            password_hash=hash_password("owner-pass"),
            role=OWNER.role,
        )
        self.db.add_all([owner, staff])
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: owner
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_owner_can_generate_login_otp(self):
        res = self.client.post("/api/users/2/login-otp")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["otp"]), 6)
        self.assertTrue(data["otp"].isdigit())
        self.assertEqual(data["user_email"], "staff@test.com")

    def test_otp_login_sets_cookie_and_updates_password(self):
        gen = self.client.post("/api/users/2/login-otp")
        self.assertEqual(gen.status_code, 200)
        code = gen.json()["otp"]

        res = self.client.post(
            "/api/auth/otp-login",
            json={"email": "staff@test.com", "otp": code, "new_password": "NewPass9!"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], "staff@test.com")
        self.assertIn(COOKIE_NAME, res.cookies)

        staff = self.db.get(User, 2)
        self.assertIsNone(staff.login_otp_hash)
        self.assertTrue(staff.password_hash)
        self.assertIsNone(staff.password_plain)

    def test_otp_login_invalid_code_returns_401(self):
        self.client.post("/api/users/2/login-otp")
        res = self.client.post(
            "/api/auth/otp-login",
            json={"email": "staff@test.com", "otp": "999999"},
        )
        self.assertEqual(res.status_code, 401)

    def test_patch_user_updates_name_and_password(self):
        res = self.client.patch(
            "/api/users/2",
            json={"name": "Updated Name", "password": "Staff@99"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["name"], "Updated Name")
        self.assertNotIn("password", res.json())
        staff = self.db.get(User, 2)
        self.assertEqual(staff.name, "Updated Name")
        self.assertIsNone(staff.password_plain)
        self.assertTrue(staff.password_hash)

    def test_delete_user_removes_account(self):
        res = self.client.delete("/api/users/2")
        self.assertEqual(res.status_code, 204)
        self.assertIsNone(self.db.get(User, 2))

    def test_cannot_delete_self(self):
        res = self.client.delete("/api/users/1")
        self.assertEqual(res.status_code, 400)
        self.assertIn("own account", res.json()["detail"].lower())
