import { formatQtyKg } from "./format";

export type JwQtyFields = {
  is_loose: boolean;
  bags?: number;
  loose_kg?: string | number;
  kg?: string | number;
};

function formatBags(bags: number): string {
  return `${bags.toLocaleString("en-IN")} bag${bags === 1 ? "" : "s"}`;
}

/** Primary qty label: bags for bagged lines, kg for loose. */
export function formatJwPrimaryQty(line: JwQtyFields): string {
  if (line.is_loose) {
    const loose = line.loose_kg ?? line.kg ?? 0;
    return formatQtyKg(loose);
  }
  return formatBags(line.bags ?? 0);
}

/** Optional kg subline for bagged rows (ordered/received totals). */
export function formatJwKgSubline(kg: string | number | undefined): string | null {
  if (kg === undefined || kg === null || kg === "") return null;
  const n = Number(kg);
  if (!Number.isFinite(n) || n <= 0) return null;
  return formatQtyKg(kg);
}

type JwLineQtyRow = {
  is_loose: boolean;
  ordered_bags?: number;
  ordered_loose_kg?: string | number;
  ordered_kg?: string | number;
  ordered_quantity_kg?: string | number;
  received_bags?: number;
  received_loose_kg?: string | number;
  received_kg?: string | number;
  received_quantity_kg?: string | number;
  returned_bags?: number;
  returned_loose_kg?: string | number;
  returned_kg?: string | number;
  returned_quantity_kg?: string | number;
  net_received_bags?: number;
  net_received_loose_kg?: string | number;
  net_received_kg?: string | number;
  remaining_receive_bags?: number;
  remaining_receive_loose_kg?: string | number;
  remaining_receive_kg?: string | number;
  custody_bags?: number;
  custody_loose_kg?: string | number;
  custody_kg?: string | number;
  weight_per_bag_kg?: string | number;
};

/** Prefer API bag remainder; fall back to ordered − received when API sends 0 incorrectly. */
function bagRemainder(
  explicit: number | undefined,
  ordered: number,
  received: number,
  returned = 0,
  remainingKg?: string | number,
  weightPerBagKg?: string | number
): number {
  const computed = Math.max(ordered - received + returned, 0);
  if (explicit != null && !(explicit === 0 && computed > 0)) {
    return explicit;
  }
  if (computed > 0) return computed;
  const kg = Number(remainingKg ?? 0);
  const w = Number(weightPerBagKg ?? 0);
  if (kg > 0 && w > 0) return Math.floor(kg / w);
  return explicit ?? 0;
}

export function jwOrderedQty(line: JwLineQtyRow): JwQtyFields {
  if (line.is_loose) {
    return {
      is_loose: true,
      loose_kg: line.ordered_loose_kg ?? line.ordered_kg ?? line.ordered_quantity_kg,
      kg: line.ordered_kg ?? line.ordered_quantity_kg,
    };
  }
  return {
    is_loose: false,
    bags: line.ordered_bags ?? 0,
    kg: line.ordered_kg ?? line.ordered_quantity_kg,
  };
}

export function jwReceivedQty(line: JwLineQtyRow): JwQtyFields {
  if (line.is_loose) {
    return {
      is_loose: true,
      loose_kg: line.received_loose_kg ?? line.received_kg ?? line.received_quantity_kg,
      kg: line.received_kg ?? line.received_quantity_kg,
    };
  }
  return {
    is_loose: false,
    bags: line.received_bags ?? 0,
    kg: line.received_kg ?? line.received_quantity_kg,
  };
}

/** User-facing "Received (net)" — material still with you after returns. */
export function jwNetReceivedQty(line: JwLineQtyRow): JwQtyFields {
  if (line.is_loose) {
    const loose =
      line.net_received_loose_kg ??
      line.net_received_kg ??
      Math.max(
        Number(line.received_loose_kg ?? line.received_kg ?? line.received_quantity_kg ?? 0) -
          Number(line.returned_loose_kg ?? line.returned_kg ?? line.returned_quantity_kg ?? 0),
        0
      );
    return {
      is_loose: true,
      loose_kg: loose,
      kg: line.net_received_kg ?? loose,
    };
  }
  const bags =
    line.net_received_bags ??
    Math.max((line.received_bags ?? 0) - (line.returned_bags ?? 0), 0);
  const kg =
    line.net_received_kg ??
    Math.max(
      Number(line.received_kg ?? line.received_quantity_kg ?? 0) -
        Number(line.returned_kg ?? line.returned_quantity_kg ?? 0),
      0
    );
  return { is_loose: false, bags, kg };
}

export function jwRemainingReceiveQty(line: JwLineQtyRow): JwQtyFields {
  if (line.is_loose) {
    return {
      is_loose: true,
      loose_kg: line.remaining_receive_loose_kg ?? line.remaining_receive_kg,
      kg: line.remaining_receive_kg,
    };
  }
  return {
    is_loose: false,
    bags: bagRemainder(
      line.remaining_receive_bags,
      line.ordered_bags ?? 0,
      line.received_bags ?? 0,
      line.returned_bags ?? 0,
      line.remaining_receive_kg,
      line.weight_per_bag_kg
    ),
    kg: line.remaining_receive_kg,
  };
}

/** @deprecated Legacy alias — use {@link jwNetReceivedQty} for UI "Received (net)". */
export function jwCustodyQty(line: JwLineQtyRow): JwQtyFields {
  return jwNetReceivedQty(line);
}
