"""Spec v15.1 — signup lockdown via ALLOWED_EMAILS allowlist."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.auth import COOKIE_NAME, EMAIL_NOT_AUTHORIZED, hash_password, validate_auth_email_policy
from app.database import get_db
from app.main import app
from app.models.entities import User
from tests.processing_test_helpers import mock_db_scalar_auth

OWNER_EMAIL = "jaganraj@rajagro.com"
BLOCKED_EMAIL = "other@gmail.com"
PASSWORD = "Test@123"


class SignupLockdownPolicyTests(unittest.TestCase):
    @patch("app.core.auth.settings")
    def test_validate_refuses_startup_when_required_but_empty(self, mock_settings):
        mock_settings.require_allowed_emails = True
        mock_settings.allowed_emails = ""
        with self.assertRaises(RuntimeError) as ctx:
            validate_auth_email_policy()
        self.assertIn("REQUIRE_ALLOWED_EMAILS", str(ctx.exception))

    @patch("app.core.auth.settings")
    def test_validate_ok_when_allowlist_set(self, mock_settings):
        mock_settings.require_allowed_emails = True
        mock_settings.allowed_emails = OWNER_EMAIL
        validate_auth_email_policy()


class SignupLockdownApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db_no_user(self):
        db = MagicMock()
        mock_db_scalar_auth(db, user=None)

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        return db

    def _mock_db_with_user(self, email: str):
        password_hash = hash_password(PASSWORD)
        user = User(
            id=2,
            email=email,
            password_hash=password_hash,
            name="Staff",
            is_active=True,
        )
        db = MagicMock()
        mock_db_scalar_auth(db, user=user)

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        return db

    @patch("app.core.auth.settings.allowed_emails", OWNER_EMAIL)
    def test_signup_blocked_for_non_allowlisted_email(self):
        self._mock_db_no_user()

        res = self.client.post(
            "/api/auth/signup",
            json={"email": BLOCKED_EMAIL, "password": PASSWORD},
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], EMAIL_NOT_AUTHORIZED)

    @patch("app.core.auth.settings.allowed_emails", OWNER_EMAIL)
    def test_signup_allowed_for_allowlisted_email(self):
        db = self._mock_db_no_user()

        def _refresh(obj):
            if isinstance(obj, User):
                obj.id = 1

        db.refresh.side_effect = _refresh

        res = self.client.post(
            "/api/auth/signup",
            json={"email": OWNER_EMAIL, "password": PASSWORD, "name": "Owner"},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["email"], OWNER_EMAIL)
        self.assertIn(COOKIE_NAME, res.cookies)

    @patch("app.core.auth.settings.allowed_emails", OWNER_EMAIL)
    def test_login_blocked_for_non_allowlisted_email(self):
        self._mock_db_no_user()

        res = self.client.post(
            "/api/auth/login",
            json={"email": BLOCKED_EMAIL, "password": PASSWORD},
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], EMAIL_NOT_AUTHORIZED)

    @patch("app.core.auth.settings.allowed_emails", OWNER_EMAIL)
    def test_login_allowed_for_allowlisted_email(self):
        self._mock_db_with_user(OWNER_EMAIL)

        res = self.client.post(
            "/api/auth/login",
            json={"email": OWNER_EMAIL, "password": PASSWORD},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], OWNER_EMAIL)
        self.assertIn(COOKIE_NAME, res.cookies)

    @patch("app.core.auth.settings.allowed_emails", OWNER_EMAIL)
    def test_login_allowed_for_owner_created_user_not_on_allowlist(self):
        staff_email = "staff@company.com"
        self._mock_db_with_user(staff_email)

        res = self.client.post(
            "/api/auth/login",
            json={"email": staff_email, "password": PASSWORD},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], staff_email)

    @patch("app.core.auth.settings.allowed_emails", OWNER_EMAIL)
    def test_allowlist_is_case_insensitive(self):
        self._mock_db_with_user(OWNER_EMAIL)

        res = self.client.post(
            "/api/auth/login",
            json={"email": "JaganRaj@RajAgro.com", "password": PASSWORD},
        )
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
