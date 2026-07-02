"""Spec v15.7 — destructive dev script guard."""
import unittest
from unittest.mock import patch

from app.config import settings
from app.core.destructive_guard import (
    CONFIRM_PHRASE,
    DestructiveScriptBlocked,
    check_destructive_scripts_allowed,
    database_host,
    require_destructive_scripts_allowed,
)


class DestructiveGuardUnitTests(unittest.TestCase):
    def test_database_host_parses_localhost(self):
        self.assertEqual(
            database_host("postgresql+psycopg://inventory:inventory@localhost:5432/inventory"),
            "localhost",
        )

    def test_blocked_when_disabled(self):
        with patch.object(settings, "allow_destructive_scripts", False):
            with self.assertRaises(DestructiveScriptBlocked) as ctx:
                check_destructive_scripts_allowed()
            self.assertIn("destructive scripts disabled", str(ctx.exception).lower())

    def test_blocked_without_confirm_phrase(self):
        with patch.object(settings, "allow_destructive_scripts", True):
            with patch.object(settings, "destructive_script_confirm", ""):
                with patch.object(
                    settings,
                    "database_url",
                    "postgresql+psycopg://inventory:inventory@localhost:5432/inventory",
                ):
                    with self.assertRaises(DestructiveScriptBlocked) as ctx:
                        check_destructive_scripts_allowed()
                    self.assertIn("DESTRUCTIVE_SCRIPT_CONFIRM", str(ctx.exception))

    def test_blocked_for_remote_database_host(self):
        with patch.object(settings, "allow_destructive_scripts", True):
            with patch.object(settings, "destructive_script_confirm", CONFIRM_PHRASE):
                with patch.object(
                    settings,
                    "database_url",
                    "postgresql+psycopg://inventory:inventory@db.prod.example:5432/inventory",
                ):
                    with self.assertRaises(DestructiveScriptBlocked) as ctx:
                        check_destructive_scripts_allowed()
                    self.assertIn("not localhost", str(ctx.exception).lower())

    def test_allowed_for_local_dev_settings(self):
        with patch.object(settings, "allow_destructive_scripts", True):
            with patch.object(settings, "destructive_script_confirm", CONFIRM_PHRASE):
                with patch.object(
                    settings,
                    "database_url",
                    "postgresql+psycopg://inventory:inventory@127.0.0.1:5432/inventory",
                ):
                    check_destructive_scripts_allowed()

    def test_require_exits_when_blocked(self):
        with patch.object(settings, "allow_destructive_scripts", False):
            with self.assertRaises(SystemExit) as ctx:
                require_destructive_scripts_allowed("reset_db.py")
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
