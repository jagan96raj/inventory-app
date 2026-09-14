/** Display-only sales stock hint. Billing never changes on_hand. */

export type OpenBillRemaining = {
  bill_id: number;
  bill_date: string;
  remaining_kg: number;
  remaining_bags?: number;
};

export type SalesStockHintItem = {
  product_id: number;
  brand_id: number;
  bag_type_id: number;
  stock_source: string;
  customer_id?: number | null;
  on_hand_kg: string;
  on_hand_bags?: number;
  open_bills: { bill_id: number; bill_date: string; remaining_kg: string; remaining_bags?: number }[];
};

export type SalesStockHint = {
  availableKg: number;
  availableBags: number;
  reservedKg: number;
  reservedBags: number;
};

export function computeSalesStockHint(
  onHandKg: number,
  otherOpenBills: OpenBillRemaining[],
  onHandBags = 0
): SalesStockHint {
  const bills = otherOpenBills.filter((b) => b.remaining_kg > 0 || (b.remaining_bags ?? 0) > 0);
  const reservedKg = bills.reduce((sum, b) => sum + b.remaining_kg, 0);
  const reservedBags = bills.reduce((sum, b) => sum + (b.remaining_bags ?? 0), 0);
  return {
    availableKg: onHandKg,
    availableBags: onHandBags,
    reservedKg,
    reservedBags,
  };
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

export function hintFromOtherBills(
  item: SalesStockHintItem | undefined,
  onHandKg: number,
  onHandBags: number
): SalesStockHint {
  const others = (item?.open_bills ?? []).map((b) => ({
    bill_id: b.bill_id,
    bill_date: b.bill_date,
    remaining_kg: Number(b.remaining_kg) || 0,
    remaining_bags: Number(b.remaining_bags) || 0,
  }));
  return computeSalesStockHint(onHandKg, others, onHandBags);
}
