"""Spec v17.3.19 — in-app PostgreSQL dump via docker compose exec."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.utils.time import business_tz

logger = logging.getLogger(__name__)

BACKUP_DUMP_FAILED_MSG = (
    "Backup failed — Postgres dump did not complete. "
    "On the server, Postgres must be reachable via docker compose exec "
    f"(service '{settings.postgres_compose_service}', pg_dump -Fc)."
)
BACKUP_TIMEOUT_MSG = "Backup timed out. Try again or check Docker Postgres on the server."
BACKUP_EMPTY_MSG = "Backup failed — dump file was empty."


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def backup_filename(when: datetime | None = None) -> str:
    stamp = (when or datetime.now(business_tz())).strftime("%Y-%m-%d_%H%M")
    return f"graintrack-{stamp}.dump"


def run_pg_dump() -> tuple[Path, str]:
    """Run ``pg_dump -Fc`` inside the Compose Postgres container.

    Returns ``(temp_dump_path, download_filename)``. Caller must delete the temp file.
    """
    filename = backup_filename()
    tmp = tempfile.NamedTemporaryFile(prefix="graintrack-backup-", suffix=".dump", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        settings.postgres_compose_service,
        "pg_dump",
        "-U",
        settings.postgres_user,
        "-Fc",
        "-f",
        "-",
        settings.postgres_db,
    ]
    try:
        with tmp_path.open("wb") as out:
            result = subprocess.run(
                cmd,
                cwd=str(repo_root()),
                stdout=out,
                stderr=subprocess.PIPE,
                timeout=settings.backup_timeout_seconds,
                check=False,
            )
    except FileNotFoundError as exc:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(BACKUP_DUMP_FAILED_MSG) from exc
    except subprocess.TimeoutExpired as exc:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(BACKUP_TIMEOUT_MSG) from exc
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(BACKUP_DUMP_FAILED_MSG) from exc

    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        tmp_path.unlink(missing_ok=True)
        logger.warning("pg_dump failed rc=%s stderr=%s", result.returncode, stderr[:500])
        raise ValueError(BACKUP_DUMP_FAILED_MSG)
    if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(BACKUP_EMPTY_MSG)
    return tmp_path, filename
