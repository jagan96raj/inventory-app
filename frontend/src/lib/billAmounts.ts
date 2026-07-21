/** Minimal bill money fields needed to resolve amount due. */
export type BillDueFields = {
  amount_due?: string | null;
  due_amount?: string | null;
  grand_total: string;
  amount_paid: string;
};

/**
 * Single source of truth for bill amount due.
 * Prefer API `amount_due` / `due_amount`; else grand_total − amount_paid.
 */
export function billDueAmount(bill: BillDueFields): number {
  return Number(
    bill.amount_due ?? bill.due_amount ?? Number(bill.grand_total) - Number(bill.amount_paid)
  );
}
