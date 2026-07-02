const ACTION_LABELS: Record<string, string> = {
  payment_voided: "Payment voided",
  fulfillment_voided: "Fulfillment voided",
  bill_voided: "Bill voided",
  bill_edited: "Bill edited",
  inventory_qty_edited: "Inventory qty edited",
  master_deleted: "Master deleted",
  bag_change_voided: "Bag change voided",
  product_transfer_voided: "Product transfer voided",
  stock_disposal_voided: "Stock disposal voided",
  processing_batch_voided: "Processing batch voided",
  cash_book_voided: "Cash book entry voided",
  job_work_order_voided: "Job work order voided",
  job_work_receipt_voided: "Job work receipt voided",
  user_created: "User created",
  user_updated: "User updated",
  user_disabled: "User disabled",
  user_enabled: "User enabled",
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  payment: "Payment",
  bill: "Bill",
  fulfillment_entry: "Fulfillment",
  inventory: "Inventory",
  product: "Product",
  brand: "Brand",
  customer: "Customer",
  location: "Location",
  bag_type: "Bag type",
  bag_change: "Bag change",
  product_transfer: "Transfer",
  stock_disposal: "Disposal",
  processing_batch: "Processing batch",
  cash_book_entry: "Cash book",
  job_work_order: "Job work order",
  job_work_receipt: "Job work receipt",
  user: "User",
};

export function auditActionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replace(/_/g, " ");
}

export function auditEntityTypeLabel(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType.replace(/_/g, " ");
}

export const AUDIT_ACTION_OPTIONS = Object.entries(ACTION_LABELS).map(([value, label]) => ({
  value,
  label,
}));

export const AUDIT_ENTITY_TYPE_OPTIONS = Object.entries(ENTITY_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));
