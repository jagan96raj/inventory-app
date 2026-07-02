"""Void authorization gate tests."""
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from tests.idempotency_helpers import configure_test_void_auth
from app.core.auth import hash_password
from app.core.void_auth import (
    VOID_AUTH_INVALID_MSG,
    VOID_AUTH_REQUIRED_MSG,
    verify_void_authorization,
)
from app.database import Base
from app.models.entities import User


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class VoidAuthTests(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        settings.void_auth_password = "admin-void-pass"
        self.user = User(
            id=1,
            email="user@example.com",
            password_hash=hash_password("user-login-pass"),
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        configure_test_void_auth()

    def test_missing_password_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            verify_void_authorization(None, self.user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, VOID_AUTH_REQUIRED_MSG)

    def test_admin_password_accepted(self):
        verify_void_authorization("admin-void-pass", self.user)

    def test_user_login_password_accepted(self):
        verify_void_authorization("user-login-pass", self.user)

    def test_wrong_password_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            verify_void_authorization("wrong", self.user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, VOID_AUTH_INVALID_MSG)


if __name__ == "__main__":
    unittest.main()
