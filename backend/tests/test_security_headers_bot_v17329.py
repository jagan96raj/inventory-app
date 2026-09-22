"""Spec v17.3.29 — security headers middleware + Turnstile bot protection."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.core.security_headers import SECURITY_HEADERS
from app.main import app
from app.services.bot_protection import (
    CAPTCHA_FAILED_MSG,
    CAPTCHA_REQUIRED_MSG,
    bot_protection_public_status,
    require_captcha_token,
)


class SecurityHeadersMiddlewareTests(unittest.TestCase):
    def test_health_includes_security_headers(self):
        client = TestClient(app)
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        for key, value in SECURITY_HEADERS.items():
            self.assertEqual(res.headers.get(key), value)
        # HSTS only when COOKIE_SECURE (prod HTTPS)
        if settings.cookie_secure:
            self.assertIn("max-age=", res.headers.get("Strict-Transport-Security", ""))
        else:
            self.assertIsNone(res.headers.get("Strict-Transport-Security"))


class BotProtectionStatusTests(unittest.TestCase):
    def test_status_disabled_by_default(self):
        client = TestClient(app)
        with patch.object(settings, "bot_protection_enabled", False):
            res = client.get("/api/auth/bot-protection-status")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertFalse(data["enabled"])
        self.assertIsNone(data["site_key"])


class RequireCaptchaTokenTests(unittest.TestCase):
    def test_noop_when_disabled(self):
        with patch.object(settings, "bot_protection_enabled", False):
            require_captcha_token(None)

    def test_requires_token_when_enabled(self):
        with patch.object(settings, "bot_protection_enabled", True):
            with patch.object(settings, "turnstile_site_key", "site"):
                with patch.object(settings, "turnstile_secret_key", "secret"):
                    with self.assertRaises(HTTPException) as ctx:
                        require_captcha_token(None)
                    self.assertEqual(ctx.exception.status_code, 400)
                    self.assertEqual(ctx.exception.detail, CAPTCHA_REQUIRED_MSG)

    @patch("app.services.bot_protection.httpx.Client")
    def test_rejects_failed_verify(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value.json.return_value = {"success": False}
        mock_client.post.return_value.raise_for_status = MagicMock()
        mock_client_cls.return_value = mock_client
        with patch.object(settings, "bot_protection_enabled", True):
            with patch.object(settings, "turnstile_site_key", "site"):
                with patch.object(settings, "turnstile_secret_key", "secret"):
                    with self.assertRaises(HTTPException) as ctx:
                        require_captcha_token("bad-token")
                    self.assertEqual(ctx.exception.detail, CAPTCHA_FAILED_MSG)

    @patch("app.services.bot_protection.httpx.Client")
    def test_accepts_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value.json.return_value = {"success": True}
        mock_client.post.return_value.raise_for_status = MagicMock()
        mock_client_cls.return_value = mock_client
        with patch.object(settings, "bot_protection_enabled", True):
            with patch.object(settings, "turnstile_site_key", "site"):
                with patch.object(settings, "turnstile_secret_key", "secret"):
                    require_captcha_token("ok-token")

    def test_public_status_requires_site_key(self):
        with patch.object(settings, "bot_protection_enabled", True):
            with patch.object(settings, "turnstile_site_key", ""):
                status = bot_protection_public_status()
                self.assertFalse(status["enabled"])


if __name__ == "__main__":
    unittest.main()
