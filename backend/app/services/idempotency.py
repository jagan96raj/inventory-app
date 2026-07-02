import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import IdempotencyRecord, IdempotencyStatus

logger = logging.getLogger(__name__)

_last_cleanup_at: datetime | None = None
_CLEANUP_THROTTLE = timedelta(hours=1)

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_KEY_REQUIRED_MSG = "Idempotency-Key header is required"
IDEMPOTENCY_KEY_REUSED_MSG = "Idempotency-Key was already used with a different request body"
IDEMPOTENCY_IN_PROGRESS_MSG = "Request already in progress. Please wait."


def canonical_request_hash(body: bytes | None) -> str:
    if not body:
        payload: dict = {}
    else:
        payload = json.loads(body)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_pydantic_body(body_model) -> str:
    payload = body_model.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_empty_body() -> str:
    return canonical_request_hash(None)


def lookup_idempotent_response(db: Session, user_id: int, key: str) -> IdempotencyRecord | None:
    return db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.idempotency_key == key,
        )
    )


def _cached_response_dict(record: IdempotencyRecord) -> dict:
    body = json.loads(record.response_body) if record.response_body else {}
    return {"status": record.response_status, "body": body}


def _apply_existing_record_rules(record: IdempotencyRecord, request_hash: str) -> dict | None:
    if record.request_hash != request_hash:
        raise ValueError(IDEMPOTENCY_KEY_REUSED_MSG)
    if record.status == IdempotencyStatus.completed:
        return _cached_response_dict(record)
    if record.status == IdempotencyStatus.in_progress:
        raise ValueError(IDEMPOTENCY_IN_PROGRESS_MSG)
    return None


@dataclass(frozen=True)
class IdempotencyClaim:
    record_id: int | None = None
    cached: dict | None = None


def cleanup_idempotency_records(db: Session) -> dict[str, int]:
    """Delete old idempotency guard rows so the table stays bounded (Spec v16.0.3)."""
    now = datetime.now(UTC)
    completed_cutoff = now - timedelta(days=settings.idempotency_retention_days)
    stale_cutoff = now - timedelta(hours=settings.idempotency_stale_in_progress_hours)

    completed_result = db.execute(
        delete(IdempotencyRecord).where(
            IdempotencyRecord.status == IdempotencyStatus.completed,
            IdempotencyRecord.created_at < completed_cutoff,
        )
    )
    stale_result = db.execute(
        delete(IdempotencyRecord).where(
            IdempotencyRecord.status == IdempotencyStatus.in_progress,
            IdempotencyRecord.created_at < stale_cutoff,
        )
    )
    db.commit()
    return {
        "completed_deleted": completed_result.rowcount or 0,
        "stale_in_progress_deleted": stale_result.rowcount or 0,
    }


def _maybe_run_throttled_cleanup(db: Session) -> None:
    """Run cleanup at most once per hour per process (non-blocking, best-effort)."""
    global _last_cleanup_at
    now = datetime.now(UTC)
    if _last_cleanup_at is not None and now - _last_cleanup_at < _CLEANUP_THROTTLE:
        return
    try:
        counts = cleanup_idempotency_records(db)
        _last_cleanup_at = now
        if counts["completed_deleted"] or counts["stale_in_progress_deleted"]:
            logger.info(
                "Idempotency cleanup: %d completed, %d stale in_progress deleted",
                counts["completed_deleted"],
                counts["stale_in_progress_deleted"],
            )
    except Exception:
        logger.exception("Idempotency cleanup failed")


def claim_idempotency(
    db: Session,
    user_id: int,
    key: str,
    route_key: str,
    request_hash: str,
) -> IdempotencyClaim:
    _maybe_run_throttled_cleanup(db)
    record = lookup_idempotent_response(db, user_id, key)
    if record is not None:
        cached = _apply_existing_record_rules(record, request_hash)
        if cached is not None:
            return IdempotencyClaim(cached=cached)

    row = IdempotencyRecord(
        user_id=user_id,
        idempotency_key=key,
        route_key=route_key,
        request_hash=request_hash,
        status=IdempotencyStatus.in_progress,
        response_status=None,
        response_body=None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = lookup_idempotent_response(db, user_id, key)
        if existing is None:
            raise
        cached = _apply_existing_record_rules(existing, request_hash)
        if cached is not None:
            return IdempotencyClaim(cached=cached)
        raise ValueError(IDEMPOTENCY_IN_PROGRESS_MSG) from None
    return IdempotencyClaim(record_id=row.id)


def complete_idempotency(
    db: Session,
    record_id: int,
    status: int,
    body_dict: dict,
) -> None:
    record = db.get(IdempotencyRecord, record_id)
    if record is None:
        raise ValueError("Idempotency record not found")
    record.response_status = status
    record.response_body = json.dumps(body_dict, separators=(",", ":"), default=str)
    record.status = IdempotencyStatus.completed
    db.commit()


def fail_idempotency(db: Session, user_id: int, key: str) -> None:
    record = lookup_idempotent_response(db, user_id, key)
    if record is None or record.status != IdempotencyStatus.in_progress:
        return
    db.delete(record)
    db.commit()


def assert_idempotent_request(
    db: Session,
    user_id: int,
    key: str,
    route_key: str,
    request_hash: str,
) -> dict | None:
    record = lookup_idempotent_response(db, user_id, key)
    if record is None:
        return None
    if record.status == IdempotencyStatus.in_progress:
        if record.request_hash != request_hash:
            raise ValueError(IDEMPOTENCY_KEY_REUSED_MSG)
        raise ValueError(IDEMPOTENCY_IN_PROGRESS_MSG)
    if record.request_hash != request_hash:
        raise ValueError(IDEMPOTENCY_KEY_REUSED_MSG)
    return _cached_response_dict(record)


def store_idempotent_response(
    db: Session,
    user_id: int,
    key: str,
    route_key: str,
    request_hash: str,
    status: int,
    body_dict: dict,
) -> None:
    body_text = json.dumps(body_dict, separators=(",", ":"), default=str)
    record = IdempotencyRecord(
        user_id=user_id,
        idempotency_key=key,
        route_key=route_key,
        request_hash=request_hash,
        status=IdempotencyStatus.completed,
        response_status=status,
        response_body=body_text,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = lookup_idempotent_response(db, user_id, key)
        if existing is None:
            raise
        if existing.request_hash != request_hash:
            raise ValueError(IDEMPOTENCY_KEY_REUSED_MSG) from None
