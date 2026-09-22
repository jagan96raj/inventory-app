"""Helpers to keep secrets out of logs (Spec v17.3.28)."""

from __future__ import annotations

from typing import Mapping

SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-void-authorization",
        "x-csrf-token",
        "proxy-authorization",
    }
)

SENSITIVE_BODY_KEYS = frozenset(
    {
        "password",
        "new_password",
        "password_hash",
        "password_plain",
        "void_password",
        "otp",
        "id_token",
        "authorization_password",
    }
)


def sanitize_headers_for_log(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Drop or redact auth/cookie/void headers before any request logging."""
    if not headers:
        return {}
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADER_NAMES:
            out[key] = "[redacted]"
        else:
            out[key] = value
    return out


def sanitize_mapping_for_log(data: Mapping[str, object] | None) -> dict[str, object]:
    if not data:
        return {}
    out: dict[str, object] = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_BODY_KEYS:
            out[key] = "[redacted]"
        else:
            out[key] = value
    return out
