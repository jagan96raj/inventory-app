"""Spec v12.21 — cash book router."""
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import Permission, require_permission, require_void_user
from app.core.void_auth import VOID_AUTH_HEADER, verify_backdate_authorization, verify_void_authorization
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.database import get_db
from app.models.entities import CashBookEntry, CashBookEntryType, CashBookSourceMode, User
from app.schemas import (
    CashBookEntryCreate,
    CashBookEntryEdit,
    CashBookEntryOut,
    CashBookEntryPageOut,
)
from app.services.cash_book import (
    CASH_BOOK_EXPECTED_VERSION_REQUIRED_MSG,
    CASH_BOOK_STALE_MSG,
    create_cash_book_entry,
    edit_cash_book_entry,
    list_cash_book,
    serialize_entry,
    void_cash_book_entry,
)
from app.services.idempotency import hash_empty_body, hash_pydantic_body

EXPECTED_CASH_BOOK_VERSION_HEADER = "X-Expected-Cash-Book-Version"

router = APIRouter(
    prefix="/cashbook",
    tags=["cashbook"],
    dependencies=[Depends(require_permission(Permission.CASHBOOK_MANAGE))],
)


def _to_out(entry) -> CashBookEntryOut:
    return CashBookEntryOut.model_validate(serialize_entry(entry))


def _http_for_value_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg == CASH_BOOK_STALE_MSG:
        return HTTPException(409, msg)
    if msg == CASH_BOOK_EXPECTED_VERSION_REQUIRED_MSG:
        return HTTPException(400, msg)
    return HTTPException(400, msg)


@router.get("", response_model=CashBookEntryPageOut)
def list_cash_book_endpoint(
    entry_type: CashBookEntryType | None = None,
    category_id: int | None = None,
    source_payment_mode: CashBookSourceMode | None = None,
    source_bank_account_id: int | None = None,
    bill_id: int | None = None,
    voided: str = Query("false", pattern="^(false|true|any)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = list_cash_book(
        db,
        entry_type=entry_type,
        category_id=category_id,
        source_payment_mode=source_payment_mode,
        source_bank_account_id=source_bank_account_id,
        bill_id=bill_id,
        voided=voided,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [_to_out(r) for r in rows]
    return CashBookEntryPageOut(**page_dict(items, total, limit, offset))


@router.get("/{entry_id}", response_model=CashBookEntryOut)
def get_cash_book_entry(
    entry_id: int,
    db: Session = Depends(get_db),
):
    entry = db.get(CashBookEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Cash book entry not found")
    return _to_out(entry)


@router.post("", response_model=CashBookEntryOut, status_code=201)
def post_cash_book_entry(
    body: CashBookEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_backdate_authorization(body.entry_date, void_password, user)
    route_key = "POST /api/cashbook"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            entry = create_cash_book_entry(
                db,
                entry_type=body.entry_type,
                category_id=body.category_id,
                amount=body.amount,
                description=body.description,
                reference_no=body.reference_no,
                bill_id=body.bill_id,
                source_payment_mode=body.source_payment_mode,
                source_bank_account_id=body.source_bank_account_id,
                dest_payment_mode=body.dest_payment_mode,
                dest_bank_account_id=body.dest_bank_account_id,
                entry_date=body.entry_date,
            )
        except ValueError as e:
            raise _http_for_value_error(e) from e
        return _to_out(entry), 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.patch("/{entry_id}", response_model=CashBookEntryOut)
def patch_cash_book_entry(
    entry_id: int,
    body: CashBookEntryEdit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = f"PATCH /api/cashbook/{entry_id}"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            entry = edit_cash_book_entry(
                db,
                entry_id,
                expected_version=body.expected_version,
                entry_type=body.entry_type,
                category_id=body.category_id,
                amount=body.amount,
                description=body.description,
                reference_no=body.reference_no,
                bill_id=body.bill_id,
                source_payment_mode=body.source_payment_mode,
                source_bank_account_id=body.source_bank_account_id,
                dest_payment_mode=body.dest_payment_mode,
                dest_bank_account_id=body.dest_bank_account_id,
            )
        except ValueError as e:
            raise _http_for_value_error(e) from e
        return _to_out(entry), 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/{entry_id}/void", response_model=CashBookEntryOut)
def void_cash_book_entry_endpoint(
    entry_id: int,
    expected_version: int | None = Header(None, alias=EXPECTED_CASH_BOOK_VERSION_HEADER),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/cashbook/{entry_id}/void"
    request_hash = hash_empty_body()

    def execute():
        try:
            entry = void_cash_book_entry(
                db, entry_id, expected_version=expected_version, actor=user
            )
        except ValueError as e:
            raise _http_for_value_error(e) from e
        return _to_out(entry), 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)
