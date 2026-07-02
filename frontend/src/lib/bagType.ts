/** Bag type with loose flag (API or joined row). */
export type BagTypeLike = {
  is_loose: boolean;
  weight_per_bag_kg?: string | number;
};

export function isLooseBagType(bt: BagTypeLike | null | undefined): boolean {
  return Boolean(bt?.is_loose);
}

/** Preview total kg for inventory/bill qty (bagged = bags × weight only). */
export function calcPreviewTotalKg(
  bt: BagTypeLike | undefined,
  bagCount: number | string,
  looseKg: number | string
): number {
  if (!bt) return 0;
  if (isLooseBagType(bt)) return Number(looseKg) || 0;
  return (Number(bagCount) || 0) * Number(bt.weight_per_bag_kg ?? 0);
}

export function formatBagTypeWeight(bt: { is_loose: boolean; weight_per_bag_kg: string }): string {
  return bt.is_loose ? "—" : bt.weight_per_bag_kg;
}
