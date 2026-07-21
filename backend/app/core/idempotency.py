from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.models.entities import User
from app.services.idempotency import (
    IDEMPOTENCY_IN_PROGRESS_MSG,
    IDEMPOTENCY_KEY_HEADER,
    IDEMPOTENCY_KEY_REQUIRED_MSG,
    IDEMPOTENCY_KEY_REUSED_MSG,
    assert_idempotent_request,
    claim_idempotency,
    complete_idempotency,
    fail_idempotency,
    store_idempotent_response,
)

T = TypeVar("T")


def require_idempotency_key(
    idempotency_key: str | None = Header(None, alias=IDEMPOTENCY_KEY_HEADER),
) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail=IDEMPOTENCY_KEY_REQUIRED_MSG)
    return idempotency_key.strip()


def _raise_idempotency_conflict(exc: ValueError) -> None:
    msg = str(exc)
    if msg in (IDEMPOTENCY_KEY_REUSED_MSG, IDEMPOTENCY_IN_PROGRESS_MSG):
        raise HTTPException(status_code=409, detail=msg) from exc
    raise exc


def check_idempotency(
    db: Session,
    user: User,
    key: str,
    route_key: str,
    request_hash: str,
) -> JSONResponse | None:
    try:
        cached = assert_idempotent_request(db, user.id, key, route_key, request_hash)
    except ValueError as e:
        _raise_idempotency_conflict(e)
    if cached:
        return JSONResponse(status_code=cached["status"], content=cached["body"])
    return None


def persist_idempotency(
    db: Session,
    user: User,
    key: str,
    route_key: str,
    request_hash: str,
    status: int,
    response: Any,
) -> None:
    body_dict = jsonable_encoder(response)
    try:
        store_idempotent_response(db, user.id, key, route_key, request_hash, status, body_dict)
    except ValueError as e:
        _raise_idempotency_conflict(e)


def run_idempotent_mutation(
    db: Session,
    user: User,
    key: str,
    route_key: str,
    request_hash: str,
    execute: Callable[[], tuple[T, int]],
) -> T | JSONResponse:
    try:
        claim = claim_idempotency(db, user.id, key, route_key, request_hash)
    except ValueError as e:
        _raise_idempotency_conflict(e)

    if claim.cached is not None:
        return JSONResponse(status_code=claim.cached["status"], content=claim.cached["body"])

    assert claim.record_id is not None
    record_id = claim.record_id
    try:
        result, status_code = execute()
        body_dict = jsonable_encoder(result)
        complete_idempotency(db, record_id, status_code, body_dict)
        return result
    except HTTPException:
        fail_idempotency(db, user.id, key, route_key)
        raise
    except Exception:
        fail_idempotency(db, user.id, key, route_key)
        raise
