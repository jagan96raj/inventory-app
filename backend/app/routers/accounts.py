"""Spec v12.21 — accounts dashboard + customer statement routers."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.database import get_db
from app.schemas import (
    AccountsSummaryOut,
    CustomerBalancePageOut,
    CustomerBalanceRowOut,
    CustomerStatementPageOut,
)
from app.services.accounts import (
    customer_to_row,
    get_accounts_summary,
    get_customer_statement,
    list_customer_balances_query,
)

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    dependencies=[Depends(require_permission(Permission.ACCOUNTS_VIEW))],
)


@router.get("/summary", response_model=AccountsSummaryOut)
def accounts_summary_endpoint(db: Session = Depends(get_db)):
    return get_accounts_summary(db)


@router.get("/customers", response_model=CustomerBalancePageOut)
def customer_balances_endpoint(
    has_balance: str = Query("any", pattern="^(any|positive|zero)$"),
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = list_customer_balances_query(db, has_balance=has_balance, search=search)
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [CustomerBalanceRowOut(**customer_to_row(db, c)) for c in rows]
    return CustomerBalancePageOut(**page_dict(items, total, limit, offset))


@router.get("/customers/{customer_id}/statement", response_model=CustomerStatementPageOut)
def customer_statement_endpoint(
    customer_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    try:
        data = get_customer_statement(
            db,
            customer_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return CustomerStatementPageOut(**data)
