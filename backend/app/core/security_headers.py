"""HTTP security headers middleware (Spec v17.3.29).

Mirrors the Nginx production headers for API responses behind a proxy.
CSP is intentionally omitted here (Phase 2 — see docs/nginx-security-headers.md).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

# Match docs/nginx-security-headers.md (non-CSP headers).
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        # HSTS only when cookies are Secure (HTTPS production). Avoid locking HTTP dev.
        if settings.cookie_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=15552000; includeSubDomains",
            )
        return response
