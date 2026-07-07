import { calcPreviewTotalKg, isLooseBagType, type BagTypeLike } from "./bagType";
import { formatQtyKg } from "./format";
import { parseBagCount, parseLooseKg } from "./qtyInput";
import type { StockAtLocation } from "./stockAtLocation";

export function exceedsAvailableStock(
  bagType: BagTypeLike | undefined,
  bagCount: number | string,
  looseKg: number | string,
  stockLine: StockAtLocation | undefined
): boolean {
  if (!bagType || !stockLine) return false;
  const qtyKg = calcPreviewTotalKg(bagType, bagCount, looseKg);
  if (qtyKg <= 0) return false;
  if (isLooseBagType(bagType)) {
    return qtyKg > Number(stockLine.loose_kg);
  }
  const bags = Number(bagCount) || 0;
  return bags > stockLine.bag_count || qtyKg > Number(stockLine.total_quantity_kg);
}

export function formatAvailableStock(
  bagType: BagTypeLike | undefined,
  stockLine: StockAtLocation | undefined
): string {
  if (!bagType || !stockLine) return "";
  if (isLooseBagType(bagType)) {
    return formatQtyKg(stockLine.loose_kg);
  }
  return `${stockLine.bag_count} bags (${formatQtyKg(stockLine.total_quantity_kg)})`;
}

export function stockExceedsMessage(
  bagType: BagTypeLike | undefined,
  bagCount: number | string,
  looseKg: number | string,
  stockLine: StockAtLocation | undefined
): string {
  if (!exceedsAvailableStock(bagType, bagCount, looseKg, stockLine) || !stockLine || !bagType) {
    return "";
  }
  if (isLooseBagType(bagType)) {
    return `Exceeds available stock (${formatQtyKg(stockLine.loose_kg)}) — cannot submit`;
  }
  return `Exceeds available stock (${stockLine.bag_count} bags · ${formatQtyKg(stockLine.total_quantity_kg)}) — cannot submit`;
}

/** Sum qty reserved by lines **before** excludeIndex in the same stock bucket (for per-line remaining display). */
export function reservedStockFromEarlierLines(
  bagType: BagTypeLike | undefined,
  lines: { bag_count: string; loose_kg: string }[],
  excludeIndex: number,
  sameBucket: (lineIndex: number) => boolean
): { bagCount: number; looseKg: number } {
  let bagCount = 0;
  let looseKg = 0;
  lines.forEach((ln, i) => {
    if (i >= excludeIndex || !sameBucket(i)) return;
    if (bagType && isLooseBagType(bagType)) {
      looseKg += parseLooseKg(ln.loose_kg);
    } else {
      bagCount += parseBagCount(ln.bag_count);
    }
  });
  return { bagCount, looseKg };
}

/** Sum qty reserved by other lines sharing the same stock bucket (e.g. location + bag type). */
export function reservedStockFromSiblingLines(
  bagType: BagTypeLike | undefined,
  lines: { bag_count: string; loose_kg: string }[],
  excludeIndex: number,
  sameBucket: (lineIndex: number) => boolean
): { bagCount: number; looseKg: number } {
  let bagCount = 0;
  let looseKg = 0;
  lines.forEach((ln, i) => {
    if (i === excludeIndex || !sameBucket(i)) return;
    if (bagType && isLooseBagType(bagType)) {
      looseKg += parseLooseKg(ln.loose_kg);
    } else {
      bagCount += parseBagCount(ln.bag_count);
    }
  });
  return { bagCount, looseKg };
}

export function remainingStockRowAfterReserved(
  bagType: BagTypeLike | undefined,
  stockLine: StockAtLocation | undefined,
  reservedBags: number,
  reservedLooseKg: number
): { bagCount: number; looseKg: number; totalKg: number } {
  if (!bagType || !stockLine) {
    return { bagCount: 0, looseKg: 0, totalKg: 0 };
  }
  const reservedKg = calcPreviewTotalKg(bagType, reservedBags, reservedLooseKg);
  if (isLooseBagType(bagType)) {
    const looseKg = Math.max(0, Number(stockLine.loose_kg) - reservedLooseKg);
    return { bagCount: 0, looseKg, totalKg: looseKg };
  }
  const bagCount = Math.max(0, stockLine.bag_count - reservedBags);
  const totalKg = Math.max(0, Number(stockLine.total_quantity_kg) - reservedKg);
  return { bagCount, looseKg: 0, totalKg };
}

export function formatRemainingStockAfterReserved(
  bagType: BagTypeLike | undefined,
  stockLine: StockAtLocation | undefined,
  reservedBags: number,
  reservedLooseKg: number
): string {
  if (!bagType || !stockLine) return "";
  const remaining = remainingStockRowAfterReserved(bagType, stockLine, reservedBags, reservedLooseKg);
  if (isLooseBagType(bagType)) {
    return formatQtyKg(remaining.looseKg);
  }
  return `${remaining.bagCount} bags (${formatQtyKg(remaining.totalKg)})`;
}

export function exceedsAvailableStockWithReserved(
  bagType: BagTypeLike | undefined,
  bagCount: number | string,
  looseKg: number | string,
  stockLine: StockAtLocation | undefined,
  reservedBags: number,
  reservedLooseKg: number
): boolean {
  if (!bagType || !stockLine) return false;
  const lineKg = calcPreviewTotalKg(bagType, bagCount, looseKg);
  const reservedKg = calcPreviewTotalKg(bagType, reservedBags, reservedLooseKg);
  if (lineKg <= 0 && reservedKg <= 0) return false;
  if (isLooseBagType(bagType)) {
    return reservedLooseKg + parseLooseKg(String(looseKg)) > Number(stockLine.loose_kg);
  }
  const totalBags = reservedBags + parseBagCount(String(bagCount));
  const totalKg = reservedKg + lineKg;
  return totalBags > stockLine.bag_count || totalKg > Number(stockLine.total_quantity_kg);
}

export function stockExceedsMessageWithReserved(
  bagType: BagTypeLike | undefined,
  bagCount: number | string,
  looseKg: number | string,
  stockLine: StockAtLocation | undefined,
  reservedBags: number,
  reservedLooseKg: number
): string {
  if (
    !exceedsAvailableStockWithReserved(
      bagType,
      bagCount,
      looseKg,
      stockLine,
      reservedBags,
      reservedLooseKg
    ) ||
    !stockLine ||
    !bagType
  ) {
    return "";
  }
  const avail = formatAvailableStock(bagType, stockLine);
  const reservedKg = calcPreviewTotalKg(bagType, reservedBags, reservedLooseKg);
  if (reservedKg > 0) {
    return `Exceeds available stock (${avail}) including other lines in this batch — cannot submit`;
  }
  return `Exceeds available stock (${avail}) — cannot submit`;
}

export function returnExceedsMessage(
  bagType: BagTypeLike | undefined,
  bagCount: number | string,
  looseKg: number | string,
  maxKg: number,
  maxBags: number
): string {
  if (!bagType) return "";
  const qtyKg = calcPreviewTotalKg(bagType, bagCount, looseKg);
  if (qtyKg <= 0) return "";
  if (isLooseBagType(bagType)) {
    if (qtyKg > maxKg) {
      return `Exceeds returnable quantity (${formatQtyKg(maxKg)}) — cannot submit`;
    }
    return "";
  }
  const bags = Number(bagCount) || 0;
  if (bags > maxBags || qtyKg > maxKg) {
    return `Exceeds returnable quantity (${maxBags} bags · ${formatQtyKg(maxKg)}) — cannot submit`;
  }
  return "";
}

export function deliverExceedsRemainingMessage(
  bagType: BagTypeLike | undefined,
  bagCount: number | string,
  looseKg: number | string,
  maxKg: number,
  maxBags: number
): string {
  if (!bagType) return "";
  const qtyKg = calcPreviewTotalKg(bagType, bagCount, looseKg);
  if (qtyKg <= 0) return "";
  if (isLooseBagType(bagType)) {
    if (qtyKg > maxKg) {
      return `Exceeds remaining on line (${formatQtyKg(maxKg)}) — cannot submit`;
    }
    return "";
  }
  const bags = Number(bagCount) || 0;
  if (bags > maxBags || qtyKg > maxKg) {
    return `Exceeds remaining on line (${maxBags} bags · ${formatQtyKg(maxKg)}) — cannot submit`;
  }
  return "";
}
