// Keep in lockstep with `backend/app/core/permissions.py`: the `Permission`
// union and `ROLE_PERMISSIONS` map below mirror the Python enum + role table
// by hand. When you add / rename / remove a permission on the backend, update
// both files in the same commit — otherwise the UI will hide or show controls
// that disagree with the API guard.
import { useMemo } from "react";
import { useAuth } from "../context/AuthContext";

export type UserRole = "owner" | "writer" | "stock_manager" | "factory_manager";

export type Permission =
  | "dashboard_view"
  | "reports_view"
  | "masters_read"
  | "masters_manage"
  | "book_settings_view"
  | "book_settings_edit"
  | "bills_manage"
  | "payments_manage"
  | "accounts_view"
  | "cashbook_manage"
  | "bank_accounts_manage"
  | "expense_categories_manage"
  | "fulfillment_write"
  | "fulfillment_view"
  | "job_work_manage"
  | "job_work_fulfillment_write"
  | "product_transfer_write"
  | "product_transfer_view"
  | "inventory_view"
  | "inventory_opening_stock"
  | "inventory_edit_qty"
  | "bag_change_write"
  | "bag_change_view"
  | "stock_disposal_write"
  | "stock_disposal_view"
  | "processing_manage"
  | "processing_view"
  | "void"
  | "users_manage"
  | "audit_view"
  | "notes_view";

const ROLE_PERMISSIONS: Record<UserRole, ReadonlySet<Permission>> = {
  owner: new Set<Permission>([
    "dashboard_view",
    "reports_view",
    "masters_read",
    "masters_manage",
    "book_settings_view",
    "book_settings_edit",
    "bills_manage",
    "payments_manage",
    "accounts_view",
    "cashbook_manage",
    "bank_accounts_manage",
    "expense_categories_manage",
    "fulfillment_write",
    "fulfillment_view",
    "job_work_manage",
    "job_work_fulfillment_write",
    "product_transfer_write",
    "product_transfer_view",
    "inventory_view",
    "inventory_opening_stock",
    "inventory_edit_qty",
    "bag_change_write",
    "bag_change_view",
    "stock_disposal_write",
    "stock_disposal_view",
    "processing_manage",
    "processing_view",
    "void",
    "users_manage",
    "audit_view",
    "notes_view",
  ]),
  writer: new Set([
    "dashboard_view",
    "reports_view",
    "masters_read",
    "inventory_view",
    "fulfillment_write",
    "fulfillment_view",
    "job_work_fulfillment_write",
    "product_transfer_write",
    "product_transfer_view",
    "notes_view",
  ]),
  stock_manager: new Set([
    "dashboard_view",
    "reports_view",
    "masters_read",
    "inventory_view",
    "bag_change_write",
    "bag_change_view",
    "stock_disposal_write",
    "stock_disposal_view",
    "notes_view",
  ]),
  factory_manager: new Set([
    "dashboard_view",
    "reports_view",
    "masters_read",
    "inventory_view",
    "book_settings_view",
    "processing_manage",
    "processing_view",
    "notes_view",
  ]),
};

export const ROLE_LABELS: Record<UserRole, string> = {
  owner: "Owner",
  writer: "Writer",
  stock_manager: "Stock manager",
  factory_manager: "Factory manager",
};

export function usePermissions() {
  const { user } = useAuth();
  const role = user?.role ?? null;

  return useMemo(() => {
    const permissions = role ? ROLE_PERMISSIONS[role] : new Set<Permission>();
    const can = (permission: Permission) => permissions.has(permission);
    return {
      role,
      hasRole: Boolean(role),
      can,
      isOwner: role === "owner",
      canVoid: can("void"),
      canManageUsers: can("users_manage"),
      canManageMasters: can("masters_manage"),
      canManageBills: can("bills_manage"),
      canManagePayments: can("payments_manage"),
      canViewAccounts: can("accounts_view"),
      canFulfillmentWrite: can("fulfillment_write"),
      canJobWorkFulfillment: can("job_work_fulfillment_write"),
      canJobWorkManage: can("job_work_manage"),
      canProductTransfer: can("product_transfer_write"),
      canBagChange: can("bag_change_write"),
      canStockDisposal: can("stock_disposal_write"),
      canProcessing: can("processing_manage"),
      canInventoryOpening: can("inventory_opening_stock"),
      canInventoryEditQty: can("inventory_edit_qty"),
      canViewBookSettings: can("book_settings_view"),
      canEditBookSettings: can("book_settings_edit"),
      canViewAuditLog: can("audit_view"),
    };
  }, [role]);
}
