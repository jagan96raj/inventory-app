"""Spec v17.3.22 — company notes board role visibility."""
import unittest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import User, UserRole
from app.services.notes import OWNER_ONLY_NOTES_MSG
from tests.idempotency_helpers import ensure_test_user


OWNER = User(id=1, email="owner@test.com", name="Owner", role=UserRole.owner, company_id=1)
WRITER = User(id=2, email="writer@test.com", name="Writer", role=UserRole.writer, company_id=1)
STOCK = User(id=3, email="stock@test.com", name="Stock", role=UserRole.stock_manager, company_id=1)


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class CompanyNotesV17322Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        for u in (WRITER, STOCK):
            if self.db.get(User, u.id) is None:
                self.db.add(
                    User(
                        id=u.id,
                        email=u.email,
                        name=u.name,
                        password_hash="x",
                        role=u.role,
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

    def test_default_owner_only_writer_sees_empty(self):
        self._as(OWNER)
        res = self.client.post(
            "/api/notes",
            json={"title": "Private", "body": "Owner only note", "note_date": "2026-08-20"},
        )
        self.assertEqual(res.status_code, 201, res.text)
        note = res.json()
        self.assertEqual(note["viewer_roles"], [])

        self._as(WRITER)
        listed = self.client.get("/api/notes")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json(), [])

        self._as(OWNER)
        listed_owner = self.client.get("/api/notes")
        self.assertEqual(len(listed_owner.json()), 1)
        self.assertEqual(listed_owner.json()[0]["id"], note["id"])

    def test_share_with_writer_not_stock(self):
        self._as(OWNER)
        created = self.client.post(
            "/api/notes",
            json={
                "title": "Shared",
                "body": "Writers can see this",
                "note_date": "2026-08-21",
                "viewer_roles": ["writer"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        note_id = created.json()["id"]
        self.assertEqual(created.json()["viewer_roles"], ["writer"])

        self._as(WRITER)
        writer_list = self.client.get("/api/notes")
        self.assertEqual(writer_list.status_code, 200)
        ids = [n["id"] for n in writer_list.json()]
        self.assertIn(note_id, ids)

        self._as(STOCK)
        stock_list = self.client.get("/api/notes")
        self.assertEqual(stock_list.status_code, 200)
        self.assertEqual(stock_list.json(), [])

        self._as(OWNER)
        owner_list = self.client.get("/api/notes")
        self.assertIn(note_id, [n["id"] for n in owner_list.json()])

    def test_non_owner_cannot_mutate(self):
        self._as(OWNER)
        created = self.client.post(
            "/api/notes",
            json={
                "body": "Visible to writer",
                "viewer_roles": ["writer"],
                "note_date": str(date(2026, 8, 22)),
            },
        )
        note_id = created.json()["id"]

        self._as(WRITER)
        patch = self.client.patch(f"/api/notes/{note_id}", json={"body": "Hacked"})
        self.assertEqual(patch.status_code, 403)
        self.assertEqual(patch.json()["detail"], OWNER_ONLY_NOTES_MSG)

        visibility = self.client.patch(
            f"/api/notes/{note_id}", json={"viewer_roles": ["stock_manager"]}
        )
        self.assertEqual(visibility.status_code, 403)

        delete = self.client.delete(f"/api/notes/{note_id}")
        self.assertEqual(delete.status_code, 403)

        create = self.client.post("/api/notes", json={"body": "Nope"})
        self.assertEqual(create.status_code, 403)

    def test_hidden_note_is_404_for_non_viewer(self):
        self._as(OWNER)
        created = self.client.post(
            "/api/notes",
            json={"body": "Secret", "viewer_roles": []},
        )
        note_id = created.json()["id"]

        self._as(WRITER)
        res = self.client.patch(f"/api/notes/{note_id}", json={"body": "x"})
        self.assertEqual(res.status_code, 404)

        self._as(STOCK)
        gone = self.client.delete(f"/api/notes/{note_id}")
        self.assertEqual(gone.status_code, 404)

    def test_owner_can_update_visibility(self):
        self._as(OWNER)
        created = self.client.post("/api/notes", json={"body": "Later shared"})
        note_id = created.json()["id"]
        patched = self.client.patch(
            f"/api/notes/{note_id}",
            json={"viewer_roles": ["writer", "factory_manager"]},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["viewer_roles"], ["factory_manager", "writer"])
