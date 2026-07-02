"""Spec v12.19 — configurable CORS origins."""
import unittest

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.cors import DEFAULT_DEV_CORS_ORIGINS, parse_cors_origins
from app.main import app


def _test_app(cors_raw: str) -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=parse_cors_origins(cors_raw),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @test_app.get("/health")
    def health():
        return {"status": "ok"}

    return test_app


class ParseCorsOriginsTests(unittest.TestCase):
    def test_empty_returns_dev_defaults(self):
        self.assertEqual(parse_cors_origins(""), list(DEFAULT_DEV_CORS_ORIGINS))
        self.assertEqual(parse_cors_origins("   "), list(DEFAULT_DEV_CORS_ORIGINS))

    def test_comma_separated_strips_whitespace(self):
        self.assertEqual(
            parse_cors_origins("https://a.com, https://b.com "),
            ["https://a.com", "https://b.com"],
        )


class CorsMiddlewareTests(unittest.TestCase):
    def test_default_app_allows_localhost_5173(self):
        client = TestClient(app)
        res = client.get("/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), "http://localhost:5173")

    def test_default_app_options_preflight_localhost_5173(self):
        client = TestClient(app)
        res = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), "http://localhost:5173")

    def test_custom_origin_only_allows_configured(self):
        client = TestClient(_test_app("https://prod.example.com"))
        allowed = client.get("/health", headers={"Origin": "https://prod.example.com"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "https://prod.example.com",
        )

        blocked = client.get("/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(blocked.status_code, 200)
        self.assertIsNone(blocked.headers.get("access-control-allow-origin"))


if __name__ == "__main__":
    unittest.main()
