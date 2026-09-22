"""Spec v17.3.28 — API rate limit + log sanitize unit tests."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.core.log_sanitize import sanitize_headers_for_log, sanitize_mapping_for_log
from app.core.rate_limit import (
    RATE_LIMIT_MSG,
    check_rate_limit,
    reset_rate_limit_state_for_tests,
)


class LogSanitizeTests(unittest.TestCase):
    def test_redacts_sensitive_headers(self):
        cleaned = sanitize_headers_for_log(
            {
                "Authorization": "Bearer secret-token",
                "Cookie": "access_token=abc",
                "X-Void-Authorization": "void-pass",
                "User-Agent": "pytest",
            }
        )
        self.assertEqual(cleaned["Authorization"], "[redacted]")
        self.assertEqual(cleaned["Cookie"], "[redacted]")
        self.assertEqual(cleaned["X-Void-Authorization"], "[redacted]")
        self.assertEqual(cleaned["User-Agent"], "pytest")

    def test_redacts_sensitive_body_keys(self):
        cleaned = sanitize_mapping_for_log(
            {"email": "a@b.com", "password": "Secret1!", "otp": "123456"}
        )
        self.assertEqual(cleaned["email"], "a@b.com")
        self.assertEqual(cleaned["password"], "[redacted]")
        self.assertEqual(cleaned["otp"], "[redacted]")


class ApiRateLimitTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limit_state_for_tests()

    def tearDown(self):
        reset_rate_limit_state_for_tests()

    def test_allows_under_limit(self):
        for _ in range(3):
            check_rate_limit(key="t:1", limit=3, window_seconds=60)

    def test_blocks_over_limit(self):
        for _ in range(2):
            check_rate_limit(key="t:2", limit=2, window_seconds=60)
        with self.assertRaises(HTTPException) as ctx:
            check_rate_limit(key="t:2", limit=2, window_seconds=60)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.detail, RATE_LIMIT_MSG)

    def test_zero_limit_disables(self):
        for _ in range(50):
            check_rate_limit(key="t:off", limit=0, window_seconds=60)

    @patch("app.core.rate_limit.settings")
    def test_otp_login_helper_uses_settings(self, mock_settings):
        from app.core.rate_limit import rate_limit_otp_login

        mock_settings.api_rate_limit_otp_login = 1
        mock_settings.api_rate_limit_window_seconds = 60
        request = MagicMock()
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"
        rate_limit_otp_login(request)
        with self.assertRaises(HTTPException) as ctx:
            rate_limit_otp_login(request)
        self.assertEqual(ctx.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
