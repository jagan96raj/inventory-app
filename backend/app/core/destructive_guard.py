"""Guard destructive dev-only CLI scripts (Spec v15.7)."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from app.config import settings

CONFIRM_PHRASE = "I_UNDERSTAND_DELETE_DATA"
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

BLOCKED_DISABLED = (
    "Blocked: destructive scripts disabled. Set ALLOW_DESTRUCTIVE_SCRIPTS=true in .env "
    "only on local dev if you really need this. Never on production."
)
BLOCKED_CONFIRM = (
    f"Blocked: set DESTRUCTIVE_SCRIPT_CONFIRM={CONFIRM_PHRASE} in .env to confirm "
    "you understand this will delete or reset data."
)
BLOCKED_REMOTE = (
    "Blocked: DATABASE_URL host is not localhost. Destructive scripts are local-dev only. "
    "Point DATABASE_URL at localhost (e.g. docker compose Postgres) or do not run this script."
)


class DestructiveScriptBlocked(Exception):
    """Raised when a destructive script is not allowed to run."""


def database_host(database_url: str) -> str | None:
    parsed = urlparse(database_url.replace("+psycopg", ""))
    return (parsed.hostname or "").lower() or None


def check_destructive_scripts_allowed() -> None:
    """Raise DestructiveScriptBlocked when wipe scripts must not run."""
    if not settings.allow_destructive_scripts:
        raise DestructiveScriptBlocked(BLOCKED_DISABLED)

    if settings.destructive_script_confirm != CONFIRM_PHRASE:
        raise DestructiveScriptBlocked(BLOCKED_CONFIRM)

    host = database_host(settings.database_url)
    if host is not None and host not in LOCAL_DB_HOSTS:
        raise DestructiveScriptBlocked(BLOCKED_REMOTE)


def require_destructive_scripts_allowed(script_name: str = "") -> None:
    """Print a clear error and exit 1 when destructive scripts are blocked."""
    try:
        check_destructive_scripts_allowed()
    except DestructiveScriptBlocked as exc:
        prefix = f"{script_name}: " if script_name else ""
        print(f"{prefix}{exc}", file=sys.stderr)
        sys.exit(1)
