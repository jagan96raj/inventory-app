"""Spec v16.0.4 — configurable database connection pool."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import QueuePool

from app.config import Settings
from app.database import create_db_engine
from app.main import app

_POSTGRES_URL = "postgresql+psycopg://inventory:inventory@localhost:5432/inventory"


class TestDatabasePoolV1604(unittest.TestCase):
    def test_engine_uses_default_pool_settings(self):
        cfg = Settings(database_url=_POSTGRES_URL)
        engine = create_db_engine(_POSTGRES_URL, cfg)
        try:
            self.assertIsInstance(engine.pool, QueuePool)
            self.assertEqual(engine.pool.size(), cfg.db_pool_size)
            self.assertEqual(engine.pool._max_overflow, cfg.db_max_overflow)
            self.assertEqual(engine.pool._timeout, cfg.db_pool_timeout)
            self.assertEqual(engine.pool._recycle, cfg.db_pool_recycle)
        finally:
            engine.dispose()

    def test_overridden_settings_reflect_in_engine(self):
        cfg = Settings(
            database_url=_POSTGRES_URL,
            db_pool_size=8,
            db_max_overflow=12,
            db_pool_timeout=45,
            db_pool_recycle=3600,
        )
        engine = create_db_engine(_POSTGRES_URL, cfg)
        try:
            self.assertEqual(engine.pool.size(), 8)
            self.assertEqual(engine.pool._max_overflow, 12)
            self.assertEqual(engine.pool._timeout, 45)
            self.assertEqual(engine.pool._recycle, 3600)
        finally:
            engine.dispose()

    def test_pool_pre_ping_enabled(self):
        cfg = Settings(database_url=_POSTGRES_URL)
        engine = create_db_engine(_POSTGRES_URL, cfg)
        try:
            self.assertTrue(engine.pool._pre_ping)
        finally:
            engine.dispose()

    @patch("app.main.check_database", return_value=True)
    def test_health_ready_still_ok_when_db_up(self, _mock_check):
        client = TestClient(app)
        res = client.get("/health/ready")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "database": "ok"})


if __name__ == "__main__":
    unittest.main()
