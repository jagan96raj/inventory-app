from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.permissions import require_assigned_role
from app.routers import (
    accounts,
    audit,
    auth,
    bank_accounts,
    bills,
    book_settings,
    cash_book,
    companies,
    expense_categories,
    fulfillment,
    inventory,
    job_work,
    login_history,
    masters,
    operations,
    payments,
    reports,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth")
# Spec v17.0.4 — public company registration (no auth; gated by ALLOW_COMPANY_REGISTRATION).
api_router.include_router(companies.public_router)

protected_router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_assigned_role)])
protected_router.include_router(users.router)
protected_router.include_router(companies.router)
protected_router.include_router(masters.router)
protected_router.include_router(inventory.router)
protected_router.include_router(job_work.router)
protected_router.include_router(bills.router)
protected_router.include_router(fulfillment.router)
protected_router.include_router(operations.router)
protected_router.include_router(payments.router)
protected_router.include_router(reports.router)
protected_router.include_router(bank_accounts.router)
protected_router.include_router(expense_categories.router)
protected_router.include_router(cash_book.router)
protected_router.include_router(accounts.router)
protected_router.include_router(book_settings.router)
protected_router.include_router(audit.router)
protected_router.include_router(login_history.router)
api_router.include_router(protected_router)
