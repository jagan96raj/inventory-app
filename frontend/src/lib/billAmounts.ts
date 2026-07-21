/** Minimal bill money fields needed to resolve amount due. */
export type BillDueFields = {
  amount_due?: string | null;
  due_amount?: string | null;
  grand_total?: string | null;
  amount_paid?: string | null;
};

/**
 * Single source of truth for bill amount due.
 * Prefer API `amount_due` / `due_amount`; else grand_total − amount_paid.
 * Smoke cases: undefined/null/non-numeric inputs resolve to 0 and never NaN.
 */
export function billDueAmount(bill: BillDueFields): number {
  const asFinite = (value: unknown): number | null => {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };
  const explicitDue = asFinite(bill.amount_due) ?? asFinite(bill.due_amount);
  if (explicitDue != null) return Math.max(0, explicitDue);
  const grandTotal = asFinite(bill.grand_total) ?? 0;
  const amountPaid = asFinite(bill.amount_paid) ?? 0;
  return Math.max(0, grandTotal - amountPaid);
}
