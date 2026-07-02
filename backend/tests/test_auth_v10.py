"""Spec v10 authentication tests — password login and session cookies."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import COOKIE_NAME, create_access_token, hash_password, verify_password
from app.database import Base, get_db
from app.main import app
from app.models.entities import User, UserRole

STRONG_PASSWORD = "Test@123"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class PasswordAuthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_password_hash_roundtrip(self):
        hashed = hash_password("secret-pass-123")
        self.assertTrue(verify_password("secret-pass-123", hashed))
        self.assertFalse(verify_password("wrong-pass", hashed))

    def test_inventory_without_cookie_returns_401(self):
        res = self.client.get("/api/inventory")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Not authenticated")

    @patch("app.core.auth.settings")
    def test_signup_creates_user_and_sets_cookie(self, mock_settings):
        mock_settings.allowed_emails = ""
        mock_settings.jwt_expire_hours = 24
        mock_settings.jwt_secret = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.cookie_secure = False
        db = _make_session()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db

        res = self.client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": STRONG_PASSWORD, "name": "New User"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["email"], "new@example.com")
        self.assertEqual(data["name"], "New User")
        self.assertIn(COOKIE_NAME, res.cookies)
        user = db.scalar(select(User).where(User.email == "new@example.com"))
        self.assertIsNotNone(user)
        self.assertTrue(user.password_hash)
        self.assertIsNone(user.google_sub)
        db.close()

    @patch("app.core.auth.settings")
    def test_signup_duplicate_email_returns_409(self, mock_settings):
        mock_settings.allowed_emails = ""
        db = _make_session()
        db.add(User(id=1, email="taken@example.com", password_hash="x"))
        db.commit()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db

        res = self.client.post(
            "/api/auth/signup",
            json={"email": "taken@example.com", "password": STRONG_PASSWORD},
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["detail"], "Email already registered")
        db.close()

    def test_login_success_sets_cookie(self):
        password_hash = hash_password("password123")
        db = _make_session()
        db.add(User(id=2, email="user@example.com", password_hash=password_hash, name="User"))
        db.commit()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db

        res = self.client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "password123"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], "user@example.com")
        self.assertIn(COOKIE_NAME, res.cookies)
        db.close()

    def test_login_wrong_password_returns_401(self):
        password_hash = hash_password("password123")
        db = _make_session()
        db.add(User(id=2, email="user@example.com", password_hash=password_hash))
        db.commit()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db

        res = self.client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "wrong-password"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password")
        db.close()

    def test_inventory_with_valid_cookie_returns_200(self):
        db = _make_session()
        user = User(
            id=1,
            email="user@example.com",
            password_hash=hash_password("password123"),
            name="Test",
            role=UserRole.owner,
        )
        db.add(user)
        db.commit()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db

        token = create_access_token(1)
        self.client.cookies.set(COOKIE_NAME, token)
        res = self.client.get("/api/inventory")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json().get("items"), [])
        db.close()

    @patch("app.core.auth.settings")
    def test_allowed_emails_blocks_signup(self, mock_settings):
        mock_settings.allowed_emails = "allowed@example.com"
        db = _make_session()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db

        res = self.client.post(
            "/api/auth/signup",
            json={"email": "blocked@example.com", "password": STRONG_PASSWORD},
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "Email not authorized")
        db.close()


if __name__ == "__main__":
    unittest.main()
