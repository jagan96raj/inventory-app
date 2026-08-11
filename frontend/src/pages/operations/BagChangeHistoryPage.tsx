import OperationHistoryPage, {
  OperationHistoryVoidAction,
  OperationHistoryVoidCell,
} from "../../components/operations/OperationHistoryPage";
import { cn } from "../../lib/cn";
import { formatQtyKg } from "../../lib/format";

type BagChangeRecord = {
  id: number;
  location_name?: string;
  product_name?: string;
  brand_name?: string;
  from_bag_type_name?: string;
  from_bag_count: number;
  from_loose_kg: string;
  from_quantity_kg: string;
  quantity_loss_kg: string;
  operation_at: string;
  voided_at?: string | null;
  to_lines: {
    to_bag_type_name?: string;
    bag_count: number;
    loose_kg: string;
    quantity_kg: string;
  }[];
};

export default function BagChangeHistoryPage() {
  return (
    <OperationHistoryPage<BagChangeRecord>
      title="Bag change history"
      subtitle="All bag changes — newest first"
      formTo="/operations/bag-change"
      historyTo="/histories/bag-change"
      listPath="/api/operations/bag-change"
      voidPath={(id) => `/api/operations/bag-change/${id}/void`}
      emptyMessage="No bag changes yet."
      voidSuccessMessage="Bag change voided — stock restored"
      voidDialogTitle="Void this bag change?"
      voidDialogDescription="Reverse this bag change and restore stock?"
      renderTable={(rows, onVoid) => (
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Location</th>
              <th>Product</th>
              <th>From</th>
              <th className="col-num">From kg</th>
              <th className="col-num">Loss kg</th>
              <th>To lines</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const voided = Boolean(r.voided_at);
              return (
                <tr key={r.id} className={cn(voided && "opacity-65")}>
                  <td>{new Date(r.operation_at).toLocaleString()}</td>
                  <td>{r.location_name}</td>
                  <td>
                    {r.product_name} · {r.brand_name}
                  </td>
                  <td className={cn(voided && "line-through")}>
                    {r.from_bag_type_name} (
                    {r.from_bag_count > 0 ? `${r.from_bag_count} bags` : `${r.from_loose_kg} kg loose`})
                  </td>
                  <td className={cn("col-num", voided && "line-through")}>
                    {formatQtyKg(r.from_quantity_kg)}
                  </td>
                  <td className={cn("col-num", voided && "line-through")}>
                    {formatQtyKg(r.quantity_loss_kg)}
                  </td>
                  <td className={cn(voided && "line-through")}>
                    {r.to_lines.map((tl, i) => (
                      <span key={i} className="operations-history-line">
                        {tl.to_bag_type_name}: {tl.bag_count > 0 ? `${tl.bag_count} bags` : `${tl.loose_kg} kg`} (
                        {formatQtyKg(tl.quantity_kg)})
                      </span>
                    ))}
                  </td>
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
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-ink">
                    {r.product_name} · {r.brand_name}
                  </p>
                  <p className="mt-0.5 text-sm text-ink-muted">{r.location_name}</p>
                  <p className="v2-mono text-xs text-ink-subtle">
                    {new Date(r.operation_at).toLocaleString()}
                  </p>
                </div>
              </div>
              <dl className={cn("grid grid-cols-2 gap-2 text-sm", voided && "line-through")}>
                <div className="col-span-2">
                  <dt className="text-ink-subtle">From</dt>
                  <dd className="text-ink">
                    {r.from_bag_type_name} (
                    {r.from_bag_count > 0 ? `${r.from_bag_count} bags` : `${r.from_loose_kg} kg loose`}) ·{" "}
                    {formatQtyKg(r.from_quantity_kg)}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-subtle">Loss</dt>
                  <dd className="v2-mono text-ink">{formatQtyKg(r.quantity_loss_kg)}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-ink-subtle">To</dt>
                  <dd className="space-y-1 text-ink">
                    {r.to_lines.map((tl, i) => (
                      <p key={i}>
                        {tl.to_bag_type_name}: {tl.bag_count > 0 ? `${tl.bag_count} bags` : `${tl.loose_kg} kg`} (
                        {formatQtyKg(tl.quantity_kg)})
                      </p>
                    ))}
                  </dd>
                </div>
              </dl>
              <OperationHistoryVoidAction voidedAt={r.voided_at} onVoid={() => onVoid(r)} />
            </div>
          );
        })
      }
    />
  );
}
