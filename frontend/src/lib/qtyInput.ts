import { isLooseBagType, type BagTypeLike } from "./bagType";

/** Empty quantity fields — no prefilled 0 or 1 in forms. */
export const PH_BAGS = "Enter bags";
export const PH_LOOSE_KG = "Enter kg";
export const PH_RATE = "Rate per kg";
export const PH_AMOUNT = "Enter amount";
export const PH_PERCENT = "0";
export const PH_ADJUSTMENT = "0";

export function emptyQtyFields(): { bag_count: string; loose_kg: string } {
  return { bag_count: "", loose_kg: "" };
}

export function clearQtyOnBagTypeChange(): { bag_count: string; loose_kg: string } {
  return emptyQtyFields();
}

export function parseBagCount(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
}

export function parseLooseKg(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

export function parseOptionalNumber(value: string): number {
  if (value.trim() === "") return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function isQtyComplete(
  bt: BagTypeLike | null | undefined,
  bagCount: string,
  looseKg: string
): boolean {
  if (!bt) return false;
  if (isLooseBagType(bt)) {
    const v = looseKg.trim();
    return v !== "" && parseLooseKg(v) > 0;
  }
  const v = bagCount.trim();
  return v !== "" && parseBagCount(v) > 0;
}

export function stockLineStarted(line: {
  location_id: string;
  bag_type_id: string;
  bag_count: string;
  loose_kg: string;
}): boolean {
  return Boolean(
    line.location_id || line.bag_type_id || line.bag_count.trim() || line.loose_kg.trim()
  );
}

export function stockLineComplete(
  bt: BagTypeLike | null | undefined,
  line: { location_id: string; bag_type_id: string; bag_count: string; loose_kg: string }
): boolean {
  return Boolean(line.location_id && line.bag_type_id && isQtyComplete(bt, line.bag_count, line.loose_kg));
}

export function qtyFieldError(
  bt: BagTypeLike | null | undefined,
  bagCount: string,
  looseKg: string
): string {
  if (!bt) return "";
  if (isLooseBagType(bt)) {
    if (looseKg.trim() === "") return "Enter loose kg";
    if (parseLooseKg(looseKg) <= 0) return "Loose quantity must be greater than zero";
    return "";
  }
  if (bagCount.trim() === "") return "Enter number of bags";
  if (parseBagCount(bagCount) <= 0) return "At least one bag required";
  return "";
}

export function outputLineStarted(line: {
  brand_id: string;
  location_id: string;
  bag_type_id: string;
  bag_count: string;
  loose_kg: string;
}): boolean {
  return Boolean(line.brand_id || stockLineStarted(line));
}

export function validateStockLineQty(
  bt: (BagTypeLike & { name?: string }) | null | undefined,
  line: { bag_count: string; loose_kg: string },
  label: string
): string | null {
  if (!bt) return `${label}: select a bag type`;
  const name = bt.name ? String(bt.name) : "bag type";
  if (isLooseBagType(bt)) {
    if (line.bag_count.trim() && parseBagCount(line.bag_count) > 0) {
      return `${label} (${name}): this is a loose type — enter kg, not bags`;
    }
    const err = qtyFieldError(bt, line.bag_count, line.loose_kg);
    return err ? `${label} (${name}): ${err}` : null;
  }
  if (line.loose_kg.trim() && parseLooseKg(line.loose_kg) > 0) {
    return `${label} (${name}): this is a bagged type — enter number of bags, not kg`;
  }
  const err = qtyFieldError(bt, line.bag_count, line.loose_kg);
  return err ? `${label} (${name}): ${err}` : null;
}
