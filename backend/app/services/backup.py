"""Spec v17.3.19 — in-app PostgreSQL dump via docker compose exec + cp."""

from __future__ import annotations

import logging
import subprocess
import tempfile
import uuid
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


def _compose_cmd(*args: str) -> list[str]:
    return ["docker", "compose", *args]


def _run(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        cmd,
        cwd=str(repo_root()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _rm_container_dump(service: str, container_tmp: str, timeout: int) -> None:
    try:
        _run(
            _compose_cmd("exec", "-T", service, "rm", "-f", container_tmp),
            timeout=min(30, max(5, timeout)),
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        logger.warning("failed to remove container dump %s", container_tmp)


def run_pg_dump() -> tuple[Path, str]:
    """Dump with ``pg_dump -Fc -f /tmp/...`` then ``docker compose cp`` to the host.

    ``pg_dump -Fc -f -`` writes 0 bytes on Lightsail; writing a container file
    matches ``scripts/backup_db.ps1``. Caller must delete the host temp file.
    """
    filename = backup_filename()
    service = settings.postgres_compose_service
    timeout = settings.backup_timeout_seconds
    container_tmp = f"/tmp/graintrack-{uuid.uuid4().hex}.dump"

    host_tmp = tempfile.NamedTemporaryFile(prefix="graintrack-backup-", suffix=".dump", delete=False)
    host_path = Path(host_tmp.name)
    host_tmp.close()

    dump_cmd = _compose_cmd(
        "exec",
        "-T",
        service,
        "pg_dump",
        "-U",
        settings.postgres_user,
        "-Fc",
        "-f",
        container_tmp,
        settings.postgres_db,
    )
    cp_cmd = _compose_cmd("cp", f"{service}:{container_tmp}", str(host_path))

    def fail_host() -> None:
        host_path.unlink(missing_ok=True)

    try:
        result = _run(dump_cmd, timeout=timeout)
    except FileNotFoundError as exc:
        fail_host()
        raise ValueError(BACKUP_DUMP_FAILED_MSG) from exc
    except subprocess.TimeoutExpired as exc:
        _rm_container_dump(service, container_tmp, timeout)
        fail_host()
        raise ValueError(BACKUP_TIMEOUT_MSG) from exc
    except OSError as exc:
        fail_host()
        raise ValueError(BACKUP_DUMP_FAILED_MSG) from exc

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        logger.warning("pg_dump failed rc=%s stderr=%s", result.returncode, stderr[:500])
        _rm_container_dump(service, container_tmp, timeout)
        fail_host()
        raise ValueError(BACKUP_DUMP_FAILED_MSG)

    try:
        cp_result = _run(cp_cmd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _rm_container_dump(service, container_tmp, timeout)
        fail_host()
        raise ValueError(BACKUP_TIMEOUT_MSG) from exc
    except (FileNotFoundError, OSError) as exc:
        _rm_container_dump(service, container_tmp, timeout)
        fail_host()
        raise ValueError(BACKUP_DUMP_FAILED_MSG) from exc
    else:
        _rm_container_dump(service, container_tmp, timeout)

    if cp_result.returncode != 0:
        stderr = (cp_result.stderr or b"").decode("utf-8", errors="replace").strip()
        logger.warning("docker compose cp failed rc=%s stderr=%s", cp_result.returncode, stderr[:500])
        fail_host()
        raise ValueError(BACKUP_DUMP_FAILED_MSG)
    if not host_path.exists() or host_path.stat().st_size <= 0:
        fail_host()
        raise ValueError(BACKUP_EMPTY_MSG)
    return host_path, filename
