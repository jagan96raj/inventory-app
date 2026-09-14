/** Display-only sales stock hint. Billing never changes on_hand. */

export type OpenBillRemaining = {
  bill_id: number;
  bill_date: string;
  remaining_kg: number;
};

export type SalesStockHintItem = {
  product_id: number;
  brand_id: number;
  bag_type_id: number;
  stock_source: string;
  customer_id?: number | null;
  on_hand_kg: string;
  open_bills: { bill_id: number; bill_date: string; remaining_kg: string }[];
};

export type SalesStockHint = {
  availableKg: number;
  reservedKg: number;
  notDeliveredKg: number;
};

const UNSAVED_BILL_ID = Number.MAX_SAFE_INTEGER;

export function computeSalesStockHint(
  onHandKg: number,
  openBills: OpenBillRemaining[]
): SalesStockHint {
  const bills = openBills
    .filter((b) => b.remaining_kg > 0)
    .slice()
    .sort((a, b) => a.bill_date.localeCompare(b.bill_date) || a.bill_id - b.bill_id);
  const notDeliveredKg = bills.reduce((sum, b) => sum + b.remaining_kg, 0);
  if (bills.length <= 1) {
    return { availableKg: onHandKg, reservedKg: 0, notDeliveredKg };
  }
  const laterQty = bills.slice(1).reduce((sum, b) => sum + b.remaining_kg, 0);
  return { availableKg: onHandKg, reservedKg: onHandKg - laterQty, notDeliveredKg };
}

export function mergeFormIntoOpenBills(
  saved: OpenBillRemaining[],
  formRemainingKg: number,
  opts?: { billId?: number; billDate?: string }
): OpenBillRemaining[] {
  if (formRemainingKg <= 0) return saved;
  return [
    ...saved,
    {
      bill_id: opts?.billId ?? UNSAVED_BILL_ID,
      bill_date: opts?.billDate ?? "9999-12-31",
      remaining_kg: formRemainingKg,
    },
  ];
}

export function findHintItem(
  items: SalesStockHintItem[],
  productId: string,
  brandId: string,
  bagTypeId: string,
  stockSource: string,
  customerId?: string | null
): SalesStockHintItem | undefined {
  const pid = Number(productId);
  const bid = Number(brandId);
  const bag = Number(bagTypeId);
  const cust = stockSource === "job_work" && customerId ? Number(customerId) : null;
  return items.find((it) => {
    if (it.product_id !== pid || it.brand_id !== bid || it.bag_type_id !== bag) return false;
    if (it.stock_source !== stockSource) return false;
    if (stockSource === "job_work") {
      return Number(it.customer_id) === cust;
    }
    return it.customer_id == null;
  });
}

export function hintFromItemAndForm(
  item: SalesStockHintItem | undefined,
  onHandKg: number,
  formRemainingKg: number,
  opts?: { billId?: number; billDate?: string }
): SalesStockHint {
  const saved = (item?.open_bills ?? []).map((b) => ({
    bill_id: b.bill_id,
    bill_date: b.bill_date,
    remaining_kg: Number(b.remaining_kg) || 0,
  }));
  return computeSalesStockHint(onHandKg, mergeFormIntoOpenBills(saved, formRemainingKg, opts));
}
