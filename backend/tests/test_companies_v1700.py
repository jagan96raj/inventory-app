"""Spec v17.0.0 — multi-tenant Phase 1: company model + users belong to a company."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import COOKIE_NAME, get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import Company, User, UserRole
from tests.idempotency_helpers import ensure_test_user, new_test_idempotency_key

STRONG_PASSWORD = "Test@123"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class CompaniesV1700Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_users_have_company_id_after_bootstrap(self):
        user = self.db.scalar(select(User).where(User.id == 1))
        self.assertIsNotNone(user)
        self.assertEqual(user.company_id, 1)
        company = self.db.get(Company, user.company_id)
        self.assertIsNotNone(company)
        self.assertEqual(company.name, "Raj Agro")

    def test_auth_me_includes_company_id(self):
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["company_id"], 1)
        self.assertEqual(data["company_name"], "Raj Agro")

    def test_companies_me_returns_company(self):
        res = self.client.get("/api/companies/me")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["name"], "Raj Agro")
        self.assertTrue(data["is_active"])

    def test_create_user_inherits_admin_company_id(self):
        res = self.client.post(
            "/api/users",
            json={"email": "staff@test.com", "password": STRONG_PASSWORD, "role": "writer"},
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertEqual(data["company_id"], 1)
        self.assertEqual(data["company_name"], "Raj Agro")

        created = self.db.scalar(select(User).where(User.email == "staff@test.com"))
        self.assertIsNotNone(created)
        self.assertEqual(created.company_id, 1)

    @patch("app.core.auth.settings")
    def test_signup_assigns_default_company(self, mock_settings):
        mock_settings.allowed_emails = ""
        mock_settings.jwt_expire_hours = 24
        mock_settings.jwt_secret = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.cookie_secure = False

        res = self.client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": STRONG_PASSWORD, "name": "New User"},
        )
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertEqual(data["company_id"], 1)
        self.assertEqual(data["company_name"], "Raj Agro")
        self.assertIn(COOKIE_NAME, res.cookies)

        user = self.db.scalar(select(User).where(User.email == "new@example.com"))
        self.assertIsNotNone(user)
        self.assertEqual(user.company_id, 1)


if __name__ == "__main__":
    unittest.main()
