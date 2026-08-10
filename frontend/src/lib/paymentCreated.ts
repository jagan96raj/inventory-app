import type { Bill, Payment } from "../api/client";

const LAST_CREATED_KEY = "inventory.payment.lastCreated";
/** Only reuse remembered create for a short window (covers Electron state loss). */
const REMEMBER_MS = 120_000;

type Stored = { payment: Payment; at: number };

/** Survive Electron dropping react-router location.state after create. */
export function rememberPaymentCreated(payment: Payment): void {
  try {
    const payload: Stored = { payment, at: Date.now() };
    sessionStorage.setItem(LAST_CREATED_KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}

export function readRememberedPaymentCreated(): Payment | null {
  try {
    const raw = sessionStorage.getItem(LAST_CREATED_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Stored | Payment;
    if (parsed && typeof parsed === "object" && "payment" in parsed) {
      const stored = parsed as Stored;
      if (!stored.payment || typeof stored.payment.id !== "number") return null;
      if (Date.now() - stored.at > REMEMBER_MS) {
        sessionStorage.removeItem(LAST_CREATED_KEY);
        return null;
      }
      return stored.payment;
    }
    const payment = parsed as Payment;
    if (!payment || typeof payment.id !== "number") return null;
    return payment;
  } catch {
    return null;
  }
}

export function clearRememberedPaymentCreated(id?: number): void {
  try {
    if (id == null) {
      sessionStorage.removeItem(LAST_CREATED_KEY);
      return;
    }
    const cur = readRememberedPaymentCreated();
    if (!cur || cur.id === id) sessionStorage.removeItem(LAST_CREATED_KEY);
  } catch {
    /* ignore */
  }
}

function sameId(a: number | string | null | undefined, b: number | string | null | undefined): boolean {
  if (a == null || b == null) return false;
  return Number(a) === Number(b);
}

/** Merge a just-created payment into bill detail when list/detail GET is one-behind. */
export function mergePaymentIntoBill(bill: Bill, payment: Payment): Bill {
  if (!sameId(payment.bill_id, bill.id)) return bill;

  const existing = bill.payments ?? [];
  const payments = existing.some((p) => sameId(p.id, payment.id))
    ? existing.map((p) => (sameId(p.id, payment.id) ? payment : p))
    : [...existing, payment];

  for (const linked of payment.linked_payments ?? []) {
    if (!sameId(linked.bill_id, bill.id)) continue;
    if (payments.some((p) => sameId(p.id, linked.id))) continue;
    payments.push(linked);
  }

  payments.sort((a, b) => String(a.paid_at).localeCompare(String(b.paid_at)));

  const amount_paid = payment.amount_paid ?? bill.amount_paid;
  const amount_due = payment.amount_due ?? bill.amount_due ?? bill.due_amount;
  const grand = Number(payment.grand_total ?? bill.grand_total);
  const paid = Number(amount_paid);
  let payment_status = bill.payment_status;
  if (paid <= 0) payment_status = "unpaid";
  else if (grand > 0 && paid + 0.005 >= grand) payment_status = "paid";
  else payment_status = "partial";

  return {
    ...bill,
    payments,
    amount_paid,
    amount_due,
    due_amount: amount_due,
    payment_status,
    version: payment.bill_version ?? bill.version,
  };
}
