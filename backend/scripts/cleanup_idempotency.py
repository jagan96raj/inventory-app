"""Prune old idempotency guard rows (Spec v16.0.3).

Safe for production: only deletes completed rows older than IDEMPOTENCY_RETENTION_DAYS
and stuck in_progress rows older than IDEMPOTENCY_STALE_IN_PROGRESS_HOURS. Frontend
generates a new Idempotency-Key per form submit, so pruning does not affect normal ops.

Usage:
    cd backend
    python scripts/cleanup_idempotency.py

Optional: schedule weekly via Windows Task Scheduler for long-running deployments.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.services.idempotency import cleanup_idempotency_records


def main() -> int:
    db = SessionLocal()
    try:
        counts = cleanup_idempotency_records(db)
        print(f"completed_deleted={counts['completed_deleted']}")
        print(f"stale_in_progress_deleted={counts['stale_in_progress_deleted']}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
