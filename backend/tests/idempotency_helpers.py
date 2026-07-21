"""Shared helpers for idempotency-aware router calls in tests (v12.15)."""
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.core.void_auth import VOID_AUTH_HEADER
from app.models.entities import Company, User, UserRole

TEST_USER = User(id=1, email="test@example.com", name="Test", role=UserRole.owner, company_id=1)
TEST_VOID_AUTH_PASSWORD = "test-void-auth"


def configure_test_void_auth() -> None:
    settings.void_auth_password = TEST_VOID_AUTH_PASSWORD


configure_test_void_auth()


def new_test_idempotency_key() -> str:
    return str(uuid4())


def ensure_test_user(db: Session) -> User:
    if db.get(Company, 1) is None:
        db.add(Company(id=1, name="Raj Agro", is_active=True))
        db.flush()
    if db.get(User, TEST_USER.id) is None:
        db.add(
            User(
                id=TEST_USER.id,
                email=TEST_USER.email,
                name=TEST_USER.name,
                password_hash="x",
                role=UserRole.owner,
                company_id=1,
            )
        )
        db.flush()
    return TEST_USER


def idem_kwargs(key: str | None = None) -> dict:
    return {"user": TEST_USER, "idempotency_key": key or new_test_idempotency_key()}


def void_auth_header(password: str = TEST_VOID_AUTH_PASSWORD) -> dict[str, str]:
    return {VOID_AUTH_HEADER: password}


def idem_void_headers(key: str | None = None, password: str = TEST_VOID_AUTH_PASSWORD) -> dict[str, str]:
    return {**void_auth_header(password), "Idempotency-Key": key or new_test_idempotency_key()}
