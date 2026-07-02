"""Spec v15.5 — login rate limiting per email."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import COOKIE_NAME, hash_password
from app.database import Base, get_db
from app.main import app
from app.models.entities import LoginRateLimit, User, UserRole

PASSWORD = "password123"
WRONG = "wrong-password"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class LoginRateLimitV155Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.user = User(
            id=1,
            email="user@test.com",
            password_hash=hash_password(PASSWORD),
            name="User",
            role=UserRole.owner,
        )
        self.other = User(
            id=2,
            email="other@test.com",
            password_hash=hash_password(PASSWORD),
            name="Other",
            role=UserRole.writer,
        )
        self.db.add_all([self.user, self.other])
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _login(self, email: str, password: str):
        return self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )

    @patch("app.services.login_rate_limit.settings")
    def test_five_wrong_passwords_then_sixth_returns_429(self, mock_settings):
        mock_settings.login_max_failed_attempts = 5
        mock_settings.login_lockout_minutes = 15

        for _ in range(5):
            res = self._login(self.user.email, WRONG)
            self.assertEqual(res.status_code, 401, res.text)

        blocked = self._login(self.user.email, WRONG)
        self.assertEqual(blocked.status_code, 429, blocked.text)
        self.assertIn("Too many failed login attempts", blocked.json()["detail"])

        row = self.db.scalar(select(LoginRateLimit).where(LoginRateLimit.email == self.user.email))
        self.assertIsNotNone(row)
        self.assertEqual(row.failed_attempts, 5)
        self.assertIsNotNone(row.locked_until)

    @patch("app.services.login_rate_limit.settings")
    def test_successful_login_clears_counter(self, mock_settings):
        mock_settings.login_max_failed_attempts = 5
        mock_settings.login_lockout_minutes = 15

        for _ in range(3):
            self.assertEqual(self._login(self.user.email, WRONG).status_code, 401)

        ok = self._login(self.user.email, PASSWORD)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertIn(COOKIE_NAME, ok.cookies)

        row = self.db.scalar(select(LoginRateLimit).where(LoginRateLimit.email == self.user.email))
        self.assertIsNotNone(row)
        self.assertEqual(row.failed_attempts, 0)
        self.assertIsNone(row.locked_until)

        for _ in range(5):
            self.assertEqual(self._login(self.user.email, WRONG).status_code, 401)
        self.assertEqual(self._login(self.user.email, WRONG).status_code, 429)

    @patch("app.services.login_rate_limit.settings")
    def test_correct_password_before_lock_still_works(self, mock_settings):
        mock_settings.login_max_failed_attempts = 5
        mock_settings.login_lockout_minutes = 15

        for _ in range(4):
            self.assertEqual(self._login(self.user.email, WRONG).status_code, 401)

        ok = self._login(self.user.email, PASSWORD)
        self.assertEqual(ok.status_code, 200, ok.text)

    @patch("app.services.login_rate_limit.settings")
    def test_different_emails_independent(self, mock_settings):
        mock_settings.login_max_failed_attempts = 5
        mock_settings.login_lockout_minutes = 15

        for _ in range(5):
            self.assertEqual(self._login(self.user.email, WRONG).status_code, 401)
        self.assertEqual(self._login(self.user.email, WRONG).status_code, 429)

        other_ok = self._login(self.other.email, PASSWORD)
        self.assertEqual(other_ok.status_code, 200, other_ok.text)

    @patch("app.core.auth.settings")
    @patch("app.services.login_rate_limit.settings")
    def test_allowlist_403_does_not_count_as_failed_login(self, mock_rate_settings, mock_auth_settings):
        mock_rate_settings.login_max_failed_attempts = 5
        mock_rate_settings.login_lockout_minutes = 15
        mock_auth_settings.allowed_emails = "allowed@example.com"

        for _ in range(10):
            res = self.client.post(
                "/api/auth/login",
                json={"email": "blocked@example.com", "password": WRONG},
            )
            self.assertEqual(res.status_code, 403, res.text)

        row = self.db.scalar(select(LoginRateLimit).where(LoginRateLimit.email == "blocked@example.com"))
        self.assertIsNone(row)

    @patch("app.services.login_rate_limit.settings")
    def test_signup_blocked_when_email_locked(self, mock_settings):
        mock_settings.login_max_failed_attempts = 5
        mock_settings.login_lockout_minutes = 15

        for _ in range(5):
            self.assertEqual(self._login(self.user.email, WRONG).status_code, 401)
        self.assertEqual(self._login(self.user.email, WRONG).status_code, 429)

        signup = self.client.post(
            "/api/auth/signup",
            json={"email": self.user.email, "password": "NewPass9!", "name": "New"},
        )
        self.assertEqual(signup.status_code, 429, signup.text)


if __name__ == "__main__":
    unittest.main()
