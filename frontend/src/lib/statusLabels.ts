export type PaymentStatusFilter = "all" | "unpaid" | "partial" | "paid";
export type DeliveryStatusFilter = "all" | "not_delivered" | "partial" | "delivered";

export function normalizePaymentStatus(status: string): "unpaid" | "partial" | "paid" {
  if (status === "pending") return "unpaid";
  if (status === "done") return "paid";
  return status as "unpaid" | "partial" | "paid";
}

export function normalizeDeliveryStatus(status: string): "not_delivered" | "partial" | "delivered" {
  if (status === "pending") return "not_delivered";
  if (status === "done") return "delivered";
  return status as "not_delivered" | "partial" | "delivered";
}

export function paymentModeLabel(mode: string): string {
  switch (mode) {
    case "cash":
      return "Cash";
    case "bank":
      return "Bank";
    case "credit":
      return "Credit balance";
    case "debit":
      return "Debit balance";
    case "setoff":
      return "Set-off";
    default:
      return mode;
  }
}

export function paymentStatusLabel(status: string): string {
  switch (status) {
    case "unpaid":
      return "Unpaid";
    case "partial":
      return "Partial";
    case "paid":
      return "Paid";
    case "pending":
      return "Unpaid";
    case "done":
      return "Paid";
    default:
      return status;
  }
}

export function deliveryStatusLabel(status: string): string {
  switch (status) {
    case "not_delivered":
      return "Not Delivered";
    case "partial":
      return "Partial";
    case "delivered":
      return "Delivered";
    case "pending":
      return "Not Delivered";
    case "done":
      return "Delivered";
    default:
      return status;
  }
}

export function statusBadgeClass(kind: "payment" | "delivery", status: string): string {
  const s = status === "pending" ? "not_delivered" : status === "done" ? "delivered" : status;
  if (kind === "payment") {
    const p = status === "pending" ? "unpaid" : status === "done" ? "paid" : status;
    return `badge badge-${p}`;
  }
  return `badge badge-${s}`;
}
