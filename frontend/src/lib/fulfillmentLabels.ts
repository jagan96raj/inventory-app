import { formatQtyKg } from "./format";

export type FulfillmentQtyLike = {
  quantity_kg: string | number;
  bag_count: number;
};

export function fulfillmentEntryLabel(
  entryType: string,
  billType: "sales" | "purchase" | string
): string {
  const isSales = billType === "sales";
  if (entryType === "return") return "Return";
  return isSales ? "Deliver" : "Receive";
}

export function fulfillmentQtyLabel(entry: FulfillmentQtyLike, isLoose: boolean): string {
  if (isLoose) return formatQtyKg(entry.quantity_kg);
  return `${entry.bag_count} bags (${formatQtyKg(entry.quantity_kg)})`;
}
