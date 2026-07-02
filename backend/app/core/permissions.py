"""Spec v15.0 — role-based access control."""

from enum import Enum
from typing import Callable

from fastapi import Depends, HTTPException

from app.core.auth import get_current_user
from app.models.entities import User, UserRole

ROLE_NOT_ASSIGNED_MSG = "No role assigned. Contact the owner to get access."
FORBIDDEN_MSG = "You do not have permission for this action."
OWNER_ONLY_VOID_MSG = "Only the owner role may void records."


class Permission(str, Enum):
    DASHBOARD_VIEW = "dashboard_view"
    REPORTS_VIEW = "reports_view"
    MASTERS_READ = "masters_read"
    MASTERS_MANAGE = "masters_manage"
    BOOK_SETTINGS_VIEW = "book_settings_view"
    BOOK_SETTINGS_EDIT = "book_settings_edit"
    BILLS_MANAGE = "bills_manage"
    PAYMENTS_MANAGE = "payments_manage"
    ACCOUNTS_VIEW = "accounts_view"
    CASHBOOK_MANAGE = "cashbook_manage"
    BANK_ACCOUNTS_MANAGE = "bank_accounts_manage"
    EXPENSE_CATEGORIES_MANAGE = "expense_categories_manage"
    FULFILLMENT_WRITE = "fulfillment_write"
    FULFILLMENT_VIEW = "fulfillment_view"
    JOB_WORK_MANAGE = "job_work_manage"
    JOB_WORK_FULFILLMENT_WRITE = "job_work_fulfillment_write"
    PRODUCT_TRANSFER_WRITE = "product_transfer_write"
    PRODUCT_TRANSFER_VIEW = "product_transfer_view"
    INVENTORY_VIEW = "inventory_view"
    INVENTORY_OPENING_STOCK = "inventory_opening_stock"
    INVENTORY_EDIT_QTY = "inventory_edit_qty"
    BAG_CHANGE_WRITE = "bag_change_write"
    BAG_CHANGE_VIEW = "bag_change_view"
    STOCK_DISPOSAL_WRITE = "stock_disposal_write"
    STOCK_DISPOSAL_VIEW = "stock_disposal_view"
    PROCESSING_MANAGE = "processing_manage"
    PROCESSING_VIEW = "processing_view"
    VOID = "void"
    USERS_MANAGE = "users_manage"
    AUDIT_VIEW = "audit_view"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.owner: frozenset(Permission),
    UserRole.writer: frozenset(
        {
            Permission.DASHBOARD_VIEW,
            Permission.REPORTS_VIEW,
            Permission.MASTERS_READ,
            Permission.INVENTORY_VIEW,
            Permission.FULFILLMENT_WRITE,
            Permission.FULFILLMENT_VIEW,
            Permission.JOB_WORK_FULFILLMENT_WRITE,
            Permission.PRODUCT_TRANSFER_WRITE,
            Permission.PRODUCT_TRANSFER_VIEW,
        }
    ),
    UserRole.stock_manager: frozenset(
        {
            Permission.DASHBOARD_VIEW,
            Permission.REPORTS_VIEW,
            Permission.MASTERS_READ,
            Permission.INVENTORY_VIEW,
            Permission.BAG_CHANGE_WRITE,
            Permission.BAG_CHANGE_VIEW,
            Permission.STOCK_DISPOSAL_WRITE,
            Permission.STOCK_DISPOSAL_VIEW,
        }
    ),
    UserRole.factory_manager: frozenset(
        {
            Permission.DASHBOARD_VIEW,
            Permission.REPORTS_VIEW,
            Permission.MASTERS_READ,
            Permission.INVENTORY_VIEW,
            Permission.BOOK_SETTINGS_VIEW,
            Permission.PROCESSING_MANAGE,
            Permission.PROCESSING_VIEW,
        }
    ),
}


def user_has_permission(user: User, permission: Permission) -> bool:
    if user.role is None:
        return False
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def require_assigned_role(user: User = Depends(get_current_user)) -> User:
    if user.role is None:
        raise HTTPException(status_code=403, detail=ROLE_NOT_ASSIGNED_MSG)
    return user


def require_permission(permission: Permission) -> Callable:
    def _dep(user: User = Depends(require_assigned_role)) -> User:
        if not user_has_permission(user, permission):
            raise HTTPException(status_code=403, detail=FORBIDDEN_MSG)
        return user

    return _dep


def require_any_permission(*permissions: Permission) -> Callable:
    def _dep(user: User = Depends(require_assigned_role)) -> User:
        if not any(user_has_permission(user, p) for p in permissions):
            raise HTTPException(status_code=403, detail=FORBIDDEN_MSG)
        return user

    return _dep


def require_roles(*roles: UserRole) -> Callable:
    allowed = frozenset(roles)

    def _dep(user: User = Depends(require_assigned_role)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail=FORBIDDEN_MSG)
        return user

    return _dep


def require_owner_user(user: User = Depends(require_assigned_role)) -> User:
    if user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail=OWNER_ONLY_VOID_MSG)
    return user


def require_void_user(user: User = Depends(require_owner_user)) -> User:
    if not user_has_permission(user, Permission.VOID):
        raise HTTPException(status_code=403, detail=OWNER_ONLY_VOID_MSG)
    return user
