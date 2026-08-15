"""Spec v12.21 — accounts dashboard + customer statement routers."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import Permission, require_permission
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.core.tenant import company_id_for_user
from app.database import get_db
from app.models.entities import User
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
from app.services.customer_search import sum_customer_balances

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    dependencies=[Depends(require_permission(Permission.ACCOUNTS_VIEW))],
)


@router.get("/summary", response_model=AccountsSummaryOut)
def accounts_summary_endpoint(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return get_accounts_summary(db, company_id=company_id_for_user(user))


@router.get("/customers", response_model=CustomerBalancePageOut)
def customer_balances_endpoint(
    has_balance: str = Query("any", pattern="^(any|positive|zero)$"),
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    company_id = company_id_for_user(user)
    q = list_customer_balances_query(
        db, company_id=company_id, has_balance=has_balance, search=search
    )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [
        CustomerBalanceRowOut(**customer_to_row(db, c, company_id=company_id)) for c in rows
    ]
    credit_total, debit_total = sum_customer_balances(
        db, company_id=company_id, search=search, has_balance=has_balance
    )
    return CustomerBalancePageOut(
        **page_dict(items, total, limit, offset),
        credit_total=credit_total,
        debit_total=debit_total,
    )


@router.get("/customers/{customer_id}/statement", response_model=CustomerStatementPageOut)
def customer_statement_endpoint(
    customer_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    try:
        data = get_customer_statement(
            db,
            customer_id,
            company_id=company_id_for_user(user),
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return CustomerStatementPageOut(**data)
