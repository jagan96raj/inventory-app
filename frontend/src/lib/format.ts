export type QtyUnit = "kg" | "quintal" | "ton";

const UNIT_FACTORS: Record<QtyUnit, number> = {
  kg: 1,
  quintal: 100,
  ton: 1000,
};

let qtyUnit: QtyUnit = "kg";

export function getQtyUnit(): QtyUnit {
  return qtyUnit;
}

export function setQtyUnit(u: QtyUnit) {
  qtyUnit = u;
}

export function formatInr(value: string | number): string {
  const n = Number(value);
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatQtyKg(kg: string | number): string {
  const raw = Number(kg);
  const factor = UNIT_FACTORS[qtyUnit];
  const v = raw / factor;
  const label = qtyUnit === "kg" ? "kg" : qtyUnit === "quintal" ? "q" : "t";
  return `${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${label}`;
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Local calendar date as YYYY-MM-DD (matches bill/job date pickers). */
export function localIsoDate(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function validateDateNotFuture(iso: string, maxIso = localIsoDate()): string | null {
  if (!iso) return "Date is required";
  if (iso > maxIso) return "Date cannot be in the future";
  return null;
}

export function nowIsoLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

const inrCompact = new Intl.NumberFormat("en-IN", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function formatInrCompact(value: string | number): string {
  return `₹${inrCompact.format(Number(value || 0))}`;
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelative(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = d.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const rtf = new Intl.RelativeTimeFormat("en-IN", { numeric: "auto" });
  const map: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 365 * 24 * 3600 * 1000],
    ["month", 30 * 24 * 3600 * 1000],
    ["day", 24 * 3600 * 1000],
    ["hour", 3600 * 1000],
    ["minute", 60 * 1000],
  ];
  for (const [unit, ms] of map) {
    if (abs >= ms || unit === "minute") {
      return rtf.format(Math.round(diffMs / ms), unit);
    }
  }
  return formatDateTime(d);
}

