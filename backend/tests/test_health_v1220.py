"""Spec v12.20 — health and readiness checks."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.health import check_database
from app.main import app


class HealthV1220Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_returns_ok(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    @patch("app.main.check_database", return_value=True)
    def test_health_ready_db_up(self, _mock_check):
        res = self.client.get("/health/ready")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "database": "ok"})

    @patch("app.main.check_database", return_value=False)
    def test_health_ready_db_down(self, _mock_check):
        res = self.client.get("/health/ready")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json(), {"status": "degraded", "database": "unavailable"})

    @patch("app.main.check_database", return_value=False)
    def test_health_liveness_ignores_db(self, _mock_check):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})


class CheckDatabaseTests(unittest.TestCase):
    def test_check_database_sqlite(self):
        eng = create_engine("sqlite:///:memory:")
        self.assertTrue(check_database(eng))


if __name__ == "__main__":
    unittest.main()
