import { formatQtyKg } from "../../lib/format";

export default function SalesStockHint({
  isLoose,
  availableKg,
  availableBags,
  reservedKg,
  reservedBags,
}: {
  isLoose: boolean;
  availableKg: number;
  availableBags: number;
  reservedKg: number;
  reservedBags: number;
}) {
  const available = isLoose ? formatQtyKg(availableKg) : `${availableBags} bags`;
  const reservedQty = isLoose ? reservedKg : reservedBags;
  const reserved = isLoose ? formatQtyKg(reservedKg) : `${reservedBags} bags`;
  return (
    <div className="stock-hint flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <span>
        Available: <strong className="v2-mono font-semibold text-ink">{available}</strong>
      </span>
      {reservedQty > 0 && (
        <span>
          Reserved: <strong className="v2-mono font-semibold text-ink">{reserved}</strong>
        </span>
      )}
    </div>
  );
}
