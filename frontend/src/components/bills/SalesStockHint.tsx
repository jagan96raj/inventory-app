import { formatQtyKg } from "../../lib/format";
import { cn } from "../../lib/cn";

export default function SalesStockHint({
  availableKg,
  reservedKg,
  notDeliveredKg,
}: {
  availableKg: number;
  reservedKg: number;
  notDeliveredKg: number;
}) {
  const reservedWarn = reservedKg < 0;
  return (
    <div className="stock-hint flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <span>
        Available (on hand):{" "}
        <strong className="v2-mono font-semibold text-ink">{formatQtyKg(availableKg)}</strong>
      </span>
      <span className={cn(reservedWarn && "font-semibold text-amber-800 dark:text-amber-300")}>
        Reserved:{" "}
        <strong className="v2-mono">{formatQtyKg(reservedKg)}</strong>
      </span>
      <span>
        Not delivered:{" "}
        <strong className="v2-mono font-semibold text-ink">{formatQtyKg(notDeliveredKg)}</strong>
      </span>
    </div>
  );
}
