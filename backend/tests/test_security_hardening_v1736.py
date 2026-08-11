"""Spec v17.3.6 — production security hardening."""
import logging
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.auth import get_current_user, hash_password, verify_password
from app.database import Base, get_db
from app.main import app
from app.models.entities import User, UserRole
from app.services.users import create_user, set_user_password
from tests.idempotency_helpers import TEST_USER, ensure_test_user, new_test_idempotency_key


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class PasswordPlainHardeningV1736Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        owner = self.db.get(User, TEST_USER.id)
        assert owner is not None
        owner.role = UserRole.owner
        self.db.commit()

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: owner
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_set_user_password_clears_plaintext(self):
        user = User(
            email="plain@test.com",
            password_hash=hash_password("OldPass1!"),
            password_plain="OldPass1!",
            role=UserRole.writer,
            company_id=1,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        set_user_password(user, "NewPass9!")
        self.db.commit()
        self.assertIsNone(user.password_plain)
        self.assertTrue(verify_password("NewPass9!", user.password_hash))

    def test_users_list_and_create_never_return_password(self):
        create_user(
            self.db,
            actor=self.db.get(User, TEST_USER.id),
            email="staff2@test.com",
            password="Staff@99",
            name="Staff",
            role=UserRole.writer,
        )
        listed = self.client.get("/api/users")
        self.assertEqual(listed.status_code, 200)
        for row in listed.json():
            self.assertNotIn("password", row)

        created = self.client.post(
            "/api/users",
            json={"email": "staff3@test.com", "password": "Staff@99", "role": "writer"},
            headers={"Idempotency-Key": new_test_idempotency_key()},
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertNotIn("password", created.json())
        row = self.db.scalar(select(User).where(User.email == "staff3@test.com"))
        self.assertIsNotNone(row)
        self.assertIsNone(row.password_plain)


class DisableApiDocsV1736Tests(unittest.TestCase):
    def test_disable_api_docs_setting_default_false(self):
        s = Settings(disable_api_docs=False)
        self.assertFalse(s.disable_api_docs)
        s2 = Settings(disable_api_docs=True)
        self.assertTrue(s2.disable_api_docs)

    def test_fastapi_hides_docs_when_urls_none(self):
        """Matches DISABLE_API_DOCS=true wiring in app.main."""
        locked = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        client = TestClient(locked)
        self.assertEqual(client.get("/docs").status_code, 404)
        self.assertEqual(client.get("/redoc").status_code, 404)
        self.assertEqual(client.get("/openapi.json").status_code, 404)


class CookieSecureWarningV1736Tests(unittest.TestCase):
    def test_cookie_secure_false_logs_warning(self):
        from app.main import lifespan

        with patch("app.main.settings") as mock_settings:
            mock_settings.db_pool_size = 5
            mock_settings.db_max_overflow = 10
            mock_settings.db_pool_timeout = 30
            mock_settings.db_pool_recycle = 1800
            mock_settings.cookie_secure = False
            mock_settings.disable_api_docs = False
            with patch("app.main.check_database", return_value=False):
                with self.assertLogs("app.main", level=logging.WARNING) as cm:
                    # lifespan is async context manager
                    import asyncio

                    async def _run():
                        async with lifespan(app):
                            pass

                    asyncio.run(_run())
        joined = "\n".join(cm.output)
        self.assertIn("COOKIE_SECURE", joined)


if __name__ == "__main__":
    unittest.main()
