"""Cloudflare Turnstile verification for auth-only bot protection (Spec v17.3.29)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
CAPTCHA_REQUIRED_MSG = "Complete the security check and try again."
CAPTCHA_FAILED_MSG = "Security check failed. Refresh the page and try again."
CAPTCHA_MISCONFIGURED_MSG = "Bot protection is enabled but not configured on the server."


def bot_protection_enabled() -> bool:
    return bool(settings.bot_protection_enabled)


def bot_protection_public_status() -> dict[str, Any]:
    enabled = bot_protection_enabled() and bool(settings.turnstile_site_key)
    return {
        "enabled": enabled,
        "provider": "turnstile" if enabled else None,
        "site_key": settings.turnstile_site_key if enabled else None,
    }


def require_captcha_token(token: str | None) -> None:
    """Verify Turnstile when bot protection is on; no-op when flag is false."""
    if not settings.bot_protection_enabled:
        return
    if not settings.turnstile_secret_key or not settings.turnstile_site_key:
        logger.error("BOT_PROTECTION_ENABLED but Turnstile keys missing")
        raise HTTPException(status_code=503, detail=CAPTCHA_MISCONFIGURED_MSG)
    cleaned = (token or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=CAPTCHA_REQUIRED_MSG)
    if not _verify_turnstile(cleaned):
        raise HTTPException(status_code=400, detail=CAPTCHA_FAILED_MSG)


def _verify_turnstile(token: str) -> bool:
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(
                TURNSTILE_VERIFY_URL,
                data={
                    "secret": settings.turnstile_secret_key,
                    "response": token,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        logger.exception("Turnstile verify request failed")
        return False
    return bool(payload.get("success"))
