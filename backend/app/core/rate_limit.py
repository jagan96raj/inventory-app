"""In-memory sliding-window rate limits for high-risk API routes (Spec v17.3.28).

Does not replace per-email login lockout (v15.5). Limits are keyed by client IP + route bucket.
Disabled when limit is 0. Process-local only (fine for single uvicorn worker / Lightsail).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import settings

_lock = threading.Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)

RATE_LIMIT_MSG = "Too many requests. Please wait a moment and try again."


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _prune(entries: deque[float], window_seconds: float, now: float) -> None:
    cutoff = now - window_seconds
    while entries and entries[0] < cutoff:
        entries.popleft()


def check_rate_limit(
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Raise HTTP 429 when key exceeds limit within the window. limit<=0 disables."""
    if limit <= 0 or window_seconds <= 0:
        return
    now = time.monotonic()
    with _lock:
        entries = _buckets[key]
        _prune(entries, float(window_seconds), now)
        if len(entries) >= limit:
            raise HTTPException(status_code=429, detail=RATE_LIMIT_MSG)
        entries.append(now)


def enforce_route_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    ip = _client_ip(request)
    check_rate_limit(key=f"{bucket}:{ip}", limit=limit, window_seconds=window_seconds)


def reset_rate_limit_state_for_tests() -> None:
    with _lock:
        _buckets.clear()


def rate_limit_otp_login(request: Request) -> None:
    enforce_route_rate_limit(
        request,
        "otp-login",
        settings.api_rate_limit_otp_login,
        settings.api_rate_limit_window_seconds,
    )


def rate_limit_otp_request(request: Request) -> None:
    enforce_route_rate_limit(
        request,
        "otp-request",
        settings.api_rate_limit_otp_request,
        settings.api_rate_limit_window_seconds,
    )


def rate_limit_company_register(request: Request) -> None:
    enforce_route_rate_limit(
        request,
        "company-register",
        settings.api_rate_limit_company_register,
        settings.api_rate_limit_window_seconds,
    )


def rate_limit_payment_create(request: Request) -> None:
    enforce_route_rate_limit(
        request,
        "payment-create",
        settings.api_rate_limit_payment_create,
        settings.api_rate_limit_window_seconds,
    )


def rate_limit_dashboard_bundle(request: Request) -> None:
    enforce_route_rate_limit(
        request,
        "dashboard-bundle",
        settings.api_rate_limit_dashboard_bundle,
        settings.api_rate_limit_window_seconds,
    )
