import OperationHistoryPage, {
  OperationHistoryVoidAction,
  OperationHistoryVoidCell,
} from "../../components/operations/OperationHistoryPage";
import { cn } from "../../lib/cn";
import { formatQtyKg } from "../../lib/format";

type TransferRecord = {
  id: number;
  product_name?: string;
  brand_name?: string;
  bag_type_name?: string;
  from_location_name?: string;
  to_location_name?: string;
  bag_count: number;
  loose_kg: string;
  quantity_kg: string;
  operation_at: string;
  voided_at?: string | null;
  notes?: string | null;
};

export default function ProductTransferHistoryPage() {
  return (
    <OperationHistoryPage<TransferRecord>
      title="Product transfer history"
      subtitle="All location transfers — newest first"
      formTo="/operations/product-transfer"
      historyTo="/histories/product-transfer"
      listPath="/api/operations/product-transfer"
      voidPath={(id) => `/api/operations/product-transfer/${id}/void`}
      emptyMessage="No transfers yet."
      voidSuccessMessage="Transfer voided — stock restored"
      voidDialogTitle="Void this transfer?"
      voidDialogDescription="Reverse this transfer?"
      renderTable={(rows, onVoid) => (
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Product</th>
              <th>From</th>
              <th>To</th>
              <th>Bag type</th>
              <th className="col-num">Qty</th>
              <th>Notes</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const voided = Boolean(r.voided_at);
              return (
                <tr key={r.id} className={cn(voided && "opacity-65")}>
                  <td>{new Date(r.operation_at).toLocaleString()}</td>
                  <td>
                    {r.product_name} · {r.brand_name}
                  </td>
                  <td>{r.from_location_name}</td>
                  <td>{r.to_location_name}</td>
                  <td className={cn(voided && "line-through")}>
                    {r.bag_type_name}
                    {r.bag_count > 0 ? ` (${r.bag_count} bags)` : ` (${r.loose_kg} kg loose)`}
                  </td>
                  <td className={cn("col-num", voided && "line-through")}>
                    {formatQtyKg(r.quantity_kg)}
                  </td>
                  <td>{r.notes?.trim() || "—"}</td>
                  <OperationHistoryVoidCell voidedAt={r.voided_at} onVoid={() => onVoid(r)} />
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      renderCards={(rows, onVoid) =>
        rows.map((r) => {
          const voided = Boolean(r.voided_at);
          return (
            <div
              key={r.id}
              className={cn(
                "space-y-3 rounded-2xl border border-line/80 bg-surface p-4",
                voided && "opacity-65"
              )}
            >
              <div className="min-w-0">
                <p className="font-semibold text-ink">
                  {r.product_name} · {r.brand_name}
                </p>
                <p className="mt-0.5 text-sm text-ink-muted">
                  {r.from_location_name} → {r.to_location_name}
                </p>
                <p className="v2-mono text-xs text-ink-subtle">
                  {new Date(r.operation_at).toLocaleString()}
                </p>
              </div>
              <dl className={cn("grid grid-cols-2 gap-2 text-sm", voided && "line-through")}>
                <div className="col-span-2">
                  <dt className="text-ink-subtle">Bag / qty</dt>
                  <dd className="text-ink">
                    {r.bag_type_name}
                    {r.bag_count > 0 ? ` (${r.bag_count} bags)` : ` (${r.loose_kg} kg loose)`} ·{" "}
                    {formatQtyKg(r.quantity_kg)}
                  </dd>
                </div>
                {r.notes?.trim() ? (
                  <div className="col-span-2">
                    <dt className="text-ink-subtle">Notes</dt>
                    <dd className="text-ink">{r.notes.trim()}</dd>
                  </div>
                ) : null}
              </dl>
              <OperationHistoryVoidAction voidedAt={r.voided_at} onVoid={() => onVoid(r)} />
            </div>
          );
        })
      }
    />
  );
}
