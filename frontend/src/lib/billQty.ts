import { formatQtyKg } from "./format";

/** Sum ordered bags + kg from bill lines (detail / print). */
export function sumOrderedBagsKg(
  lines: { ordered_bags?: number | null; ordered_quantity_kg?: string | number | null }[]
): { bags: number; kg: number } {
  let bags = 0;
  let kg = 0;
  for (const line of lines) {
    bags += Number(line.ordered_bags) || 0;
    kg += Number(line.ordered_quantity_kg) || 0;
  }
  return { bags, kg };
}

export function formatBagsKgLabel(bags: number, kg: string | number): string {
  return `${bags} bags · ${formatQtyKg(kg)}`;
}
