"""Spec v16.0.3 — idempotency guard table retention cleanup."""
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.entities import IdempotencyRecord, IdempotencyStatus
from app.services.idempotency import (
    claim_idempotency,
    cleanup_idempotency_records,
    complete_idempotency,
)
from tests.idempotency_helpers import TEST_USER, ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _insert_record(
    db: Session,
    *,
    status: IdempotencyStatus,
    age_days: int = 0,
    age_hours: int = 0,
    key: str | None = None,
) -> IdempotencyRecord:
    ensure_test_user(db)
    record = IdempotencyRecord(
        user_id=TEST_USER.id,
        idempotency_key=key or str(uuid4()),
        route_key="test.route",
        request_hash="abc123",
        status=status,
        response_status=200 if status == IdempotencyStatus.completed else None,
        response_body='{"ok":true}' if status == IdempotencyStatus.completed else None,
    )
    db.add(record)
    db.flush()
    created_at = datetime.now(UTC) - timedelta(days=age_days, hours=age_hours)
    db.execute(
        update(IdempotencyRecord)
        .where(IdempotencyRecord.id == record.id)
        .values(created_at=created_at)
    )
    db.commit()
    db.refresh(record)
    return record


class TestIdempotencyCleanupV1603(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self._orig_retention = settings.idempotency_retention_days
        self._orig_stale = settings.idempotency_stale_in_progress_hours
        settings.idempotency_retention_days = 90
        settings.idempotency_stale_in_progress_hours = 24

    def tearDown(self):
        settings.idempotency_retention_days = self._orig_retention
        settings.idempotency_stale_in_progress_hours = self._orig_stale
        self.db.close()

    def _count(self) -> int:
        return self.db.scalar(select(func.count()).select_from(IdempotencyRecord)) or 0

    def test_old_completed_row_deleted(self):
        _insert_record(self.db, status=IdempotencyStatus.completed, age_days=100)
        self.assertEqual(self._count(), 1)
        counts = cleanup_idempotency_records(self.db)
        self.assertEqual(counts["completed_deleted"], 1)
        self.assertEqual(self._count(), 0)

    def test_recent_completed_row_kept(self):
        _insert_record(self.db, status=IdempotencyStatus.completed, age_days=10)
        counts = cleanup_idempotency_records(self.db)
        self.assertEqual(counts["completed_deleted"], 0)
        self.assertEqual(self._count(), 1)

    def test_stale_in_progress_deleted(self):
        _insert_record(self.db, status=IdempotencyStatus.in_progress, age_hours=48)
        counts = cleanup_idempotency_records(self.db)
        self.assertEqual(counts["stale_in_progress_deleted"], 1)
        self.assertEqual(self._count(), 0)

    def test_recent_in_progress_kept(self):
        _insert_record(self.db, status=IdempotencyStatus.in_progress, age_hours=1)
        counts = cleanup_idempotency_records(self.db)
        self.assertEqual(counts["stale_in_progress_deleted"], 0)
        self.assertEqual(self._count(), 1)

    def test_unique_constraint_still_works_after_cleanup(self):
        key = "reuse-after-cleanup"
        _insert_record(
            self.db,
            status=IdempotencyStatus.completed,
            age_days=100,
            key=key,
        )
        cleanup_idempotency_records(self.db)
        self.assertEqual(self._count(), 0)

        claim = claim_idempotency(self.db, TEST_USER.id, key, "test.route", "hash1")
        self.assertIsNotNone(claim.record_id)
        self.assertIsNone(claim.cached)

        complete_idempotency(self.db, claim.record_id, 200, {"ok": True})

        replay = claim_idempotency(self.db, TEST_USER.id, key, "test.route", "hash1")
        self.assertIsNotNone(replay.cached)
        self.assertEqual(replay.cached["status"], 200)


if __name__ == "__main__":
    unittest.main()
