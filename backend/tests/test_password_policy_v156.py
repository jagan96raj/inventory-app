"""Spec v15.6 — strong password policy."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import COOKIE_NAME, get_current_user, hash_password
from app.core.password_policy import validate_password_strength
from app.database import Base, get_db
from app.main import app
from app.models.entities import User, UserRole
from tests.idempotency_helpers import new_test_idempotency_key

STRONG = "Test@123"
WEAK_CASES = {
    "short1!": "8 characters",
    "nouppercase1!": "uppercase",
    "NOLOWERCASE1!": "lowercase",
    "NoDigits!!": "digit",
    "NoSpecial1": "special",
}


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class PasswordPolicyUnitTests(unittest.TestCase):
    def test_reject_weak_passwords(self):
        for password, needle in WEAK_CASES.items():
            with self.subTest(password=password):
                with self.assertRaises(ValueError) as ctx:
                    validate_password_strength(password)
                self.assertIn(needle, str(ctx.exception).lower())

    def test_accept_strong_passwords(self):
        for password in (STRONG, "RajAgro1!"):
            with self.subTest(password=password):
                validate_password_strength(password)


class PasswordPolicyApiTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        owner = User(
            id=1,
            email="owner@test.com",
            name="Owner",
            password_hash=hash_password(STRONG),
            role=UserRole.owner,
        )
        self.db.add(owner)
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: owner
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    @patch("app.core.auth.settings")
    def test_signup_rejects_weak_password(self, mock_settings):
        mock_settings.allowed_emails = ""
        res = self.client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": "NoSpecial1", "name": "New"},
        )
        self.assertEqual(res.status_code, 400, res.text)
        self.assertIn("special", res.json()["detail"].lower())

    @patch("app.core.auth.settings")
    def test_signup_accepts_strong_password(self, mock_settings):
        mock_settings.allowed_emails = ""
        mock_settings.jwt_expire_hours = 24
        mock_settings.jwt_secret = "test-secret-key-32-chars-minimum!!"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.cookie_secure = False
        res = self.client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": STRONG, "name": "New"},
        )
        self.assertEqual(res.status_code, 201, res.text)
        self.assertIn(COOKIE_NAME, res.cookies)

    def test_create_user_rejects_weak_password(self):
        res = self.client.post(
            "/api/users",
            json={"email": "staff@test.com", "password": "NoSpecial1", "role": "writer"},
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 400, res.text)
        self.assertIn("special", res.json()["detail"].lower())

    def test_create_user_accepts_strong_password(self):
        res = self.client.post(
            "/api/users",
            json={"email": "staff@test.com", "password": "RajAgro1!", "role": "writer"},
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["email"], "staff@test.com")

    def test_login_allows_existing_weak_password(self):
        weak_hash = hash_password("password123")
        user = User(
            id=2,
            email="legacy@test.com",
            password_hash=weak_hash,
            role=UserRole.writer,
        )
        self.db.add(user)
        self.db.commit()

        res = self.client.post(
            "/api/auth/login",
            json={"email": "legacy@test.com", "password": "password123"},
        )
        self.assertEqual(res.status_code, 200, res.text)


if __name__ == "__main__":
    unittest.main()
