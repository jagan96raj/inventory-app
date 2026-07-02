"""Spec v16.0.11 — seed_bag_types.py aligned with POST /api/seed/bag-types."""
import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models import BagType
from tests.idempotency_helpers import TEST_USER, ensure_test_user

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_bag_types.py"


def _load_seed_script():
    spec = importlib.util.spec_from_file_location("seed_bag_types", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestSeedBagTypesV1611(unittest.TestCase):
    def test_script_imports_and_runs(self):
        mod = _load_seed_script()
        db = _make_session()

        with patch.object(mod, "SessionLocal", lambda: db):
            mod.main()
            names = sorted(b.name for b in db.scalars(select(BagType)).all())
            self.assertEqual(names, ["25kg", "30kg", "50kg", "Loose"])

            mod.main()
            self.assertEqual(len(db.scalars(select(BagType)).all()), 4)

    def test_case_insensitive_skip_matches_api(self):
        mod = _load_seed_script()
        db = _make_session()
        db.add(BagType(name="50KG", weight_per_bag_kg=Decimal("50"), is_loose=False))
        db.commit()

        with patch.object(mod, "SessionLocal", lambda: db):
            mod.main()
            names = sorted(b.name for b in db.scalars(select(BagType)).all())
            self.assertEqual(names, ["25kg", "30kg", "50KG", "Loose"])

    def test_api_seed_endpoint_unchanged(self):
        db = _make_session()
        ensure_test_user(db)

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        client = TestClient(app)
        try:
            res = client.post("/api/seed/bag-types")
            self.assertEqual(res.status_code, 200)
            created = res.json()["created"]
            self.assertEqual(sorted(created), ["25kg", "30kg", "50kg", "Loose"])

            res2 = client.post("/api/seed/bag-types")
            self.assertEqual(res2.status_code, 200)
            self.assertEqual(res2.json()["created"], [])
        finally:
            app.dependency_overrides.clear()
            db.close()


if __name__ == "__main__":
    unittest.main()
