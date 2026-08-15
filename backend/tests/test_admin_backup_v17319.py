"""Spec v17.3.19 — owner-only in-app Postgres backup download."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import User, UserRole
from app.routers.admin import OWNER_ONLY_BACKUP_MSG
from app.services.backup import BACKUP_DUMP_FAILED_MSG, backup_filename
from tests.idempotency_helpers import ensure_test_user


OWNER = User(id=1, email="owner@test.com", name="Owner", role=UserRole.owner, company_id=1)
WRITER = User(id=2, email="writer@test.com", name="Writer", role=UserRole.writer, company_id=1)


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class AdminBackupV17319Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        if self.db.get(User, WRITER.id) is None:
            self.db.add(
                User(
                    id=WRITER.id,
                    email=WRITER.email,
                    name=WRITER.name,
                    password_hash="x",
                    role=UserRole.writer,
                    company_id=1,
                )
            )
            self.db.commit()

        def override_db():
            yield self.db

        self._current = OWNER
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self._current
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _as(self, user: User):
        self._current = user

    def test_backup_filename_format(self):
        name = backup_filename()
        self.assertTrue(name.startswith("graintrack-"))
        self.assertTrue(name.endswith(".dump"))
        self.assertRegex(name, r"^graintrack-\d{4}-\d{2}-\d{2}_\d{4}\.dump$")

    def test_non_owner_forbidden(self):
        self._as(WRITER)
        r = self.client.get("/api/admin/backup")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"], OWNER_ONLY_BACKUP_MSG)

    def test_owner_downloads_dump(self):
        tmp = tempfile.NamedTemporaryFile(prefix="gt-test-dump-", suffix=".dump", delete=False)
        tmp.write(b"PGDMP-FAKE")
        tmp.close()
        tmp_path = Path(tmp.name)
        filename = "graintrack-2026-08-15_1200.dump"

        def fake_dump():
            return tmp_path, filename

        self._as(OWNER)
        with patch("app.routers.admin.run_pg_dump", side_effect=fake_dump):
            r = self.client.get("/api/admin/backup")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"PGDMP-FAKE")
        cd = r.headers.get("content-disposition", "")
        self.assertIn(filename, cd)
        self.assertIn("attachment", cd.lower())
        self.assertFalse(tmp_path.exists())

    def test_dump_failure_is_503(self):
        self._as(OWNER)
        with patch("app.routers.admin.run_pg_dump", side_effect=ValueError(BACKUP_DUMP_FAILED_MSG)):
            r = self.client.get("/api/admin/backup")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"], BACKUP_DUMP_FAILED_MSG)
